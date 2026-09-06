import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5273,
    proxy: {
      '/api': 'http://127.0.0.1:8800',
      '/ws': {
        target: 'http://127.0.0.1:8800',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
