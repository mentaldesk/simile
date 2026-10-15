import { defineConfig } from 'vitest/config';

const server = 'http://127.0.0.1:8000';

export default defineConfig({
  build: {
    chunkSizeWarningLimit: 2000,
  },
  server: {
    proxy: {
      '/api': server,
      '/ws': { target: server, ws: true },
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
});
