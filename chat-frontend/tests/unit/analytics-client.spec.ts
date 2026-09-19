import { describe, expect, it, vi } from 'vitest'
import { createAnalyticsClient } from '../../src/runtime/analytics/analytics-client'

const VISITOR_ID = '2f1c9d5e-0c0f-4f7a-9c1e-4d9a2b7c5e11'

function memoryStore(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key: string): string | null => values.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      values.set(key, value)
    },
    values,
  }
}

function payloadOf(send: ReturnType<typeof vi.fn>, index: number): Record<string, unknown> {
  const call = send.mock.calls[index]
  if (!call) throw new Error('缺少第 ' + index + ' 次上报')
  return JSON.parse(String(call[0])) as Record<string, unknown>
}

describe('createAnalyticsClient', () => {
  it('reports page views and demo opens once per browser session', () => {
    const send = vi.fn()
    const client = createAnalyticsClient({
      visitorStore: memoryStore(),
      dedupeStore: memoryStore(),
      send,
      createVisitorId: () => VISITOR_ID,
    })

    client.track({ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' })
    client.track({ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' })
    client.track({ event: 'analytics.public_preview.demo_open', page: 'home', demo_key: 'report' })
    client.track({ event: 'analytics.public_preview.demo_open', page: 'home', demo_key: 'report' })
    client.track({ event: 'analytics.public_preview.demo_open', page: 'home', demo_key: 'graph' })
    client.track({ event: 'analytics.auth.panel_open', page: 'home' })
    client.track({ event: 'analytics.auth.panel_open', page: 'home' })

    expect(send).toHaveBeenCalledTimes(4)
    expect(payloadOf(send, 0)).toEqual({
      visitor_id: VISITOR_ID,
      events: [{ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' }],
    })
    expect(payloadOf(send, 2)).toEqual({
      visitor_id: VISITOR_ID,
      events: [{ event: 'analytics.public_preview.demo_open', page: 'home', demo_key: 'graph' }],
    })
    expect(payloadOf(send, 3)).toEqual({
      visitor_id: VISITOR_ID,
      events: [{ event: 'analytics.auth.panel_open', page: 'home' }],
    })
  })

  it('reports every send click with one reusable anonymous identifier', () => {
    const send = vi.fn()
    const visitorStore = memoryStore()
    const createVisitorId = vi.fn(() => VISITOR_ID)
    const client = createAnalyticsClient({
      visitorStore,
      dedupeStore: memoryStore(),
      send,
      createVisitorId,
    })

    client.track({ event: 'analytics.public_preview.send_click', page: 'home', demo_key: 'graph' })
    client.track({ event: 'analytics.public_preview.send_click', page: 'home', demo_key: 'graph' })

    expect(send).toHaveBeenCalledTimes(2)
    expect(createVisitorId).toHaveBeenCalledTimes(1)
    expect(visitorStore.values.get('causalagent.analytics.visitor')).toBe(VISITOR_ID)
  })

  it('reuses a stored identifier instead of creating a new one', () => {
    const send = vi.fn()
    const createVisitorId = vi.fn(() => 'unused')
    const client = createAnalyticsClient({
      visitorStore: memoryStore({ 'causalagent.analytics.visitor': VISITOR_ID }),
      dedupeStore: memoryStore(),
      send,
      createVisitorId,
    })

    client.track({ event: 'analytics.public_preview.send_click', page: 'home', demo_key: 'overview' })

    expect(createVisitorId).not.toHaveBeenCalled()
    expect(payloadOf(send, 0).visitor_id).toBe(VISITOR_ID)
  })

  it('drops reports instead of throwing when storage or identifiers are unavailable', () => {
    const send = vi.fn()
    const brokenStore = {
      getItem: (): string | null => {
        throw new Error('storage disabled')
      },
      setItem: (): void => {
        throw new Error('storage disabled')
      },
    }
    const client = createAnalyticsClient({
      visitorStore: brokenStore,
      dedupeStore: brokenStore,
      send,
      createVisitorId: () => VISITOR_ID,
    })

    expect(() => client.track({ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' })).not.toThrow()
    expect(send).not.toHaveBeenCalled()
  })

  it('still dedupes in memory when the session store cannot be written', () => {
    const send = vi.fn()
    const readOnlyStore = {
      getItem: (): string | null => null,
      setItem: (): void => {
        throw new Error('read only')
      },
    }
    const client = createAnalyticsClient({
      visitorStore: memoryStore(),
      dedupeStore: readOnlyStore,
      send,
      createVisitorId: () => VISITOR_ID,
    })

    client.track({ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' })
    client.track({ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' })

    expect(send).toHaveBeenCalledTimes(1)
  })

  it('uses sendBeacon without waiting for a response', () => {
    const sendBeacon = vi.fn(() => true)
    const fetchMock = vi.fn()
    vi.stubGlobal('navigator', { sendBeacon })
    vi.stubGlobal('fetch', fetchMock)
    const client = createAnalyticsClient({
      visitorStore: memoryStore(),
      dedupeStore: memoryStore(),
      createVisitorId: () => VISITOR_ID,
    })

    client.track({ event: 'analytics.public_preview.view', page: 'home', demo_key: 'overview' })

    expect(sendBeacon).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('falls back to a keepalive fetch when sendBeacon refuses the request', () => {
    const sendBeacon = vi.fn(() => false)
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
    fetchMock.mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal('navigator', { sendBeacon })
    vi.stubGlobal('fetch', fetchMock)
    const client = createAnalyticsClient({
      visitorStore: memoryStore(),
      dedupeStore: memoryStore(),
      createVisitorId: () => VISITOR_ID,
    })

    client.track({ event: 'analytics.public_preview.send_click', page: 'home', demo_key: 'overview' })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const init = fetchMock.mock.calls[0]?.[1]
    expect(init).toMatchObject({ method: 'POST', keepalive: true, credentials: 'same-origin' })
  })
})
