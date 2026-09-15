import type {
  BackendJobStatus,
  JobRecord,
  PublicEvent,
  StructuredMessage,
  ThinkingProjection,
  ThinkingStep,
} from '../../types/domain'
import type { DecodedSseEvent } from '../../api/events.schemas'
import { acceptEventId, createEventCursor, markRendered } from './event-cursor'

export interface ReducerResult {
  state: JobRecord
  applied: boolean
  duplicate: boolean
  unknown: boolean
  terminal: boolean
}

function createThinking(status: ThinkingProjection['status'] = 'active', elapsedSeconds = 0): ThinkingProjection {
  return {
    status,
    startedAt: Date.now() - Math.max(0, elapsedSeconds) * 1000,
    elapsedSeconds: Math.max(0, elapsedSeconds),
    steps: {},
    stepOrder: [],
    draftStreamId: null,
    draftText: '',
    finalResult: null,
    errorMessage: null,
    waitingInput: null,
  }
}

function cloneThinking(thinking: ThinkingProjection): ThinkingProjection {
  const steps: Record<string, ThinkingStep> = {}
  for (const [key, step] of Object.entries(thinking.steps)) {
    steps[key] = { ...step, details: [...step.details] }
  }
  return {
    ...thinking,
    steps,
    stepOrder: [...thinking.stepOrder],
    waitingInput: thinking.waitingInput ? { ...thinking.waitingInput } : null,
    finalResult: thinking.finalResult ? { ...thinking.finalResult } : null,
  }
}

export function createJobRecord(
  jobId: string,
  sessionId: string,
  status: BackendJobStatus = 'queued',
  initialCursor = 0,
): JobRecord {
  const cursor = createEventCursor(initialCursor)
  const uiState = status === 'queued' ? 'queued' : status === 'running' ? 'running' : status === 'waiting_input' ? 'waiting_input' : status === 'succeeded' ? 'completed' : status
  return {
    jobId,
    sessionId,
    backendStatus: status,
    uiState,
    connection: 'idle',
    generation: 0,
    ...cursor,
    events: [],
    textSeenKeys: [],
    textStreams: {},
    thinking: createThinking(status === 'waiting_input' ? 'waiting_input' : status === 'succeeded' ? 'completed' : status === 'failed' ? 'failed' : status === 'canceled' ? 'canceled' : 'active'),
    errorMessage: null,
    errorCode: null,
    cancelKey: null,
    cancelInFlight: false,
  }
}

function stringField(data: PublicEvent, name: string): string {
  const value = data[name]
  return typeof value === 'string' ? value : ''
}

function numberField(data: PublicEvent, name: string): number | null {
  const value = data[name]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function structuredResult(value: unknown): StructuredMessage {
  if (typeof value === 'object' && value !== null && 'type' in value) {
    const candidate = value as Record<string, unknown>
    if (typeof candidate.type === 'string') return { ...candidate, type: candidate.type }
  }
  return {
    type: 'text',
    summary: typeof value === 'string' ? value : JSON.stringify(value),
  }
}

function appendDetail(thinking: ThinkingProjection, stepId: string, detail: string): void {
  if (!stepId || !detail) return
  const step = thinking.steps[stepId]
  if (step) step.details.push(detail)
}

function releaseTextBuffers(state: JobRecord): void {
  state.textSeenKeys = []
  state.textStreams = {}
}

function ensureStep(thinking: ThinkingProjection, data: PublicEvent): ThinkingStep | null {
  const stepId = stringField(data, 'step_id')
  if (!stepId) return null
  const existing = thinking.steps[stepId]
  if (existing) return existing
  const step: ThinkingStep = {
    stepId,
    nodeName: stringField(data, 'node_name'),
    title: stringField(data, 'title') || stringField(data, 'node_name'),
    status: 'in-progress',
    duration: null,
    details: [],
  }
  thinking.steps[stepId] = step
  thinking.stepOrder.push(stepId)
  return step
}

function applyKnownEvent(state: JobRecord, event: DecodedSseEvent): { state: JobRecord; visible: boolean; terminal: boolean } {
  const data = event.data
  const thinking = cloneThinking(state.thinking)
  const next: JobRecord = {
    ...state,
    thinking,
    events: event.id === null ? [...state.events] : [...state.events, { id: event.id, type: data.type, data: { ...data } }],
  }
  let visible = true
  let terminal = false

  switch (data.type) {
    case 'heartbeat':
      visible = false
      break
    case 'node_start':
      ensureStep(thinking, data)
      break
    case 'progress':
    case 'decision': {
      const step = ensureStep(thinking, data)
      if (step) step.details.push(stringField(data, 'summary'))
      break
    }
    case 'tool_call_start': {
      const step = ensureStep(thinking, data)
      const fields = Array.isArray(data.argument_keys) ? data.argument_keys.join('、') : ''
      if (step) step.details.push(`调用工具：${stringField(data, 'tool_name')}${fields ? `（参数字段：${fields}）` : ''}`)
      break
    }
    case 'tool_call_result': {
      const step = ensureStep(thinking, data)
      if (step) step.details.push(`${stringField(data, 'tool_name')}：${stringField(data, 'summary')}`)
      break
    }
    case 'node_retry': {
      const step = ensureStep(thinking, data)
      if (step) {
        step.status = 'in-progress'
        step.details.push(`调用失败：${stringField(data, 'message')}`)
        step.details.push('正在重试')
      }
      const discarded = stringField(data, 'discard_stream_id')
      if (discarded) {
        const streams = { ...next.textStreams }
        delete streams[discarded]
        next.textStreams = streams
        if (thinking.draftStreamId === discarded) {
          thinking.draftStreamId = null
          thinking.draftText = ''
        }
      }
      break
    }
    case 'node_end': {
      const step = ensureStep(thinking, data)
      if (step) {
        step.status = data.status === 'failed' ? 'failed' : 'completed'
        step.duration = numberField(data, 'duration')
        if (data.status === 'failed') appendDetail(thinking, step.stepId, stringField(data, 'message'))
      }
      break
    }
    case 'text_delta': {
      const streamId = stringField(data, 'stream_id')
      const sequence = numberField(data, 'sequence')
      const stepId = stringField(data, 'step_id')
      const key = `${stepId}:${streamId}:${sequence ?? ''}`
      if (next.textSeenKeys.includes(key)) {
        visible = false
        break
      }
      next.textSeenKeys = [...next.textSeenKeys, key]
      next.textStreams = { ...next.textStreams, [streamId]: `${next.textStreams[streamId] ?? ''}${stringField(data, 'delta')}` }
      thinking.draftStreamId = streamId
      thinking.draftText = next.textStreams[streamId] ?? ''
      break
    }
    case 'final_result': {
      thinking.status = 'completed'
      thinking.finalResult = structuredResult(data.data)
      thinking.draftStreamId = null
      thinking.draftText = ''
      next.backendStatus = 'succeeded'
      next.uiState = 'completed'
      releaseTextBuffers(next)
      terminal = true
      break
    }
    case 'interrupt':
      thinking.status = 'waiting_input'
      thinking.waitingInput = { questionId: stringField(data, 'question_id'), prompt: stringField(data, 'message') }
      next.backendStatus = 'waiting_input'
      next.uiState = 'waiting_input'
      terminal = true
      break
    case 'error':
      thinking.status = 'failed'
      thinking.errorMessage = stringField(data, 'message')
      next.errorMessage = thinking.errorMessage
      next.errorCode = 'job_error'
      next.backendStatus = 'failed'
      next.uiState = 'failed'
      releaseTextBuffers(next)
      terminal = true
      break
    case 'canceled':
      thinking.status = 'canceled'
      next.backendStatus = 'canceled'
      next.uiState = 'canceled'
      releaseTextBuffers(next)
      terminal = true
      break
    default:
      visible = false
      break
  }
  return { state: next, visible, terminal }
}

export function reduceJobEvent(state: JobRecord, event: DecodedSseEvent): ReducerResult {
  const accepted = acceptEventId(state, event.id)
  if (!accepted.accepted) return { state, applied: false, duplicate: accepted.duplicate, unknown: false, terminal: false }
  let next: JobRecord = { ...state, ...accepted.cursor }
  if (!event.known) {
    return { state: next, applied: false, duplicate: false, unknown: true, terminal: false }
  }
  if (state.uiState === 'completed' || state.uiState === 'failed' || state.uiState === 'canceled') {
    return { state: next, applied: false, duplicate: false, unknown: false, terminal: false }
  }
  const result = applyKnownEvent(next, event)
  next = result.state
  if (result.visible && event.id !== null) next = { ...next, ...markRendered(next, event.id) }
  return { state: next, applied: result.visible, duplicate: false, unknown: false, terminal: result.terminal }
}

export function seedJobFromPhase(
  jobId: string,
  sessionId: string,
  phase: { status: string; elapsedSeconds: number; lastEventId: number; events: Array<Record<string, unknown>> },
): JobRecord {
  const status: BackendJobStatus = phase.status === 'queued' || phase.status === 'running' || phase.status === 'waiting_input' || phase.status === 'succeeded' || phase.status === 'failed' || phase.status === 'canceled' ? phase.status : 'running'
  let state = createJobRecord(jobId, sessionId, status, 0)
  state = { ...state, thinking: createThinking(status === 'waiting_input' ? 'waiting_input' : status === 'succeeded' ? 'completed' : status === 'failed' ? 'failed' : status === 'canceled' ? 'canceled' : 'active', phase.elapsedSeconds) }
  for (const item of phase.events) {
    const eventId = typeof item.event_id === 'number' ? item.event_id : null
    const type = typeof item.type === 'string' ? item.type : ''
    if (!type) continue
    const decoded: DecodedSseEvent = { event: type, id: eventId, data: item as PublicEvent, known: true }
    const result = reduceJobEvent(state, decoded)
    state = result.state
  }
  const cursor = createEventCursor(phase.lastEventId)
  return {
    ...state,
    ...cursor,
    renderedEventId: phase.lastEventId,
    backendStatus: status,
    uiState: status === 'queued' ? 'queued' : status === 'running' ? 'running' : status === 'waiting_input' ? 'waiting_input' : status === 'succeeded' ? 'completed' : status,
  }
}
