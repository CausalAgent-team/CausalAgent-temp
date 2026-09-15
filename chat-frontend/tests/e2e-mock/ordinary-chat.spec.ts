import { expect, test } from '@playwright/test'

function json(payload: unknown, status = 200): { status: number; contentType: string; body: string } {
  return { status, contentType: 'application/json', body: JSON.stringify(payload) }
}

test('mock ordinary chat login, job creation and fetch SSE terminal event', async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (!url.pathname.startsWith('/api/')) {
      await route.fallback()
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
          'id: 1\nevent: node_start\ndata: {"type":"node_start","step_id":"s1","node_name":"mock","title":"Mock step"}\n\n',
          'id: 2\nevent: node_end\ndata: {"type":"node_end","step_id":"s1","node_name":"mock","title":"Mock step","duration":0.1,"status":"completed"}\n\n',
          'id: 3\nevent: final_result\ndata: {"type":"final_result","data":{"type":"text","summary":"done from mock"}}\n\n',
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

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()
  await page.getByLabel('用户名').fill('alice')
  await page.getByLabel('密码').fill('secret')
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page.getByRole('button', { name: '新建对话' })).toBeVisible()
  await page.locator('textarea[placeholder="输入消息..."]').fill('请分析这个数据')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.getByText('请分析这个数据')).toBeVisible()
  await expect(page.getByText('done from mock')).toBeVisible()
})
