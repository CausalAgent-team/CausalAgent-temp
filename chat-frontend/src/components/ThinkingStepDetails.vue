<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  PRESENTATION_CHARS_PER_TICK,
  PRESENTATION_TICK_MS,
  prefersReducedMotion,
  textLength,
} from '../runtime/chat/presentation'
import { useChatScrollFollow } from '../runtime/chat/scroll-follow'
import { decisionKindPrefix } from '../runtime/jobs/step-details'
import type { StepDecisionDetail, StepDetail, ThinkingStep } from '../types/domain'

const props = defineProps<{ step: ThinkingStep; animate: boolean }>()
const scrollFollow = useChatScrollFollow()
const revealed = ref<Record<string, number>>({})
let timer: number | null = null

const decisions = computed(() => props.step.details.filter(
  (detail): detail is StepDecisionDetail => detail.kind === 'decision',
))

function stopTimer(): void {
  if (timer !== null) {
    globalThis.clearInterval(timer)
    timer = null
  }
}

// 同一阶段内按到达顺序串行推进，避免多条公开决策同时逐字出现。
function nextEntry(): StepDecisionDetail | null {
  if (!props.animate || prefersReducedMotion()) return null
  for (const entry of decisions.value) {
    if ((revealed.value[entry.key] ?? 0) < textLength(entry.text)) return entry
  }
  return null
}

function visibleText(entry: StepDecisionDetail): string {
  if (!props.animate || prefersReducedMotion()) return entry.text
  return Array.from(entry.text).slice(0, revealed.value[entry.key] ?? 0).join('')
}

function tick(): void {
  const entry = nextEntry()
  if (!entry) {
    stopTimer()
    return
  }
  const current = revealed.value[entry.key] ?? 0
  const limit = textLength(entry.text)
  revealed.value = { ...revealed.value, [entry.key]: Math.min(limit, current + PRESENTATION_CHARS_PER_TICK) }
  scrollFollow.keepLatest()
}

function sync(): void {
  if (nextEntry()) {
    if (timer === null) timer = globalThis.setInterval(tick, PRESENTATION_TICK_MS)
  } else {
    stopTimer()
  }
}

function detailKey(detail: StepDetail, index: number): string {
  return detail.kind === 'decision' ? `${index}-${detail.key}` : `${index}-${detail.text}`
}

watch(() => props.step.details, sync)
watch(() => props.animate, sync)

onMounted(sync)
onBeforeUnmount(stopTimer)
</script>

<template>
  <div class="step-details">
    <template v-for="(detail, index) in step.details" :key="detailKey(detail, index)">
      <p v-if="detail.kind === 'text'" class="step-detail" :class="{ error: detail.tone === 'error', retry: detail.tone === 'retry' }">{{ detail.text }}</p>
      <p v-else class="step-detail decision-detail">{{ decisionKindPrefix(detail.decisionKind) }}{{ visibleText(detail) }}</p>
    </template>
  </div>
</template>
