import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

function json(payload: unknown, status = 200): { status: number; contentType: string; body: string } {
  return { status, contentType: 'application/json', body: JSON.stringify(payload) }
}

interface RecordedTraffic {
  businessPaths: string[]
  analyticsEvents: Array<Record<string, unknown>>
}

async function installApiMocks(page: Page): Promise<RecordedTraffic> {
  const traffic: RecordedTraffic = { businessPaths: [], analyticsEvents: [] }

  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname
    if (!pathname.startsWith('/api/')) return
    if (pathname === '/api/analytics/events' || pathname === '/api/check_auth') return
    traffic.businessPaths.push(pathname)
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (!url.pathname.startsWith('/api/')) {
      await route.fallback()
      return
    }
    if (url.pathname === '/api/analytics/events') {
      const body = request.postDataJSON() as { events?: Array<Record<string, unknown>> }
      traffic.analyticsEvents.push(...(body.events ?? []))
      await route.fulfill({ ...json({ success: true, accepted: body.events?.length ?? 0 }, 202) })
      return
    }
    if (url.pathname === '/api/check_auth') {
      await route.fulfill({ ...json({ isLoggedIn: false }) })
      return
    }
    if (url.pathname === '/api/login') {
      await route.fulfill({ ...json({ success: true, username: 'alice', role: 'user', csrf_token: 'csrf-token' }) })
      return
    }
    if (url.pathname === '/api/sessions') {
      await route.fulfill({ ...json([]) })
      return
    }
    if (url.pathname === '/api/files') {
      await route.fulfill({ ...json([]) })
      return
    }
    if (url.pathname === '/api/agent/jobs/active') {
      await route.fulfill({ ...json({ success: true, jobs: [] }) })
      return
    }
    if (url.pathname === '/api/new_chat') {
      await route.fulfill({ ...json({ success: true, new_session_id: 'session-1' }) })
      return
    }
    if (url.pathname === '/api/agent/jobs' && request.method() === 'POST') {
      await route.fulfill({ ...json({ success: true, job_id: 'job-1', status: 'queued', existing: false }, 202) })
      return
    }
    if (url.pathname === '/api/agent/jobs/job-1/events') {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'id: 1\nevent: node_start\ndata: {"type":"node_start","step_id":"s1","node_name":"deep_agent","title":"执行 Deep Agent 分析"}\n\n',
          'id: 2\nevent: decision_delta\ndata: {"type":"decision_delta","step_id":"s1","node_name":"deep_agent","title":"执行 Deep Agent 分析","stream_id":"decision-1","sequence":1,"delta":"选择 PC","decision_kind":"algorithm","tool_name":"pc"}\n\n',
          'id: 3\nevent: decision\ndata: {"type":"decision","step_id":"s1","node_name":"deep_agent","title":"执行 Deep Agent 分析","summary":"选择 PC","decision_kind":"algorithm","tool_name":"pc"}\n\n',
          'id: 4\nevent: tool_call_start\ndata: {"type":"tool_call_start","step_id":"s1","node_name":"deep_agent","title":"执行 Deep Agent 分析","tool_name":"pc","argument_keys":["data"]}\n\n',
          'id: 5\nevent: tool_call_result\ndata: {"type":"tool_call_result","step_id":"s1","node_name":"deep_agent","title":"执行 Deep Agent 分析","tool_name":"pc","summary":"算法执行完成","status":"succeeded"}\n\n',
          'id: 6\nevent: text_delta\ndata: {"type":"text_delta","step_id":"s1","stream_id":"answer","sequence":1,"delta":"正在生成报告"}\n\n',
          'id: 7\nevent: node_end\ndata: {"type":"node_end","step_id":"s1","node_name":"deep_agent","title":"执行 Deep Agent 分析","duration":0.1,"status":"completed"}\n\n',
          'id: 8\nevent: final_result\ndata: {"type":"final_result","data":{"type":"text","summary":"done from mock"}}\n\n',
        ].join(''),
      })
      return
    }
    if (url.pathname === '/api/logout') {
      await route.fulfill({ ...json({ success: true }) })
      return
    }
    await route.fulfill({ ...json({ success: true }) })
  })

  return traffic
}

test('anonymous visitors see the public preview without creating any business data', async ({ page }) => {
  const traffic = await installApiMocks(page)

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '把数据交给 Agent，得到可追溯的因果分析' })).toBeVisible()
  await expect(page.locator('.preview-session-item')).toHaveCount(3)
  await expect(page.locator('.auth-card')).toHaveCount(0)

  await page.locator('textarea[placeholder="输入消息..."]').fill('请分析这个数据')
  await page.reload()
  await expect(page.locator('textarea[placeholder="输入消息..."]')).toHaveValue('请分析这个数据')

  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.locator('.auth-card').getByRole('heading', { name: '登录' })).toBeVisible()
  await expect(page.locator('textarea[placeholder="输入消息..."]')).toHaveValue('请分析这个数据')
  expect(traffic.businessPaths).toEqual([])

  const localKeys = await page.evaluate(() => Object.keys(localStorage))
  const sessionKeys = await page.evaluate(() => Object.keys(sessionStorage))
  expect(localKeys).toEqual(['causalagent.analytics.visitor'])
  expect(sessionKeys).toContain('causalagent.preview.draft')

  await expect.poll(() => traffic.analyticsEvents.map((event) => event.event)).toContain('analytics.auth.panel_open')
  const reported = traffic.analyticsEvents.map((event) => event.event)
  expect(reported.filter((name) => name === 'analytics.public_preview.view')).toHaveLength(1)
  expect(reported).toContain('analytics.public_preview.send_click')
})

test('mock ordinary chat login, job creation and fetch SSE terminal event', async ({ page }) => {
  const traffic = await installApiMocks(page)

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '把数据交给 Agent，得到可追溯的因果分析' })).toBeVisible()
  await page.locator('textarea[placeholder="输入消息..."]').fill('请分析这个数据')
  await page.getByRole('button', { name: '发送' }).click()

  const authCard = page.locator('.auth-card')
  await expect(authCard.getByRole('heading', { name: '登录' })).toBeVisible()
  expect(traffic.businessPaths).toEqual([])
  await authCard.getByLabel('用户名').fill('alice')
  await authCard.getByLabel('密码').fill('secret')
  await authCard.getByRole('button', { name: '登录' }).click()

  await expect(page.getByRole('button', { name: '新建对话' })).toBeVisible()
  await expect(page.locator('textarea[placeholder="输入消息..."]')).toHaveValue('请分析这个数据')

  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.getByText('请分析这个数据')).toBeVisible()
  await expect(page.getByText('done from mock')).toBeVisible()
  expect(traffic.businessPaths).toContain('/api/new_chat')
  expect(traffic.businessPaths).toContain('/api/agent/jobs')

  await page.getByRole('button', { name: /执行 Deep Agent 分析/ }).click()
  await expect(page.getByText('算法决策：选择 PC')).toBeVisible()
  await expect(page.getByText('调用工具：pc（参数字段：data）')).toBeVisible()
  await expect(page.getByText('pc：算法执行完成')).toBeVisible()
})
