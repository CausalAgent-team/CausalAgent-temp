<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from './api/client'
import { isApiError } from './api/errors'
import AuthPanel from './components/AuthPanel.vue'
import ChatWorkspace from './components/ChatWorkspace.vue'
import { ensureMarkedLoaded } from './renderers/markdown-adapter'
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
const notice = ref('')
const appReady = ref(false)
const next = new URLSearchParams(globalThis.location.search).get('next')
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
  try {
    const redirectTo = await auth.login(username, password, next)
    const hasLoginWarning = auth.warningCode === 'last_login_record_failed'
    if (hasLoginWarning) showNotice(textForWarning())
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
  try {
    await auth.register(username, password)
    authError.value = '注册成功，请登录。'
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
}

onMounted(async () => {
  await ensureMarkedLoaded()
  const loggedIn = await auth.check()
  if (loggedIn) await loadWorkspace()
  appReady.value = true
})

onBeforeUnmount(() => {
  if (noticeTimer !== null) globalThis.clearTimeout(noticeTimer)
  if (redirectTimer !== null) globalThis.clearTimeout(redirectTimer)
})
</script>

<template>
  <div v-if="!appReady || auth.phase === 'checking'" class="app-loading">加载中...</div>
  <AuthPanel v-else-if="!auth.isAuthenticated" :busy="authBusy" :error="authError || auth.error" @login="login" @register="register" />
  <ChatWorkspace v-else :controller="controller" @error="showError" @logout="logout" />
  <div v-if="notice" class="toast" role="alert" @click="notice = ''">{{ notice }}</div>
</template>
