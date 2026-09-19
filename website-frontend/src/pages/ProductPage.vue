<script setup lang="ts">
import { FEATURES, PLATFORM_FACTS, WORKFLOW_STEPS } from '../content/product'
</script>

<template>
  <div class="page">
    <header class="page-header">
      <p class="eyebrow">产品</p>
      <h1>为可复核的因果分析设计</h1>
      <p class="section-summary">
        智能体先把材料看清楚，再决定用哪种因果方法，并把每一步的依据公开在任务事件里。
      </p>
    </header>

    <section class="section">
      <h2 class="section-title">能力说明</h2>
      <div class="detail-list">
        <article v-for="feature in FEATURES" :key="feature.key" class="detail">
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.summary }}</p>
          <ul>
            <li v-for="bullet in feature.bullets" :key="bullet">{{ bullet }}</li>
          </ul>
        </article>
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">分析流程</h2>
      <ol class="step-list">
        <li v-for="(step, index) in WORKFLOW_STEPS" :key="step.key" class="step">
          <span class="step-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <h3>{{ step.title }}</h3>
            <p>{{ step.description }}</p>
          </div>
        </li>
      </ol>
    </section>

    <section class="section">
      <h2 class="section-title">平台边界</h2>
      <dl class="fact-grid">
        <div v-for="fact in PLATFORM_FACTS" :key="fact.label" class="fact">
          <dt>{{ fact.label }}</dt>
          <dd>{{ fact.value }}</dd>
        </div>
      </dl>
    </section>

    <section class="cta-band">
      <h2>进入工作区上手体验</h2>
      <p>工作区只对登录用户开放，注册后即可开始。</p>
      <div class="hero-actions">
        <a class="primary-button large" href="/dashboard">进入工作区</a>
        <a class="ghost-button large" href="/docs">查看使用文档</a>
      </div>
    </section>
  </div>
</template>

