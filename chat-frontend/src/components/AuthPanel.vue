<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useLocale } from '../i18n/use-locale'

const props = defineProps<{
  busy: boolean
  error: string | null
  notice?: string | null
  closeable?: boolean
}>()
const emit = defineEmits<{
  login: [username: string, password: string]
  register: [username: string, password: string, confirmPassword: string]
  close: []
}>()

const { text } = useLocale()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const passwordVisible = ref(false)
const localError = ref('')
const usernameInput = ref<HTMLInputElement | null>(null)
const cardElement = ref<HTMLElement | null>(null)

const heading = computed(() => (mode.value === 'login' ? text.value.login : text.value.register))
const errorMessage = computed(() => localError.value || props.error || '')
/* 提示只在登录态展示：它讲的是“注册成功，请登录”。 */
const noticeMessage = computed(() => (mode.value === 'login' && !errorMessage.value ? props.notice || '' : ''))

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
  passwordVisible.value = false
}

/* 注册成功后回到登录态，用户只需要补一次提交。 */
watch(
  () => props.notice,
  (notice) => {
    if (!notice) return
    mode.value = 'login'
    localError.value = ''
  },
)

function closePanel(): void {
  if (props.busy) return
  emit('close')
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    if (props.closeable) closePanel()
    return
  }
  if (event.key !== 'Tab') return
  const card = cardElement.value
  if (!card) return
  const first = card.querySelector<HTMLElement>('input:not(:disabled), button:not(:disabled)')
  const buttons = card.querySelectorAll<HTMLElement>('button:not(:disabled)')
  const last = buttons.item(buttons.length - 1)
  if (!first || !last) return
  const active = globalThis.document.activeElement
  const inside = active !== null && card.contains(active)
  if (event.shiftKey) {
    if (inside && active !== first) return
    event.preventDefault()
    last.focus()
    return
  }
  if (inside && active !== last) return
  event.preventDefault()
  first.focus()
}

onMounted(() => {
  globalThis.addEventListener('keydown', onKeydown)
  usernameInput.value?.focus()
})

onBeforeUnmount(() => {
  globalThis.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <section class="auth-panel" @click.self="closeable && closePanel()">
    <form
      ref="cardElement"
      class="auth-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-title"
      :aria-busy="busy"
      @submit.prevent="submit"
    >
      <header class="auth-head">
        <span class="auth-brand">CausalAgent</span>
        <h2 id="auth-title">{{ heading }}</h2>
      </header>
      <p class="auth-message" role="alert" aria-live="polite">
        <span v-if="errorMessage" class="form-error">{{ errorMessage }}</span>
        <span v-else-if="noticeMessage" class="form-notice">{{ noticeMessage }}</span>
      </p>
      <div class="auth-field">
        <label class="auth-label" for="auth-username">{{ text.username }}</label>
        <input id="auth-username" ref="usernameInput" v-model="username" type="text" autocomplete="username" required :disabled="busy" />
      </div>
      <div class="auth-field">
        <label class="auth-label" for="auth-password">{{ text.password }}</label>
        <div class="auth-input-wrap">
          <input
            id="auth-password"
            v-model="password"
            :type="passwordVisible ? 'text' : 'password'"
            autocomplete="current-password"
            required
            :disabled="busy"
          />
          <button
            class="password-toggle"
            type="button"
            :aria-label="passwordVisible ? text.hidePassword : text.showPassword"
            :aria-pressed="passwordVisible"
            :disabled="busy"
            @click="passwordVisible = !passwordVisible"
          >
            <svg class="password-toggle-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" />
              <circle cx="12" cy="12" r="3.2" />
              <line v-if="!passwordVisible" x1="4.5" y1="19.5" x2="19.5" y2="4.5" />
            </svg>
          </button>
        </div>
      </div>
      <div v-if="mode === 'register'" class="auth-field">
        <label class="auth-label" for="auth-confirm-password">{{ text.confirmPassword }}</label>
        <input
          id="auth-confirm-password"
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          required
          :disabled="busy"
        />
      </div>
      <button class="primary-button auth-submit" type="submit" :disabled="busy">
        {{ busy ? text.loading : heading }}
      </button>
      <button class="link-button" type="button" :disabled="busy" @click="toggleMode">
        {{ mode === 'login' ? text.loginHint : text.registerHint }}
      </button>
      <button v-if="closeable" class="link-button auth-close" type="button" :disabled="busy" @click="closePanel">
        {{ text.backToPreview }}
      </button>
    </form>
  </section>
</template>
