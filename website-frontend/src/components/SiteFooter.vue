<script setup lang="ts">
const columns = [
  {
    title: '产品',
    links: [
      { label: '产品能力', href: '/product' },
      { label: '进入工作区', href: '/dashboard' },
      { label: '更新日志', href: '/changelog' },
    ],
  },
  {
    title: '资源',
    links: [
      { label: '使用文档', href: '/docs' },
      { label: '关于我们', href: '/about' },
    ],
  },
  {
    title: '账号',
    links: [
      { label: '登录', href: '/auth/sign-in' },
      { label: '注册', href: '/auth/sign-up' },
    ],
  },
] as const
</script>

<template>
  <footer class="site-footer">
    <div class="site-footer-inner">
      <div class="footer-brand">
        <span class="brand-mark" aria-hidden="true">CA</span>
        <div>
          <p class="footer-title">CausalAgent</p>
          <p class="footer-line">面向因果分析场景的智能体工作台。</p>
        </div>
      </div>
      <div class="footer-columns">
        <div v-for="column in columns" :key="column.title" class="footer-column">
          <p class="footer-column-title">{{ column.title }}</p>
          <a v-for="link in column.links" :key="link.href" :href="link.href">{{ link.label }}</a>
        </div>
      </div>
    </div>
    <p class="footer-copyright">© 2026 CausalAgent</p>
  </footer>
</template>

