<script setup lang="ts">
import { computed, ref } from 'vue'
import AuthCard from '../components/AuthCard.vue'
import { login, resolveRedirect } from '../api/auth'
import { readQueryValue } from '../routes'

const props = defineProps<{ loggedInUsername: string | null }>()

const next = readQueryValue(globalThis.location.search, 'next')
const notice = readQueryValue(globalThis.location.search, 'notice')
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref<string | null>(
  notice === 'admin_required' ? '当前账号没有管理员权限，请使用管理员账号登录。' : null,
)

const workspaceTarget = computed<string>(() => resolveRedirect(undefined, next))

async function submit(): Promise<void> {
  if (busy.value) return
  error.value = null
  if (!username.value || !password.value) {
    error.value = '请填写用户名和密码。'
    return
  }
  busy.value = true
  try {
    const payload = await login(username.value, password.value, next)
    globalThis.location.assign(resolveRedirect(payload.redirect_to, next))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败，请稍后再试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard title="登录 CausalAgent" subtitle="使用账号进入工作区；管理员登录后会自动回到管理员页面。">
    <p v-if="props.loggedInUsername" class="auth-hint">
      当前浏览器已登录账号 {{ props.loggedInUsername }}。
      <a :href="workspaceTarget">直接进入</a>
    </p>
    <form class="auth-form" @submit.prevent="submit">
      <label>
        <span>用户名</span>
        <input v-model="username" name="username" type="text" autocomplete="username" required />
      </label>
      <label>
        <span>密码</span>
        <input v-model="password" name="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button large" type="submit" :disabled="busy">
        {{ busy ? '正在登录…' : '登录' }}
      </button>
    </form>
    <p class="auth-switch">
      还没有账号？
      <a :href="next ? '/auth/sign-up?next=' + encodeURIComponent(next) : '/auth/sign-up'">立即注册</a>
    </p>
  </AuthCard>
</template>

