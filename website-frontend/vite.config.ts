import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/site-assets/',
  plugins: [vue()],
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_FLASK_ORIGIN || 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/vue')) return 'vue'
          return undefined
        },
      },
    },
  },
})

