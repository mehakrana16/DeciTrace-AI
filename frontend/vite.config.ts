import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server AND the production preview server both proxy /api to the
// FastAPI backend, so the SPA is always served same-origin and no CORS
// configuration is needed in development or in local demos.
const PROXY = {
  '/api': {
    target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: '127.0.0.1', proxy: PROXY },
  preview: { port: 4173, host: '127.0.0.1', proxy: PROXY },
  build: { outDir: 'dist', sourcemap: false },
})
