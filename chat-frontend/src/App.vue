<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from './api/client'
import { isApiError } from './api/errors'
import AuthPanel from './components/AuthPanel.vue'
import ChatWorkspace from './components/ChatWorkspace.vue'
import PublicPreview from './components/PublicPreview.vue'
import { PUBLIC_PREVIEW_PAGE_ID } from './preview/public-preview-data'
import { ensureMarkedLoaded } from './renderers/markdown-adapter'
import type { PreviewDemoKey } from './runtime/analytics/analytics-client'
import { trackPublicPreviewEvent } from './runtime/analytics/analytics-client'
import { JobController } from './runtime/jobs/job-controller'
import { useLocale } from './i18n/use-locale'
import { useAuthStore } from './stores/auth.store'
import { useComposerStore } from './stores/composer.store'
import { useFilesStore } from './stores/files.store'
import { useJobsStore } from './stores/jobs.store'
import { useSessionsStore } from './stores/sessions.store'

const auth = useAuthStore()
const sessions = useSessionsStore()
const files = useFilesStore()
const jobs = useJobsStore()
const composer = useComposerStore()
const { text } = useLocale()
const controller = new JobController(jobs)
const authBusy = ref(false)
const authError = ref<string | null>(null)
const authNotice = ref<string | null>(null)
const notice = ref('')
const appReady = ref(false)
const next = new URLSearchParams(globalThis.location.search).get('next')
const authPanelOpen = ref(false)
const activeDemoKey = ref<PreviewDemoKey>('overview')
const DRAFT_STORAGE_KEY = 'causalagent.preview.draft'
let noticeTimer: number | null = null
let redirectTimer: number | null = null

function showNotice(message: string, duration = 3000): void {
  notice.value = message
  if (noticeTimer !== null) globalThis.clearTimeout(noticeTimer)
  noticeTimer = globalThis.setTimeout(() => {
    notice.value = ''
    noticeTimer = null
  }, duration)
}

function showError(error: unknown, fallback: string): void {
  if (isApiError(error) && error.status === 401) auth.handleUnauthorized()
  showNotice(error instanceof Error ? error.message : fallback)
}

/* 未登录时的草稿只保存在浏览器：内存里的 Composer store 加会话存储，不写入后端。 */
function persistDraft(value: string): void {
  composer.setDraft(value)
  try {
    if (value) globalThis.sessionStorage.setItem(DRAFT_STORAGE_KEY, value)
    else globalThis.sessionStorage.removeItem(DRAFT_STORAGE_KEY)
  } catch {
    // 浏览器禁用会话存储时只保留内存草稿。
  }
}

function restoreDraft(): void {
  if (composer.draft.trim()) return
  try {
    const stored = globalThis.sessionStorage.getItem(DRAFT_STORAGE_KEY)
    if (stored) composer.setDraft(stored)
  } catch {
    // 读不到会话存储时保持空草稿。
  }
}

function clearStoredDraft(): void {
  try {
    globalThis.sessionStorage.removeItem(DRAFT_STORAGE_KEY)
  } catch {
    // 没有可清理的会话存储时不需要处理。
  }
}

function openAuthPanel(): void {
  trackPublicPreviewEvent({ event: 'analytics.auth.panel_open', page: PUBLIC_PREVIEW_PAGE_ID })
  authError.value = null
  authNotice.value = null
  authPanelOpen.value = true
}

function requestAuth(action: 'login' | 'register' | 'send' | 'upload' | 'new-chat'): void {
  if (action === 'send') {
    trackPublicPreviewEvent({
      event: 'analytics.public_preview.send_click',
      page: PUBLIC_PREVIEW_PAGE_ID,
      demo_key: activeDemoKey.value,
    })
  }
  openAuthPanel()
}

function openPreviewDemo(key: PreviewDemoKey): void {
  activeDemoKey.value = key
  trackPublicPreviewEvent({
    event: 'analytics.public_preview.demo_open',
    page: PUBLIC_PREVIEW_PAGE_ID,
    demo_key: key,
  })
}

async function loadWorkspace(): Promise<void> {
  await Promise.all([
    sessions.loadList().catch((error: unknown) => showError(error, '加载历史记录失败。')),
    files.load().catch((error: unknown) => showError(error, '加载文件列表失败。')),
  ])
  try {
    const active = await api.activeJobs()
    const latest = active.jobs?.at(-1)
    if (latest && !sessions.currentId) {
      await sessions.select(latest.session_id)
      for (const message of sessions.messages) if (message.thinkingAfter) jobs.seedPhase(latest.session_id, message.thinkingAfter)
    }
    for (const job of active.jobs ?? []) {
      const record = jobs.observeActive(job)
      if (record.uiState !== 'waiting_input') void controller.subscribe(record.jobId).catch((error: unknown) => showError(error, '恢复任务订阅失败。'))
    }
  } catch (error) {
    showError(error, '恢复活动任务失败。')
  }
}

async function login(username: string, password: string): Promise<void> {
  authBusy.value = true
  authError.value = null
  authNotice.value = null
  try {
    const redirectTo = await auth.login(username, password, next)
    const hasLoginWarning = auth.warningCode === 'last_login_record_failed'
    if (hasLoginWarning) showNotice(textForWarning())
    authPanelOpen.value = false
    // 草稿已经回到正式 Composer，会话存储里的副本不再需要。
    clearStoredDraft()
    if (redirectTo) {
      if (hasLoginWarning) {
        redirectTimer = globalThis.setTimeout(() => globalThis.location.assign(redirectTo), 3000)
      } else {
        globalThis.location.assign(redirectTo)
      }
      return
    }
    await loadWorkspace()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : '登录失败，请稍后再试。'
  } finally {
    authBusy.value = false
  }
}

function textForWarning(): string {
  return text.value.lastLoginWarning
}

async function register(username: string, password: string, confirmPassword: string): Promise<void> {
  if (password !== confirmPassword) {
    authError.value = '两次输入的密码不匹配。'
    return
  }
  authBusy.value = true
  authError.value = null
  authNotice.value = null
  try {
    await auth.register(username, password)
    authNotice.value = text.value.registerSuccess
  } catch (error) {
    authError.value = error instanceof Error ? error.message : '注册失败，请稍后再试。'
  } finally {
    authBusy.value = false
  }
}

async function logout(): Promise<void> {
  try {
    await auth.logout()
  } catch (error) {
    showError(error, '退出登录失败，请稍后再试。')
    return
  }
  controller.stopAll()
  sessions.reset()
  files.reset()
  jobs.reset()
  composer.reset()
  authPanelOpen.value = false
}

onMounted(async () => {
  await ensureMarkedLoaded()
  const loggedIn = await auth.check()
  if (loggedIn) {
    await loadWorkspace()
  } else {
    restoreDraft()
    trackPublicPreviewEvent({
      event: 'analytics.public_preview.view',
      page: PUBLIC_PREVIEW_PAGE_ID,
      demo_key: activeDemoKey.value,
    })
  }
  appReady.value = true
})

onBeforeUnmount(() => {
  if (noticeTimer !== null) globalThis.clearTimeout(noticeTimer)
  if (redirectTimer !== null) globalThis.clearTimeout(redirectTimer)
})
</script>

<template>
  <div v-if="!appReady || auth.phase === 'checking'" class="app-loading">加载中...</div>
  <template v-else-if="!auth.isAuthenticated">
    <PublicPreview
      :draft="composer.draft"
      :web-search-enabled="composer.webSearchEnabled"
      :demo-key="activeDemoKey"
      @update:draft="persistDraft"
      @update:web-search="composer.setWebSearch"
      @request-auth="requestAuth"
      @demo-open="openPreviewDemo"
    />
    <AuthPanel
      v-if="authPanelOpen"
      closeable
      :busy="authBusy"
      :error="authError || auth.error"
      :notice="authNotice"
      @login="login"
      @register="register"
      @close="authPanelOpen = false"
    />
  </template>
  <ChatWorkspace v-else :controller="controller" @error="showError" @logout="logout" />
  <div v-if="notice" class="toast" role="alert" @click="notice = ''">{{ notice }}</div>
</template>
