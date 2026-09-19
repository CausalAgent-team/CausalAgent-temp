<script setup lang="ts">
import { SITE_NAV } from '../routes'

const props = defineProps<{ currentPath: string }>()

function isActive(path: string): boolean {
  if (path === '/') return props.currentPath === '/'
  return props.currentPath === path || props.currentPath.startsWith(path + '/')
}
</script>

<template>
  <header class="site-header">
    <div class="site-header-inner">
      <a class="brand" href="/" aria-label="CausalAgent 首页">
        <span class="brand-mark" aria-hidden="true">CA</span>
        <span class="brand-text">CausalAgent</span>
      </a>
      <nav class="site-nav" aria-label="主导航">
        <a
          v-for="item in SITE_NAV"
          :key="item.path"
          :href="item.path"
          :class="{ active: isActive(item.path) }"
          :aria-current="isActive(item.path) ? 'page' : undefined"
        >{{ item.label }}</a>
      </nav>
      <div class="site-actions">
        <a class="ghost-button" href="/auth/sign-in">登录</a>
        <a class="primary-button" href="/auth/sign-up">免费注册</a>
      </div>
    </div>
  </header>
</template>

