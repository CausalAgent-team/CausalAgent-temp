import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/',
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['./tests/**/*.spec.ts'],
    restoreMocks: true,
  },
})

