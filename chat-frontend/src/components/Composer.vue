<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useLocale } from '../i18n/use-locale'
import type { JobRecord, UserFile } from '../types/domain'

const props = defineProps<{
  draft: string
  webSearchEnabled: boolean
  selectedFile: UserFile | null
  activeJob: JobRecord | null
  sending: boolean
  /** 未登录预览下，发送和上传只请求登录，不执行真实请求。 */
  authRequired?: boolean
}>()
const emit = defineEmits<{
  'update:draft': [value: string]
  'update:web-search': [value: boolean]
  'send': []
  'cancel': []
  'upload': [file: File]
  'clear-file': []
  'request-auth': [action: 'send' | 'upload']
}>()

const { text } = useLocale()
const textarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isWaiting = computed(() => props.activeJob?.uiState === 'waiting_input')
const isRunning = computed(() => Boolean(props.activeJob && ['queued', 'running', 'canceling'].includes(props.activeJob.uiState)))
const isCanceling = computed(() => props.activeJob?.uiState === 'canceling')
const placeholder = computed(() => isWaiting.value ? text.value.waitingPlaceholder : text.value.inputPlaceholder)
const selectedFileType = computed(() => {
  const extension = props.selectedFile?.filename.split('.').pop()?.trim()
  return extension ? extension.toUpperCase() : 'FILE'
})
const selectedFileSize = computed(() => {
  const size = props.selectedFile?.fileSize
  if (size === undefined || !Number.isFinite(size) || size < 0) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`
  return `${(size / (1024 * 1024)).toFixed(size < 10 * 1024 * 1024 ? 1 : 0)} MB`
})

function resize(): void {
  if (!textarea.value) return
  textarea.value.style.height = 'auto'
  textarea.value.style.height = `${Math.max(96, Math.min(textarea.value.scrollHeight, 260))}px`
}

function triggerUpload(): void {
  fileInput.value?.click()
}

function onFileChange(event: Event): void {
  const input = event.currentTarget as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', file)
  input.value = ''
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    requestSend()
  }
}

function onPrimaryAction(): void {
  if (isRunning.value) {
    emit('cancel')
    return
  }
  requestSend()
}

function requestSend(): void {
  if (props.authRequired) {
    emit('request-auth', 'send')
    return
  }
  emit('send')
}

function onUploadClick(): void {
  if (props.authRequired) {
    emit('request-auth', 'upload')
    return
  }
  triggerUpload()
}

watch(() => props.draft, () => { void nextTick(resize) })
</script>

<template>
  <section class="composer" aria-label="消息输入区">
    <div v-if="selectedFile" class="selected-file-draft">
      <div class="selected-file-card">
        <span class="selected-file-icon" aria-hidden="true">{{ selectedFileType }}</span>
        <span class="selected-file-details">
          <strong class="selected-file-name" :title="selectedFile.filename">{{ selectedFile.filename }}</strong>
          <span class="selected-file-meta">{{ selectedFileType }} {{ selectedFileSize }}</span>
        </span>
        <button class="clear-selected-file-button" type="button" :aria-label="text.clearFile" @click="emit('clear-file')">×</button>
      </div>
    </div>
    <textarea
      ref="textarea"
      :value="draft"
      :placeholder="placeholder"
      rows="4"
      :disabled="sending || Boolean(isRunning)"
      @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
      @keydown="onKeydown"
    ></textarea>
    <div class="composer-actions">
      <input ref="fileInput" class="visually-hidden" type="file" accept=".csv,text/csv" @change="onFileChange" />
      <button class="secondary-button web-search-button" :class="{ active: webSearchEnabled }" type="button" :aria-pressed="webSearchEnabled" @click="emit('update:web-search', !webSearchEnabled)">
        {{ webSearchEnabled ? text.webSearchOn : text.webSearchOff }}
      </button>
      <button class="secondary-button upload-button" type="button" :disabled="sending || Boolean(isRunning)" @click="onUploadClick">{{ text.upload }}</button>
      <button
        class="primary-button send-button"
        :class="{ 'is-running': isRunning }"
        type="button"
        :aria-label="isRunning ? text.cancelJob : text.send"
        :title="isRunning ? text.cancelJob : text.send"
        :disabled="sending || isCanceling || (!isRunning && !draft.trim())"
        @click="onPrimaryAction"
      >
        <span class="send-button-label">{{ sending ? text.loading : text.send }}</span>
        <span class="send-button-stop" aria-hidden="true"></span>
      </button>
    </div>
  </section>
</template>
