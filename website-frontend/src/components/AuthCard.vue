<script setup lang="ts">
defineProps<{ title: string; subtitle: string }>()
</script>

<template>
  <section class="auth-layout">
    <div class="auth-card">
      <h1>{{ title }}</h1>
      <p class="auth-subtitle">{{ subtitle }}</p>
      <slot />
    </div>
    <aside class="auth-aside">
      <h2>为什么需要账号</h2>
      <p>会话、上传的数据文件和分析报告都按账号保存，登录后才能回到之前的分析现场。</p>
      <ul>
        <li>账号状态与权限由服务端确认</li>
        <li>工作区、评测台和管理员系统各自独立</li>
        <li>退出登录后回到官网首页</li>
      </ul>
    </aside>
  </section>
</template>

