<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../renderers/markdown-adapter'

const props = defineProps<{
  content: string
  evidenceRefs: string[]
  evidence: Map<string, string>
}>()

// Markdown 解析只经过适配器；报告文本块复用普通聊天的同一套 marked 行为。
const html = computed(() => renderMarkdown(props.content))
const notes = computed(() => props.evidenceRefs
  .map((id) => ({ id, description: props.evidence.get(id) ?? '' }))
  .filter((item) => item.description))
</script>

<template>
  <div class="report-markdown">
    <div class="markdown-content" v-html="html"></div>
    <ul v-if="notes.length" class="report-evidence">
      <li v-for="note in notes" :key="note.id">{{ note.description }}</li>
    </ul>
  </div>
</template>

<style scoped>
.report-markdown {
  min-width: 0;
  font-size: var(--report-text-size, 15px);
  line-height: 1.65;
}

.report-markdown :deep(.markdown-content) {
  overflow-wrap: anywhere;
}

.report-markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}

.report-markdown :deep(th),
.report-markdown :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--report-border, #e2e5e9);
}

.report-markdown :deep(pre) {
  max-width: 100%;
  padding: 10px 12px;
  overflow-x: auto;
  background: var(--report-code-background, #eef1f4);
  border-radius: 6px;
}

.report-markdown :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  color: var(--color-text-muted, #6b7280);
  border-left: 3px solid var(--report-border, #e2e5e9);
}

.report-evidence {
  margin: 10px 0 0;
  padding: 8px 12px 8px 26px;
  font-size: 13px;
  color: var(--color-text-muted, #6b7280);
  background: var(--report-muted-background, #eef1f4);
  border-radius: 6px;
}
</style>
