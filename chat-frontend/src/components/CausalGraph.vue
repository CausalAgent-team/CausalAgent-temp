<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { mountCausalGraph } from '../renderers/graph-renderer'
import type { CausalGraphData } from '../types/domain'

const props = defineProps<{ graph: CausalGraphData }>()
const container = ref<HTMLElement | null>(null)
let destroyGraph: (() => void) | null = null

onMounted(async () => {
  if (!container.value) return
  try {
    destroyGraph = await mountCausalGraph(container.value, props.graph)
  } catch {
    if (container.value) container.value.textContent = '图形加载失败。'
  }
})

onBeforeUnmount(() => {
  destroyGraph?.()
  destroyGraph = null
})
</script>

<template>
  <div ref="container" class="causal-graph causal-graph-container" role="img" aria-label="因果关系图"></div>
</template>
