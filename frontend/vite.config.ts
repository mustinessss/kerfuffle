import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const isPublicBuild = process.env.KERFUFFLE_FRONTEND_ZONE === 'public'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: isPublicBuild ? 'index.public.html' : 'index.html',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
