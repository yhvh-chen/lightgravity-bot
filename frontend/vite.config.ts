import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// LG-002 owns this build/test wiring. The real application shell
// (frontend/src/app, components, api, views) is implemented by LG-011+.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // Forward API calls to the local backend to avoid CORS in development.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
  },
})
