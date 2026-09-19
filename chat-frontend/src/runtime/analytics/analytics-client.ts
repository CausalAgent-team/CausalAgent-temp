import { createIdempotencyKey } from '../jobs/idempotency'

/** 公开预览页面标识；取值必须与后端事件目录登记的一致。 */
export type PreviewPageId = 'home'

/** 公开预览示例标识；取值必须与后端事件目录登记的一致。 */
export type PreviewDemoKey = 'overview' | 'report' | 'graph'

export type PublicPreviewEventName =
  | 'analytics.public_preview.view'
  | 'analytics.public_preview.demo_open'
  | 'analytics.public_preview.send_click'
  | 'analytics.auth.panel_open'

export interface PublicPreviewEvent {
  event: PublicPreviewEventName
  page: PreviewPageId
  demo_key?: PreviewDemoKey
}

const ENDPOINT = '/api/analytics/events'
const VISITOR_KEY = 'causalagent.analytics.visitor'
const DEDUPE_PREFIX = 'causalagent.analytics.sent:'

/*
 * 同一浏览器会话里，页面展示、示例打开和登录面板打开只上报一次；
 * 发送点击是真实用户动作，每次都记录，失败也不补发。
 */
const ONCE_PER_SESSION: ReadonlySet<PublicPreviewEventName> = new Set([
  'analytics.public_preview.view',
  'analytics.public_preview.demo_open',
  'analytics.auth.panel_open',
])

type KeyValueStore = Pick<Storage, 'getItem' | 'setItem'>

export interface AnalyticsClientOptions {
  /** 保存匿名浏览器标识的存储；它只代表可重置的匿名身份。 */
  visitorStore?: KeyValueStore | null
  /** 保存会话级去重标记的存储。 */
  dedupeStore?: KeyValueStore | null
  send?: (body: string) => void
  createVisitorId?: () => string
}

export interface AnalyticsClient {
  track(event: PublicPreviewEvent): void
}

function safeStorage(kind: 'localStorage' | 'sessionStorage'): KeyValueStore | null {
  try {
    return globalThis[kind] ?? null
  } catch {
    return null
  }
}

function sendWithBeacon(body: string): void {
  const navigatorApi = globalThis.navigator
  const beacon = navigatorApi?.sendBeacon
  if (typeof beacon === 'function') {
    try {
      if (beacon.call(navigatorApi, ENDPOINT, new Blob([body], { type: 'application/json' }))) return
    } catch {
      // 浏览器拒绝 sendBeacon 时继续走 fetch 兜底。
    }
  }
  void fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
    credentials: 'same-origin',
  }).catch(() => undefined)
}

function dedupeKey(event: PublicPreviewEvent): string {
  return DEDUPE_PREFIX + event.event + ':' + event.page + ':' + (event.demo_key ?? '')
}

export function createAnalyticsClient(options: AnalyticsClientOptions = {}): AnalyticsClient {
  const visitorStore = options.visitorStore ?? null
  const dedupeStore = options.dedupeStore ?? null
  const send = options.send ?? sendWithBeacon
  const createVisitorId = options.createVisitorId ?? createIdempotencyKey
  const recorded = new Set<string>()
  let visitorId: string | null | undefined

  function resolveVisitorId(): string | null {
    if (visitorId !== undefined) return visitorId
    try {
      const stored = visitorStore?.getItem(VISITOR_KEY)
      visitorId = stored?.trim() ? stored : createVisitorId()
      visitorStore?.setItem(VISITOR_KEY, visitorId)
    } catch {
      // 统计标识不可用时放弃上报，页面功能不受影响。
      visitorId = null
    }
    return visitorId
  }

  function alreadyRecorded(key: string): boolean {
    if (recorded.has(key)) return true
    try {
      if (dedupeStore?.getItem(key)) {
        recorded.add(key)
        return true
      }
    } catch {
      // 读不到会话存储时只依赖内存去重。
    }
    return false
  }

  function markRecorded(key: string): void {
    recorded.add(key)
    try {
      dedupeStore?.setItem(key, '1')
    } catch {
      // 会话存储不可写时只保留内存去重。
    }
  }

  return {
    track(event: PublicPreviewEvent): void {
      if (ONCE_PER_SESSION.has(event.event)) {
        const key = dedupeKey(event)
        if (alreadyRecorded(key)) return
        markRecorded(key)
      }
      const id = resolveVisitorId()
      if (!id) return
      send(JSON.stringify({ visitor_id: id, events: [event] }))
    },
  }
}

const defaultClient = createAnalyticsClient({
  visitorStore: safeStorage('localStorage'),
  dedupeStore: safeStorage('sessionStorage'),
})

/** 上报一条公开预览事件；统计失败不会影响页面和登录流程。 */
export function trackPublicPreviewEvent(event: PublicPreviewEvent): void {
  defaultClient.track(event)
}
