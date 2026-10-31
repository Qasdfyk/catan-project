import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// The browser talks to one origin; nginx does the same routing in Docker.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.BACKEND_URL ?? 'http://localhost:8000',
      '/ws': { target: process.env.GATEWAY_URL ?? 'ws://localhost:8080', ws: true },
    },
  },
})
