import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // 输出到后端的静态目录，由 Flask 托管（static/react）
    outDir: resolve(__dirname, '../backend/static/react'),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      // 前端开发阶段把所有 /api 请求代理到后端
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
})
