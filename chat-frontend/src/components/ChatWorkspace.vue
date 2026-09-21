<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { api } from '../api/client'
import { isApiError } from '../api/errors'
import { useLocale } from '../i18n/use-locale'
import { chatScrollFollowKey, createChatScrollFollow } from '../runtime/chat/scroll-follow'
import { createIdempotencyKey, retryIdempotent } from '../runtime/jobs/idempotency'
import { JobController } from '../runtime/jobs/job-controller'
import { sessionHref, settingsHref, workspaceHref } from '../runtime/navigation/app-route'
import type { DashboardRoute } from '../runtime/navigation/app-route'
import { useAuthStore } from '../stores/auth.store'
import { useComposerStore } from '../stores/composer.store'
import { useFilesStore } from '../stores/files.store'
import { useJobsStore } from '../stores/jobs.store'
import { useSessionsStore } from '../stores/sessions.store'
import type { JobRecord } from '../types/domain'
import Composer from './Composer.vue'
import MessageTimeline from './MessageTimeline.vue'
import SettingsDialog from './SettingsDialog.vue'

const props = defineProps<{ controller: JobController; route: DashboardRoute }>()
const emit = defineEmits<{
  error: [error: unknown, fallback: string]
  logout: []
  navigate: [path: string]
}>()
const { text } = useLocale()
const auth = useAuthStore()
const sessions = useSessionsStore()
const files = useFilesStore()
const jobs = useJobsStore()
const composer = useComposerStore()

const sidebarOpen = ref(false)
const userMenuOpen = ref(false)
const editingSessionId = ref<string | null>(null)
const editingTitle = ref('')
const conversationArea = ref<HTMLElement | null>(null)
const scrollFollow = createChatScrollFollow()
const activeJob = computed<JobRecord | null>(() => sessions.currentId ? jobs.activeForSession(sessions.currentId) : null)
const settingsOpen = computed(() => props.route.view === 'settings')
const canOpenAdmin = computed(() => auth.hasPermission('admin.access'))
const canOpenRagEval = computed(() => auth.hasPermission('rag_eval.access'))

provide(chatScrollFollowKey, scrollFollow)

/* URL 是当前会话的唯一来源：地址变化时加载对应会话。 */
watch(
  () => props.route.sessionId,
  (sessionId) => {
    if (!sessionId || sessions.currentId === sessionId) return
    void loadSession(sessionId)
  },
  { immediate: true },
)

async function jumpToLatest(): Promise<void> {
  await nextTick()
  scrollFollow.resetToLatest()
}

onMounted(() => scrollFollow.attach(conversationArea.value))
onBeforeUnmount(() => scrollFollow.detach())

function report(error: unknown, fallback: string): void {
  if (isApiError(error) && error.status === 401) {
    auth.handleUnauthorized()
    props.controller.stopAll()
  }
  emit('error', error, fallback)
}

async function loadSession(sessionId: string): Promise<void> {
  try {
    await sessions.select(sessionId)
    if (sessions.currentId !== sessionId) return
    const active = await api.activeJobs(sessionId)
    if (sessions.currentId !== sessionId) return
    /* 只有仍在执行的 Job 需要运行态记录；已结束的历史阶段由消息自带的 thinking_after 渲染。 */
    const activeJobIds = new Set((active.jobs ?? []).map((job) => job.job_id))
    for (const message of sessions.messages) {
      const phase = message.thinkingAfter
      if (phase?.analysisJobId && activeJobIds.has(phase.analysisJobId)) jobs.seedPhase(sessionId, phase)
    }
    for (const job of active.jobs ?? []) {
      const record = jobs.observeActive(job)
      if (record.uiState !== 'waiting_input') void props.controller.subscribe(record.jobId).catch((error: unknown) => report(error, '恢复任务订阅失败。'))
    }
    await jumpToLatest()
  } catch (error) {
    report(error, '加载会话失败。')
  }
}

/* 打开会话时先更新地址，再加载内容，浏览器前进后退都能回到同一会话。 */
async function openSession(sessionId: string): Promise<void> {
  sidebarOpen.value = false
  emit('navigate', sessionHref(sessionId, globalThis.location.pathname))
  await loadSession(sessionId)
}

async function createNewSession(): Promise<void> {
  try {
    await sessions.create()
    if (sessions.currentId) {
      emit('navigate', sessionHref(sessions.currentId, globalThis.location.pathname))
    }
    composer.clearAfterSend()
    files.clearSelection()
    sidebarOpen.value = false
    await jumpToLatest()
  } catch (error) {
    report(error, '创建新对话失败。')
  }
}

async function send(): Promise<void> {
  const message = composer.draft.trim()
  if (!message || composer.sending) return
  const existing = activeJob.value
  if (existing && ['queued', 'running', 'canceling'].includes(existing.uiState)) return
  const resumeJob = existing?.uiState === 'waiting_input' ? existing : null
  composer.setSending(true)
  try {
    let sessionId = sessions.currentId
    if (!resumeJob && !sessionId) {
      sessionId = await sessions.create()
      emit('navigate', sessionHref(sessionId, globalThis.location.pathname))
    }
    if (!sessionId) throw new Error('当前没有可用会话。')
    const key = createIdempotencyKey()
    const response = resumeJob
      ? await retryIdempotent(() => api.resumeJob(resumeJob.jobId, resumeJob.thinking.waitingInput?.questionId ?? '', message, key))
      : await retryIdempotent(() => api.createJob(message, sessionId as string, key, composer.selectedFileId, composer.webSearchEnabled))
    if (!response.success || !response.job_id || !response.status) throw new Error(response.error || '任务请求未被接受。')
    const job = jobs.startFromResponse(response.job_id, sessionId, response.status, resumeJob?.resumeEventId ?? 0)
    if (resumeJob) {
      /* 追问开始新阶段：上一阶段的执行记录留在原来的用户消息上，运行态记录从空投影继续。 */
      const frozen = jobs.startResume(job.jobId)
      if (frozen) sessions.freezeThinking(job.jobId, frozen)
    }
    const stillInSubmittedSession = sessions.currentId === sessionId
    if (stillInSubmittedSession) {
      sessions.appendUserMessage(message, response.job_id)
      composer.draft = ''
    }
    composer.setSending(false)
    if (!resumeJob && stillInSubmittedSession) {
      files.clearSelection()
      composer.setSelectedFile(null)
    }
    void props.controller.subscribe(response.job_id).catch((error: unknown) => report(error, '任务事件订阅失败。'))
    void sessions.loadList().catch(() => undefined)
  } catch (error) {
    composer.restoreDraft(message)
    report(error, '发送消息时发生网络错误。')
  } finally {
    composer.setSending(false)
  }
}

async function cancel(): Promise<void> {
  const job = activeJob.value
  if (!job) return
  try {
    await props.controller.cancel(job.jobId)
    await sessions.loadList().catch(() => undefined)
  } catch (error) {
    const reconciled = isApiError(error) && error.status === 409 && error.code === 'job_state_conflict'
    if (!reconciled) report(error, '取消任务失败，请稍后重试。')
  }
}

async function upload(file: File): Promise<void> {
  try {
    const uploaded = await files.upload(file)
    composer.setSelectedFile(uploaded.userFileId)
  } catch (error) {
    report(error, '文件上传失败。')
  }
}

async function deleteFile(fileId: number): Promise<void> {
  if (!globalThis.confirm(text.value.deleteFileConfirm)) return
  try {
    await files.remove(fileId)
    if (composer.selectedFileId === fileId) composer.setSelectedFile(null)
  } catch (error) {
    report(error, '删除文件失败。')
  }
}

function beginRename(id: string, title: string): void {
  editingSessionId.value = id
  editingTitle.value = title
}

async function finishRename(): Promise<void> {
  const id = editingSessionId.value
  const title = editingTitle.value.trim()
  editingSessionId.value = null
  if (!id || !title) return
  try {
    await sessions.rename(id, title)
  } catch (error) {
    report(error, '更新标题失败。')
  }
}

async function deleteSession(id: string): Promise<void> {
  if (!globalThis.confirm(text.value.deleteSessionConfirm)) return
  try {
    props.controller.stopAll()
    await sessions.remove(id)
    if (!sessions.currentId) {
      composer.clearAfterSend()
      files.clearSelection()
      emit('navigate', workspaceHref(globalThis.location.pathname))
    }
  } catch (error) {
    report(error, '删除会话失败。')
  }
}

function selectFile(fileId: number): void {
  files.select(fileId)
  composer.setSelectedFile(fileId)
}

function openAdmin(): void {
  globalThis.location.assign('/admin/database')
}

function openRagEval(): void {
  globalThis.location.assign('/rag-eval')
}

function openSettings(): void {
  emit('navigate', settingsHref(globalThis.location.pathname))
}

function closeSettings(): void {
  const currentId = sessions.currentId
  emit(
    'navigate',
    currentId ? sessionHref(currentId, globalThis.location.pathname) : workspaceHref(globalThis.location.pathname),
  )
}
</script>

<template>
  <div class="workspace" :class="{ 'sidebar-open': sidebarOpen }">
    <button class="menu-button" type="button" aria-label="打开菜单" @click="sidebarOpen = !sidebarOpen">☰</button>
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="sidebar-header">
        <h3>CausalAgent</h3>
        <button class="icon-button" type="button" aria-label="关闭菜单" @click="sidebarOpen = false">☰</button>
      </div>
      <div class="sidebar-content">
        <div class="sidebar-primary-wrap">
          <button class="sidebar-primary" type="button" @click="createNewSession">{{ text.newChat }}</button>
        </div>
        <div class="sidebar-section history-section">
          <p v-if="!sessions.items.length" class="sidebar-empty">{{ text.noHistory }}</p>
          <div v-for="session in sessions.items" :key="session.id" class="sidebar-item session-item" :class="{ selected: session.id === sessions.currentId }">
            <button class="sidebar-item-main" type="button" @click="openSession(session.id)">
              <span class="sidebar-time">{{ session.lastTime }}</span>
              <span v-if="editingSessionId !== session.id" class="sidebar-preview" :title="session.preview">{{ session.preview }}</span>
              <input v-else v-model="editingTitle" class="title-input" @click.stop @keydown.enter.prevent="finishRename" @keydown.esc="editingSessionId = null" @blur="finishRename" />
            </button>
            <div class="sidebar-item-actions">
              <button type="button" :aria-label="`编辑 ${session.preview}`" @click.stop="beginRename(session.id, session.preview)">✎</button>
              <button type="button" :aria-label="`${text.delete} ${session.preview}`" @click.stop="deleteSession(session.id)">×</button>
            </div>
          </div>
        </div>
        <div class="sidebar-section files-section">
          <h2>{{ text.fileList }}</h2>
          <p v-if="!files.items.length" class="sidebar-empty">{{ text.noFiles }}</p>
          <div v-for="file in files.items" :key="file.userFileId" class="sidebar-item file-item" :class="{ selected: file.userFileId === composer.selectedFileId }">
            <button class="sidebar-item-main" type="button" @click="selectFile(file.userFileId)">
              <span class="sidebar-time">{{ file.uploadedAt?.slice(0, 10) }}</span>
              <span class="sidebar-preview" :title="file.filename">{{ file.filename }}</span>
            </button>
            <button class="sidebar-delete" type="button" :aria-label="`${text.delete} ${file.filename}`" @click.stop="deleteFile(file.userFileId)">×</button>
          </div>
        </div>
      </div>
      <div class="sidebar-footer">
        <button class="secondary-button" type="button" @click="openSettings">{{ text.settings }}</button>
        <button class="avatar-button" type="button" :aria-expanded="userMenuOpen" @click="userMenuOpen = !userMenuOpen">{{ auth.username?.charAt(0).toUpperCase() }}</button>
      </div>
      <div v-if="userMenuOpen" class="user-menu" role="dialog" aria-modal="true" :aria-label="text.userInfo">
        <h3>{{ text.userInfo }}</h3>
        <div class="user-info-content">{{ text.accountPrefix }}{{ auth.username }}</div>
        <div class="popup-button-container">
          <button v-if="canOpenAdmin" class="admin-button" type="button" @click="openAdmin">{{ text.adminPortal }}</button>
          <button v-if="canOpenRagEval" class="admin-button" type="button" @click="openRagEval">{{ text.ragEvalPortal }}</button>
          <button class="logout-button" type="button" @click="emit('logout')">{{ text.logout }}</button>
          <button class="close-button" type="button" @click="userMenuOpen = false">{{ text.close }}</button>
        </div>
      </div>
    </aside>
    <main class="main-container" :class="sessions.messages.length ? 'is-conversation' : 'is-new-chat'">
      <section ref="conversationArea" class="conversation-area" @scroll.passive="scrollFollow.handleScroll()">
        <MessageTimeline :messages="sessions.messages" />
      </section>
      <div class="new-chat-stage">
        <div class="welcome-panel">
          <h2>{{ text.welcomeTitle }}</h2>
          <p>{{ text.welcomeDescription }}</p>
        </div>
        <Composer
          :draft="composer.draft"
          :web-search-enabled="composer.webSearchEnabled"
          :selected-file="files.selected"
          :active-job="activeJob"
          :sending="composer.sending"
          @update:draft="composer.setDraft"
          @update:web-search="composer.setWebSearch"
          @send="send"
          @cancel="cancel"
          @upload="upload"
          @clear-file="files.clearSelection(); composer.setSelectedFile(null)"
        />
      </div>
    </main>
    <SettingsDialog :open="settingsOpen" @close="closeSettings" />
  </div>
</template>
