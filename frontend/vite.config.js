import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // WebSocket endpoint — must be proxied with ws:true so the browser
      // upgrade handshake is forwarded correctly to the FastAPI backend.
      '/api/v1/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
      // Detection analyze endpoint — YOLO inference can take minutes; extend timeout.
      '/api/v1/detection/analyze': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        proxyTimeout: 600000,   // 10 minutes
        timeout: 600000,
      },
      // All other /api calls forward normally.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        proxyTimeout: 120000,   // 2 minutes
        timeout: 120000,
      },
    },
  },
})
