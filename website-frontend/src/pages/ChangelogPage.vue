<script setup lang="ts">
import { CHANGELOG_ENTRIES, CHANGELOG_INTRO } from '../content/changelog'
</script>

<template>
  <div class="page">
    <header class="page-header">
      <p class="eyebrow">更新日志</p>
      <h1>{{ CHANGELOG_INTRO.title }}</h1>
      <p class="section-summary">{{ CHANGELOG_INTRO.summary }}</p>
    </header>

    <section class="section">
      <article v-for="entry in CHANGELOG_ENTRIES" :key="entry.version" class="release">
        <header class="release-header">
          <h2>{{ entry.version }}</h2>
          <span class="release-status">{{ entry.status }}</span>
          <time :datetime="entry.date">{{ entry.date }}</time>
        </header>
        <ul class="highlight-list">
          <li v-for="highlight in entry.highlights" :key="highlight">{{ highlight }}</li>
        </ul>
        <ul>
          <li v-for="item in entry.items" :key="item">{{ item }}</li>
        </ul>
      </article>
    </section>
  </div>
</template>

