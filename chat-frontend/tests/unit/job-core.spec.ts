import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { DecodedSseEvent } from '../../src/api/events.schemas'
import { useJobsStore } from '../../src/stores/jobs.store'
import { createJobRecord, reduceJobEvent } from '../../src/runtime/jobs/event-reducer'

function event(type: string, id: number, fields: Record<string, unknown> = {}, known = true): DecodedSseEvent {
  return { event: type, id, data: { type, ...fields }, known }
}

describe('job reducer and cursor semantics', () => {
  it('advances transport/resume cursor for unknown legal events without visible projection', () => {
    let state = createJobRecord('job-1', 'session-1', 'running')
    const unknown = reduceJobEvent(state, event('future_event', 1, { value: 'kept for transport only' }, false))
    state = unknown.state

    expect(unknown).toMatchObject({ applied: false, unknown: true, duplicate: false })
    expect(state.transportCursor).toBe(1)
    expect(state.resumeEventId).toBe(1)
    expect(state.renderedEventId).toBe(0)
    expect(state.events).toHaveLength(0)
  })

  it('deduplicates repeated IDs and text_delta semantic keys independently', () => {
    let state = createJobRecord('job-1', 'session-1', 'running')
    state = reduceJobEvent(state, event('text_delta', 1, { step_id: 's1', stream_id: 'answer', sequence: 1, delta: 'A' })).state
    const repeatedText = reduceJobEvent(state, event('text_delta', 2, { step_id: 's1', stream_id: 'answer', sequence: 1, delta: 'A-again' }))
    state = repeatedText.state
    const duplicateId = reduceJobEvent(state, event('text_delta', 2, { step_id: 's1', stream_id: 'answer', sequence: 2, delta: 'B' }))

    expect(repeatedText.applied).toBe(false)
    expect(state.transportCursor).toBe(2)
    expect(state.renderedEventId).toBe(1)
    expect(state.textStreams.answer).toBe('A')
    expect(duplicateId.duplicate).toBe(true)
    expect(duplicateId.state.textStreams.answer).toBe('A')
  })

  it('releases raw text buffers after a terminal result while keeping the rendered result', () => {
    let state = createJobRecord('job-1', 'session-1', 'running')
    state = reduceJobEvent(state, event('text_delta', 1, { step_id: 's1', stream_id: 'answer', sequence: 1, delta: 'partial' })).state
    const result = reduceJobEvent(state, event('final_result', 2, { data: { type: 'text', summary: 'done' } }))

    expect(result.terminal).toBe(true)
    expect(result.state.thinking.finalResult).toMatchObject({ type: 'text', summary: 'done' })
    expect(result.state.textSeenKeys).toEqual([])
    expect(result.state.textStreams).toEqual({})
  })

  it('does not mutate a completed job with a later known event', () => {
    let state = createJobRecord('job-1', 'session-1', 'running')
    state = reduceJobEvent(state, event('final_result', 1, { data: { type: 'text', summary: 'done' } })).state
    const lateEvent = reduceJobEvent(state, event('progress', 2, { step_id: 'late', node_name: 'late', title: 'late', summary: 'ignored' }))

    expect(lateEvent.applied).toBe(false)
    expect(lateEvent.state.transportCursor).toBe(2)
    expect(lateEvent.state.thinking.stepOrder).toEqual([])
    expect(lateEvent.state.thinking.finalResult).toMatchObject({ summary: 'done' })
  })

  it('keeps an active endpoint observation separate from the rendered history cursor', () => {
    setActivePinia(createPinia())
    const jobs = useJobsStore()
    jobs.startFromResponse('job-1', 'session-1', 'running', 5)
    jobs.observeActive({ job_id: 'job-1', session_id: 'session-1', status: 'running', last_event_id: 2 })

    expect(jobs.get('job-1')).toMatchObject({
      transportCursor: 5,
      resumeEventId: 5,
      renderedEventId: 5,
      observedLastEventId: 2,
    })
  })
})
