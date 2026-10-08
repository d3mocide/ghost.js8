import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// The bridge is reached through the same origin in production (nginx proxies
// /ws and /api). In dev, Vite proxies to a locally running bridge.
const BRIDGE = process.env['GHOSTJS8_BRIDGE_URL'] ?? 'http://127.0.0.1:8073';

const proxy = {
  '/api': BRIDGE,
  '/ws': { target: BRIDGE.replace(/^http/, 'ws'), ws: true },
};

export default defineConfig({
  plugins: [svelte()],
  server: { proxy },
  preview: { proxy },
  // MapLibre loads its worker relative to its own module URL; pre-bundling breaks that.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  build: { target: 'es2023', sourcemap: true },
  test: {
    include: ['tests/unit/**/*.test.ts'],
    environment: 'node',
  },
});
