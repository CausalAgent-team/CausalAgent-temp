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
}>()
const emit = defineEmits<{
  'update:draft': [value: string]
  'update:web-search': [value: boolean]
  'send': []
  'cancel': []
  'upload': [file: File]
  'clear-file': []
}>()

const { text } = useLocale()
const textarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isWaiting = computed(() => props.activeJob?.uiState === 'waiting_input')
const isRunning = computed(() => props.activeJob && ['queued', 'running', 'canceling'].includes(props.activeJob.uiState))
const placeholder = computed(() => isWaiting.value ? text.value.waitingPlaceholder : text.value.inputPlaceholder)

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
    emit('send')
  }
}

watch(() => props.draft, () => { void nextTick(resize) })
</script>

<template>
  <section class="composer" aria-label="消息输入区">
    <div v-if="selectedFile" class="selected-file-chip">
      <span class="file-chip-type">CSV</span>
      <span class="file-chip-name" :title="selectedFile.filename">{{ selectedFile.filename }}</span>
      <button type="button" :aria-label="text.clearFile" @click="emit('clear-file')">×</button>
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
      <button class="secondary-button" type="button" :disabled="sending || Boolean(isRunning)" @click="triggerUpload">{{ text.upload }}</button>
      <button v-if="isWaiting || isRunning" class="secondary-button cancel-button" type="button" :disabled="sending || activeJob?.uiState === 'canceling'" @click="emit('cancel')">
        {{ activeJob?.uiState === 'canceling' ? text.canceling : text.cancelJob }}
      </button>
      <button class="primary-button send-button" type="button" :disabled="sending || Boolean(isRunning && !isWaiting) || !draft.trim()" @click="emit('send')">
        {{ sending ? text.loading : isWaiting ? text.send : text.send }}
      </button>
    </div>
  </section>
</template>
