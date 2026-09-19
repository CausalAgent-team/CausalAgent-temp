<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import SiteFooter from './components/SiteFooter.vue'
import SiteHeader from './components/SiteHeader.vue'
import AboutPage from './pages/AboutPage.vue'
import ChangelogPage from './pages/ChangelogPage.vue'
import DocsPage from './pages/DocsPage.vue'
import HomePage from './pages/HomePage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'
import ProductPage from './pages/ProductPage.vue'
import SignInPage from './pages/SignInPage.vue'
import SignUpPage from './pages/SignUpPage.vue'
import { checkAuth } from './api/auth'
import { readSiteRoute } from './routes'
import type { SitePageName } from './routes'

const route = readSiteRoute(globalThis.location.pathname)

const PAGE_COMPONENTS = {
  home: HomePage,
  product: ProductPage,
  about: AboutPage,
  docs: DocsPage,
  changelog: ChangelogPage,
  'sign-in': SignInPage,
  'sign-up': SignUpPage,
  'not-found': NotFoundPage,
}

const AUTH_PAGES: readonly SitePageName[] = ['sign-in', 'sign-up']

const loggedInUsername = ref<string | null>(null)
const page = computed(() => PAGE_COMPONENTS[route.name])
const pageProps = computed(() =>
  AUTH_PAGES.includes(route.name) ? { loggedInUsername: loggedInUsername.value } : {},
)

onMounted(async () => {
  if (!AUTH_PAGES.includes(route.name)) return
  const session = await checkAuth()
  loggedInUsername.value = session.isLoggedIn ? session.username : null
})
</script>

<template>
  <div class="site">
    <SiteHeader :current-path="route.path" />
    <main class="site-main">
      <component :is="page" v-bind="pageProps" />
    </main>
    <SiteFooter />
  </div>
</template>

