/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// The FastAPI server mounts the build output at /static and serves index.html at /.
// In development `npm run dev` proxies /api to a locally running server.
export default defineConfig({
  base: '/static/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../app/static',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8090', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
