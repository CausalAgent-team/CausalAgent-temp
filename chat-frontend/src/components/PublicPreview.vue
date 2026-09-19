<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '../i18n/use-locale'
import { publicPreviewDemo, publicPreviewDemos } from '../preview/public-preview-data'
import type { PreviewDemoKey } from '../runtime/analytics/analytics-client'
import Composer from './Composer.vue'
import MessageBody from './MessageBody.vue'

/*
 * 公开预览只渲染静态示例数据和产品说明，所有会写数据的入口都向上抛出
 * request-auth，由 App.vue 打开登录面板；组件本身不调用任何业务接口。
 */
const props = defineProps<{
  draft: string
  webSearchEnabled: boolean
  demoKey: PreviewDemoKey
}>()
const emit = defineEmits<{
  'update:draft': [value: string]
  'update:web-search': [value: boolean]
  'request-auth': [action: 'login' | 'register' | 'send' | 'upload' | 'new-chat']
  'demo-open': [key: PreviewDemoKey]
}>()

const { text } = useLocale()
const activeDemo = computed(() => publicPreviewDemo(props.demoKey))
</script>

<template>
  <div class="preview-shell">
    <header class="preview-header">
      <span class="preview-brand">CausalAgent</span>
      <span class="preview-badge">{{ text.previewBadge }}</span>
      <div class="preview-header-actions">
        <button class="secondary-button" type="button" @click="emit('request-auth', 'login')">{{ text.login }}</button>
        <button class="primary-button" type="button" @click="emit('request-auth', 'register')">{{ text.register }}</button>
      </div>
    </header>
    <section class="preview-hero">
      <h1>{{ text.previewTitle }}</h1>
      <p>{{ text.previewDescription }}</p>
      <ul class="preview-features">
        <li>{{ text.previewFeatureData }}</li>
        <li>{{ text.previewFeatureTrace }}</li>
        <li>{{ text.previewFeatureReport }}</li>
      </ul>
    </section>
    <section class="preview-stage" aria-label="产品界面示例">
      <aside class="preview-sidebar">
        <div class="preview-sidebar-header">CausalAgent</div>
        <button class="sidebar-primary" type="button" @click="emit('request-auth', 'new-chat')">{{ text.newChat }}</button>
        <div class="preview-session-list">
          <button
            v-for="demo in publicPreviewDemos"
            :key="demo.key"
            class="preview-session-item"
            :class="{ selected: demo.key === demoKey }"
            type="button"
            @click="emit('demo-open', demo.key)"
          >
            <span class="sidebar-time">{{ text.previewDemoTag }}</span>
            <span class="sidebar-preview">{{ demo.title }}</span>
          </button>
        </div>
        <p class="preview-sidebar-note">{{ text.previewDemoNote }}</p>
      </aside>
      <div class="preview-conversation">
        <div class="preview-demo-head">
          <h2>{{ activeDemo.title }}</h2>
          <p>{{ activeDemo.description }}</p>
        </div>
        <div class="preview-messages">
          <div
            v-for="message in activeDemo.messages"
            :key="message.localId"
            class="message-row"
            :class="message.sender + '-message-row'"
          >
            <article class="message" :class="message.sender + '-message'">
              <MessageBody :text="message.text" />
            </article>
          </div>
        </div>
        <div class="preview-composer">
          <Composer
            auth-required
            :draft="draft"
            :web-search-enabled="webSearchEnabled"
            :selected-file="null"
            :active-job="null"
            :sending="false"
            @update:draft="emit('update:draft', $event)"
            @update:web-search="emit('update:web-search', $event)"
            @request-auth="emit('request-auth', $event)"
          />
          <p class="preview-lock-note">{{ text.previewLockNote }}</p>
        </div>
      </div>
    </section>
  </div>
</template>
