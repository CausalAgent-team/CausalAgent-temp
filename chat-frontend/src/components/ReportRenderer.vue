<script setup lang="ts">
import { computed } from 'vue'
import { parseReportDocument } from '../renderers/report-document'
import ReportBlockView from './ReportBlockView.vue'

const props = defineProps<{ document: unknown }>()
const parsed = computed(() => parseReportDocument(props.document))
const evidenceById = computed(() => new Map(
  (parsed.value?.evidenceRefs ?? []).map((item) => [item.evidence_id, item.description]),
))
</script>

<template>
  <section v-if="parsed" class="report-document">
    <h1 class="report-title">{{ parsed.title }}</h1>
    <ReportBlockView
      v-for="block in parsed.blocks"
      :key="block.id"
      :block="block"
      :evidence="evidenceById"
    />
    <footer v-if="parsed.sources.length" class="report-sources">
      <h2 class="report-sources-title">来源</h2>
      <ul class="report-sources-list">
        <li v-for="source in parsed.sources" :key="source.source_id">
          <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a>
          <span v-else>{{ source.title }}</span>
        </li>
      </ul>
    </footer>
  </section>
  <div v-else class="report-document report-document-error" role="alert">
    报告内容不可用，请刷新会话或重新生成报告。
  </div>
</template>

<style scoped>
.report-document {
  display: flex;
  flex-direction: column;
  gap: var(--report-block-gap, 18px);
  width: 100%;
  max-width: 100%;
  overflow-wrap: anywhere;
  color: var(--report-text, #1f2937);
}

.report-document-error {
  font-size: 14px;
  color: var(--color-text-muted, #6b7280);
}

.report-title {
  margin: 0;
  font-size: var(--report-title-size, 22px);
  line-height: 1.35;
}

.report-sources {
  padding-top: 12px;
  font-size: 13px;
  border-top: 1px solid var(--report-border, #e2e5e9);
}

.report-sources-title {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--report-accent, #0067c0);
}

.report-sources-list {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-muted, #6b7280);
}

.report-sources-list a {
  color: var(--report-accent, #0067c0);
}
</style>
