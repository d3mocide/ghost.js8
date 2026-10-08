import { defineConfig, devices } from '@playwright/test';

// Browser smoke tests against the simulated stack (fake KiwiSDR + fake
// decoder-agent + real bridge) and a production build served by vite preview.
// Real decoding is covered by `make acceptance`, not here.
const BRIDGE_PORT = 28073;
const executablePath = process.env['PW_CHROMIUM_PATH'];

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 960 } },
    },
    { name: 'phone', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    {
      command: `DIRECTORY_URL=file://${process.cwd()}/../tools/fixtures/directory-sample.js KIWI_PORT=28070 AGENT_PORT=28074 BRIDGE_PORT=${String(BRIDGE_PORT)} PERIOD=3 ../tools/dev-stack.sh`,
      url: `http://127.0.0.1:${String(BRIDGE_PORT)}/healthz`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run build && GHOSTJS8_BRIDGE_URL=http://127.0.0.1:${String(BRIDGE_PORT)} npx vite preview --host 127.0.0.1 --port 4173 --strictPort`,
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
