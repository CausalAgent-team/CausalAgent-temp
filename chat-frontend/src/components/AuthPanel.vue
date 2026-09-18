<script setup lang="ts">
import { ref } from 'vue'
import { useLocale } from '../i18n/use-locale'

defineProps<{ busy: boolean; error: string | null }>()
const emit = defineEmits<{
  login: [username: string, password: string]
  register: [username: string, password: string, confirmPassword: string]
}>()

const { text } = useLocale()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const localError = ref('')

function submit(): void {
  localError.value = ''
  if (!username.value.trim() || !password.value) {
    localError.value = `${text.value.username}和${text.value.password}不能为空。`
    return
  }
  if (mode.value === 'register') {
    if (password.value.length < 6) {
      localError.value = '密码至少需要6位。'
      return
    }
    if (password.value !== confirmPassword.value) {
      localError.value = '两次输入的密码不匹配。'
      return
    }
    emit('register', username.value.trim(), password.value, confirmPassword.value)
    return
  }
  emit('login', username.value.trim(), password.value)
}

function toggleMode(): void {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  localError.value = ''
}
</script>

<template>
  <section class="auth-panel" aria-labelledby="auth-title">
    <form class="auth-card" @submit.prevent="submit">
      <h2 id="auth-title">{{ mode === 'login' ? text.login : text.register }}</h2>
      <p class="form-error" role="alert">{{ localError || error || '' }}</p>
      <label>
        {{ text.username }}
        <input v-model="username" type="text" autocomplete="username" required :disabled="busy" />
      </label>
      <label>
        {{ text.password }}
        <input v-model="password" type="password" autocomplete="current-password" required :disabled="busy" />
      </label>
      <label v-if="mode === 'register'">
        {{ text.confirmPassword }}
        <input v-model="confirmPassword" type="password" autocomplete="new-password" required :disabled="busy" />
      </label>
      <button class="primary-button auth-submit" type="submit" :disabled="busy">
        {{ busy ? text.loading : mode === 'login' ? text.login : text.register }}
      </button>
      <button class="link-button" type="button" :disabled="busy" @click="toggleMode">
        {{ mode === 'login' ? text.loginHint : text.registerHint }}
      </button>
    </form>
  </section>
</template>
