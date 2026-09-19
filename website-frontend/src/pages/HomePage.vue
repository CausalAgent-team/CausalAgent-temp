<script setup lang="ts">
import { DOWNLOADS, FEATURES, HERO, PLATFORM_FACTS, WORKFLOW_STEPS } from '../content/product'
</script>

<template>
  <div class="page">
    <section class="hero">
      <p class="eyebrow">因果分析智能体</p>
      <h1>{{ HERO.title }}</h1>
      <p class="hero-summary">{{ HERO.summary }}</p>
      <div class="hero-actions">
        <a class="primary-button large" :href="HERO.primaryAction.href">{{ HERO.primaryAction.label }}</a>
        <a class="ghost-button large" :href="HERO.secondaryAction.href">{{ HERO.secondaryAction.label }}</a>
      </div>
      <dl class="fact-grid">
        <div v-for="fact in PLATFORM_FACTS" :key="fact.label" class="fact">
          <dt>{{ fact.label }}</dt>
          <dd>{{ fact.value }}</dd>
        </div>
      </dl>
    </section>

    <section class="section">
      <h2 class="section-title">一条链路完成分析</h2>
      <p class="section-summary">从问题描述到结论复核，中间不换工具、不丢上下文。</p>
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
      <h2 class="section-title">核心能力</h2>
      <div class="card-grid">
        <article v-for="feature in FEATURES" :key="feature.key" class="card">
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.summary }}</p>
          <ul>
            <li v-for="bullet in feature.bullets" :key="bullet">{{ bullet }}</li>
          </ul>
        </article>
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">开始使用</h2>
      <div class="card-grid two">
        <article v-for="option in DOWNLOADS" :key="option.label" class="card">
          <h3>{{ option.label }}</h3>
          <p>{{ option.description }}</p>
          <a v-if="option.href" class="ghost-button" :href="option.href">{{ option.action }}</a>
          <p v-else class="muted-note">{{ option.action }}</p>
        </article>
      </div>
    </section>

    <section class="cta-band">
      <h2>先用一次真实的分析任务试试</h2>
      <p>注册后即可上传数据、运行任务并导出报告。</p>
      <div class="hero-actions">
        <a class="primary-button large" href="/auth/sign-up">免费注册</a>
        <a class="ghost-button large" href="/auth/sign-in">已有账号，直接登录</a>
      </div>
    </section>
  </div>
</template>

