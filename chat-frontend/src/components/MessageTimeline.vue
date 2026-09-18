<script setup lang="ts">
import { computed, watch } from 'vue'
import { isPresentationActive } from '../runtime/chat/presentation'
import { useChatScrollFollow } from '../runtime/chat/scroll-follow'
import { stepDetailText, textDetail } from '../runtime/jobs/step-details'
import { useJobsStore } from '../stores/jobs.store'
import type { ChatMessage, ExecutionPhase, StepDetail, ThinkingProjection } from '../types/domain'
import MessageBody from './MessageBody.vue'
import StreamingDraft from './StreamingDraft.vue'
import ThinkingTimeline from './ThinkingTimeline.vue'

const props = defineProps<{ messages: ChatMessage[] }>()
const jobs = useJobsStore()
const scrollFollow = useChatScrollFollow()

/** 只有已持久化的历史阶段事件会走到这里；公开决策在历史中本来就是完整文本。 */
function phaseThinking(phase: ExecutionPhase): ThinkingProjection {
  const job = phase.analysisJobId ? jobs.byId(phase.analysisJobId) : undefined
  if (job) return job.thinking
  const steps: ThinkingProjection['steps'] = {}
  const order: string[] = []
  const detailsFor = (event: Record<string, unknown>): StepDetail[] => {
    if (event.type === 'node_retry') {
      const message = typeof event.message === 'string' ? event.message : ''
      return [textDetail(`调用失败：${message}`, 'error'), textDetail('正在重试', 'retry')]
    }
    if (event.type === 'node_end') {
      const message = typeof event.message === 'string' ? event.message : ''
      return event.status === 'failed' && message ? [textDetail(`调用失败：${message}`, 'error')] : []
    }
    const detail = stepDetailText(event)
    return detail ? [textDetail(detail)] : []
  }
  for (const event of phase.events) {
    const stepId = typeof event.step_id === 'string' ? event.step_id : ''
    if (!stepId) continue
    let step = steps[stepId]
    if (!step) {
      step = {
        stepId,
        nodeName: typeof event.node_name === 'string' ? event.node_name : '',
        title: typeof event.title === 'string' ? event.title : '',
        status: 'in-progress',
        duration: null,
        details: [],
      }
      steps[stepId] = step
      order.push(stepId)
    }
    if (event.type === 'node_end') {
      step.status = event.status === 'failed' ? 'failed' : 'completed'
      step.duration = typeof event.duration === 'number' ? event.duration : null
    } else if (event.type === 'node_retry') {
      step.status = 'in-progress'
    }
    step.details = [...step.details, ...detailsFor(event)]
  }
  return {
    status: phase.status === 'waiting_input' ? 'waiting_input' : phase.status === 'failed' ? 'failed' : phase.status === 'canceled' ? 'canceled' : phase.status === 'completed' ? 'completed' : 'active',
    startedAt: Date.now() - phase.elapsedSeconds * 1000,
    elapsedSeconds: phase.elapsedSeconds,
    steps,
    stepOrder: order,
    pendingStepEvents: {},
    draftStreamId: null,
    draftText: '',
    finalResult: null,
    errorMessage: null,
    waitingInput: null,
  }
}

function thinkingForMessage(message: ChatMessage): ThinkingProjection | null {
  if (message.analysisJobId) {
    const liveJob = jobs.byId(message.analysisJobId)
    if (liveJob) return liveJob.thinking
  }
  return message.thinkingAfter ? phaseThinking(message.thinkingAfter) : null
}

const messageRows = computed(() => props.messages.map((message) => ({
  message,
  thinking: thinkingForMessage(message),
})))

watch(() => props.messages.length, () => scrollFollow.keepLatest())
</script>

<template>
  <div v-if="!messageRows.length" class="conversation-empty" aria-live="polite">CausalAgent</div>
  <div v-for="row in messageRows" :key="row.message.localId" class="message-row" :class="`${row.message.sender}-message-row`">
    <article class="message" :class="`${row.message.sender}-message`">
      <MessageBody :text="row.message.text" />
    </article>
    <ThinkingTimeline v-if="row.thinking" :thinking="row.thinking" />
    <StreamingDraft v-if="row.thinking?.draftText" :text="row.thinking.draftText" :animate="isPresentationActive(row.thinking.status)" />
    <article v-if="row.thinking?.finalResult" class="message ai-message">
      <MessageBody :text="row.thinking.finalResult" />
    </article>
    <article v-if="row.thinking?.waitingInput" class="message ai-message">
      <MessageBody :text="{ type: 'human_input_required', summary: row.thinking.waitingInput.prompt }" />
    </article>
    <article v-if="row.thinking?.errorMessage" class="message ai-message">
      <MessageBody :text="{ type: 'text', summary: `错误：${row.thinking.errorMessage}` }" />
    </article>
  </div>
</template>
