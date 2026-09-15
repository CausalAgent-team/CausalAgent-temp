<script setup lang="ts">
import { computed } from 'vue'
import { useJobsStore } from '../stores/jobs.store'
import type { ChatMessage, ExecutionPhase, ThinkingProjection } from '../types/domain'
import MessageBody from './MessageBody.vue'
import ThinkingTimeline from './ThinkingTimeline.vue'

const props = defineProps<{ messages: ChatMessage[] }>()
const jobs = useJobsStore()

function phaseThinking(phase: ExecutionPhase): ThinkingProjection {
  const job = phase.analysisJobId ? jobs.byId(phase.analysisJobId) : undefined
  if (job) return job.thinking
  const steps: ThinkingProjection['steps'] = {}
  const order: string[] = []
  for (const event of phase.events) {
    const stepId = typeof event.step_id === 'string' ? event.step_id : ''
    if (!stepId) continue
    if (!steps[stepId]) {
      steps[stepId] = {
        stepId,
        nodeName: typeof event.node_name === 'string' ? event.node_name : '',
        title: typeof event.title === 'string' ? event.title : '',
        status: 'in-progress',
        duration: null,
        details: [],
      }
      order.push(stepId)
    }
    const step = steps[stepId]
    if (!step) continue
    if (event.type === 'node_end') {
      step.status = event.status === 'failed' ? 'failed' : 'completed'
      step.duration = typeof event.duration === 'number' ? event.duration : null
    } else if (typeof event.summary === 'string') step.details.push(event.summary)
    else if (typeof event.message === 'string' && event.type === 'node_retry') step.details.push(event.message)
  }
  return {
    status: phase.status === 'waiting_input' ? 'waiting_input' : phase.status === 'failed' ? 'failed' : phase.status === 'canceled' ? 'canceled' : phase.status === 'completed' ? 'completed' : 'active',
    startedAt: Date.now() - phase.elapsedSeconds * 1000,
    elapsedSeconds: phase.elapsedSeconds,
    steps,
    stepOrder: order,
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
</script>

<template>
  <div v-if="!messageRows.length" class="conversation-empty" aria-live="polite">CausalAgent</div>
  <div v-for="row in messageRows" :key="row.message.localId" class="message-row" :class="`${row.message.sender}-message-row`">
    <article class="message" :class="`${row.message.sender}-message`">
      <MessageBody :text="row.message.text" />
    </article>
    <ThinkingTimeline v-if="row.thinking" :thinking="row.thinking" />
    <article v-if="row.thinking?.draftText" class="message ai-message streaming-draft">
      <MessageBody :text="{ type: 'text', summary: row.thinking.draftText }" />
    </article>
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
