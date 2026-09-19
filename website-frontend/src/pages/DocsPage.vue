<script setup lang="ts">
import { DOC_INTRO, DOC_LINKS, DOC_SECTIONS } from '../content/docs'
</script>

<template>
  <div class="page docs-page">
    <header class="page-header">
      <p class="eyebrow">文档</p>
      <h1>{{ DOC_INTRO.title }}</h1>
      <p class="section-summary">{{ DOC_INTRO.summary }}</p>
    </header>

    <div class="docs-layout">
      <nav class="docs-toc" aria-label="文档目录">
        <a v-for="section in DOC_SECTIONS" :key="section.id" :href="'#' + section.id">{{ section.title }}</a>
      </nav>
      <div class="docs-body">
        <section v-for="section in DOC_SECTIONS" :id="section.id" :key="section.id" class="docs-section">
          <h2>{{ section.title }}</h2>
          <p v-for="paragraph in section.paragraphs" :key="paragraph">{{ paragraph }}</p>
          <ul v-if="section.bullets">
            <li v-for="bullet in section.bullets" :key="bullet">{{ bullet }}</li>
          </ul>
        </section>
        <section class="docs-section">
          <h2>继续了解</h2>
          <ul class="link-list">
            <li v-for="link in DOC_LINKS" :key="link.href">
              <a :href="link.href">{{ link.label }}</a>
              <span>{{ link.description }}</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

