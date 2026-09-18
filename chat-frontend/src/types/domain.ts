export type Locale = 'zh' | 'en'

export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

export interface Reference {
  title: string
  url: string
}

export interface CausalGraphData {
  nodes: Array<Record<string, unknown>>
  edges: Array<Record<string, unknown>>
}

export interface StructuredMessage {
  type: string
  summary?: string
  layout?: string
  data?: unknown
  references?: Reference[]
  [key: string]: unknown
}

export type MessageText = string | StructuredMessage

export interface ExecutionPhase {
  phaseSequence: number
  status: string
  elapsedSeconds: number
  lastEventId: number
  analysisJobId?: string
  analysisJobInputId?: number
  events: Array<Record<string, unknown>>
}

export interface ChatMessage {
  localId: string
  sender: 'user' | 'ai'
  text: MessageText
  analysisJobId?: string
  analysisJobInputId?: number
  references?: Reference[]
  thinkingAfter?: ExecutionPhase
}

export interface SessionSummary {
  id: string
  preview: string
  lastTime: string
}

export interface UserFile {
  id: number
  userFileId: number
  filename: string
  mimeType: string
  fileSize: number
  uploadedAt: string | null
  lastAccessedAt: string | null
  accessCount: number
}

export type BackendJobStatus = 'queued' | 'running' | 'waiting_input' | 'succeeded' | 'failed' | 'canceled'
export type JobConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'
export type JobUiState = 'idle' | 'creating' | 'queued' | 'running' | 'waiting_input' | 'resuming' | 'canceling' | 'completed' | 'failed' | 'canceled'

export interface WaitingInput {
  questionId: string
  prompt: string
}

export type DetailTone = 'default' | 'error' | 'retry'

export interface StepTextDetail {
  kind: 'text'
  text: string
  tone: DetailTone
}

/**
 * 一次工具调用的公开决策。`text` 是已经接收的完整公开说明（不含前缀），
 * 展示层按码点逐步推进；`pending` 保存同一工具尚未放行的生命周期事件。
 */
export interface StepDecisionDetail {
  kind: 'decision'
  key: string
  decisionKind: string
  toolName: string
  streamId: string | null
  text: string
  complete: boolean
  pending: Array<Record<string, unknown>>
}

export type StepDetail = StepTextDetail | StepDecisionDetail

export interface ThinkingStep {
  stepId: string
  nodeName: string
  title: string
  status: 'in-progress' | 'completed' | 'failed' | 'canceled'
  duration: number | null
  details: StepDetail[]
}

export interface ThinkingProjection {
  status: 'active' | 'completed' | 'waiting_input' | 'failed' | 'canceled'
  startedAt: number
  elapsedSeconds: number
  steps: Record<string, ThinkingStep>
  stepOrder: string[]
  pendingStepEvents: Record<string, Array<Record<string, unknown>>>
  draftStreamId: string | null
  draftText: string
  finalResult: StructuredMessage | null
  errorMessage: string | null
  waitingInput: WaitingInput | null
}

export interface StoredEvent {
  id: number
  type: string
  data: Record<string, unknown>
}

export interface PublicEventBase {
  type: string
  step_id?: string
  node_name?: string
  title?: string
  event_id?: number
  [key: string]: unknown
}

export type PublicEvent = PublicEventBase

export interface JobRecord {
  jobId: string
  sessionId: string
  backendStatus: BackendJobStatus
  uiState: JobUiState
  connection: JobConnectionState
  generation: number
  transportCursor: number
  resumeEventId: number
  renderedEventId: number
  observedLastEventId: number | null
  events: StoredEvent[]
  textSeenKeys: string[]
  textStreams: Record<string, string>
  thinking: ThinkingProjection
  errorMessage: string | null
  errorCode: string | null
  cancelKey: string | null
  cancelInFlight: boolean
}
