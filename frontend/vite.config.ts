import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Optional runtime overrides for local serving; defaults keep the original
// loopback-only dev setup. Read via globalThis so this file stays type-safe
// without a Node type dependency:
//   LG_FRONTEND_HOST     default 127.0.0.1
//   LG_FRONTEND_PORT     default 5173
//   LG_API_PROXY_TARGET  default http://127.0.0.1:8000
const runtimeEnv =
  (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process?.env ?? {}

const devHost = runtimeEnv.LG_FRONTEND_HOST ?? '127.0.0.1'
const devPort = Number(runtimeEnv.LG_FRONTEND_PORT ?? 5173)
const apiProxyTarget = runtimeEnv.LG_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: devHost,
    port: devPort,
    proxy: {
      // Forward API calls to the local backend to avoid CORS in development.
      // changeOrigin rewrites the forwarded Host to the loopback target so the
      // backend sees a same-origin request; API auth headers are still required.
      '/api': { target: apiProxyTarget, changeOrigin: true },
    },
  },
})
