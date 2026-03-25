import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'

export default defineConfig({
  plugins: [react(), cesium()],
  root: '.',
  build: {
    // Locally, we output into the Python app's static folder.
    // On Netlify, we want a normal Vite build directory for static hosting.
    outDir: process.env.NETLIFY ? 'dist' : '../src/web/static',
    emptyOutDir: process.env.NETLIFY ? true : false,
  },
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5001', changeOrigin: true },
    },
  },
})
