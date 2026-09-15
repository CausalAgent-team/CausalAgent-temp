<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useLocale } from '../i18n/use-locale'
import type { ThinkingProjection } from '../types/domain'

const props = defineProps<{ thinking: ThinkingProjection }>()
const { text } = useLocale()
const expanded = ref(true)
const expandedSteps = ref<Record<string, boolean>>({})
const now = ref(Date.now())
let durationTimer: number | null = null

const elapsed = computed(() => props.thinking.status === 'active'
  ? Math.max(0, now.value - props.thinking.startedAt) / 1000
  : props.thinking.elapsedSeconds)

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(2).replace(/0+$/, '').replace(/\.$/, '') || '0'}s`
  const whole = Math.floor(seconds)
  const minutes = Math.floor(whole / 60)
  return `${minutes}m ${whole % 60}s`
}

function statusText(): string {
  if (props.thinking.status === 'waiting_input') return text.value.waitingInput
  if (props.thinking.status === 'failed') return text.value.taskFailed
  if (props.thinking.status === 'canceled') return text.value.taskCanceled
  return props.thinking.status === 'active' ? text.value.thinking : text.value.processed
}

function toggleStep(stepId: string): void {
  expandedSteps.value = { ...expandedSteps.value, [stepId]: !expandedSteps.value[stepId] }
}

onMounted(() => {
  durationTimer = globalThis.setInterval(() => { now.value = Date.now() }, 100)
})

onBeforeUnmount(() => {
  if (durationTimer !== null) globalThis.clearInterval(durationTimer)
  durationTimer = null
})
</script>

<template>
  <div class="thinking-block">
    <button class="thinking-header" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      <span>{{ statusText() }}</span>
      <span class="thinking-duration">{{ formatElapsed(elapsed) }}</span>
      <span v-if="thinking.status === 'active'" class="thinking-dots" aria-hidden="true">...</span>
      <span class="disclosure">{{ expanded ? '▾' : '▸' }}</span>
    </button>
    <div v-if="expanded" class="thinking-detail">
      <div v-for="stepId in thinking.stepOrder" :key="stepId" class="thinking-step" :class="`is-${thinking.steps[stepId]?.status || 'completed'}`">
        <button class="step-header" type="button" @click="toggleStep(stepId)">
          <span class="step-status" aria-hidden="true"></span>
          <span class="step-name">{{ thinking.steps[stepId]?.title }}</span>
          <span class="step-time">{{ thinking.steps[stepId]?.duration !== null ? `${thinking.steps[stepId]?.duration}s` : text.inProgress }}</span>
          <span class="disclosure">{{ expandedSteps[stepId] ? '▾' : '▸' }}</span>
        </button>
        <div v-if="expandedSteps[stepId]" class="step-details">
          <p v-for="(detail, index) in thinking.steps[stepId]?.details" :key="`${stepId}-${index}`">{{ detail }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
