<script setup lang="ts">
import { computed, ref } from 'vue'
import AuthCard from '../components/AuthCard.vue'
import { register } from '../api/auth'
import { readQueryValue } from '../routes'

const next = readQueryValue(globalThis.location.search, 'next')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const done = ref(false)

const signInHref = computed<string>(() =>
  next ? '/auth/sign-in?next=' + encodeURIComponent(next) : '/auth/sign-in',
)

async function submit(): Promise<void> {
  if (busy.value) return
  error.value = null
  if (username.value.length < 3) {
    error.value = '用户名至少需要 3 个字符。'
    return
  }
  if (password.value.length < 6) {
    error.value = '密码至少需要 6 个字符。'
    return
  }
  if (!/[0-9]/.test(password.value)) {
    error.value = '密码必须包含至少一个数字。'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致。'
    return
  }
  busy.value = true
  try {
    await register(username.value, password.value)
    done.value = true
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '注册失败，请稍后再试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard title="创建账号" subtitle="注册后即可进入工作区，历史会话与上传的数据按账号保存。">
    <p v-if="done" class="auth-success" role="status">
      注册成功，请使用新账号登录。
      <a :href="signInHref">前往登录</a>
    </p>
    <form v-else class="auth-form" @submit.prevent="submit">
      <label>
        <span>用户名</span>
        <input v-model="username" name="username" type="text" autocomplete="username" required />
        <small>至少 3 个字符</small>
      </label>
      <label>
        <span>密码</span>
        <input v-model="password" name="password" type="password" autocomplete="new-password" required />
        <small>至少 6 个字符，且包含数字</small>
      </label>
      <label>
        <span>确认密码</span>
        <input v-model="confirmPassword" name="confirm-password" type="password" autocomplete="new-password" required />
      </label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button large" type="submit" :disabled="busy">
        {{ busy ? '正在注册…' : '注册' }}
      </button>
    </form>
    <p class="auth-switch">
      已有账号？
      <a :href="signInHref">直接登录</a>
    </p>
  </AuthCard>
</template>

