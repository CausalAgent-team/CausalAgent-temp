<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../renderers/markdown-adapter'
import CausalGraph from './CausalGraph.vue'
import type { CausalGraphData, MessageText, StructuredMessage } from '../types/domain'

const props = defineProps<{ text: MessageText }>()
const structured = computed<StructuredMessage | null>(() => typeof props.text === 'string' ? null : props.text)
const isGraph = computed(() => {
  const data = structured.value?.data
  return structured.value?.type === 'causal_graph'
    && typeof data === 'object'
    && data !== null
    && Array.isArray((data as Record<string, unknown>).nodes)
    && Array.isArray((data as Record<string, unknown>).edges)
})
const graph = computed<CausalGraphData | null>(() => {
  if (!isGraph.value || !structured.value?.data) return null
  const data = structured.value.data as { nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>> }
  return { nodes: data.nodes, edges: data.edges }
})
const summaryHtml = computed(() => {
  if (typeof props.text === 'string') return renderMarkdown(props.text)
  return renderMarkdown(props.text.summary ?? '')
})
</script>

<template>
  <div v-if="isGraph" class="report-content">
    <div v-if="structured?.summary" class="markdown-content" v-html="summaryHtml"></div>
    <CausalGraph v-if="graph" :graph="graph" />
  </div>
  <div v-else-if="structured?.summary !== undefined || typeof text === 'string'" class="markdown-content" v-html="summaryHtml"></div>
  <pre v-else class="unknown-message">{{ JSON.stringify(text, null, 2) }}</pre>
</template>
