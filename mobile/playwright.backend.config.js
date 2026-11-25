// cq-playwright: browser tests against the REAL local backend (tools/e2e_server.py:
// temporary SQLite, seeded synthetic members, local harness, simulated clock,
// providers mocked in that process). Never a deployed server.
//   npm run e2e:backend
// The existing preview-mode suite (playwright.config.js, mocked API) is unchanged.
import {defineConfig} from '@playwright/test';

const python = process.env.E2E_PYTHON || (process.platform === 'win32' ? '../.venv/Scripts/python.exe' : 'python');
const ci = !!process.env.CI;
// Default: Playwright's own Chromium (CI). Locally: E2E_CHANNEL=msedge uses installed Edge.
const browser = process.env.E2E_CHANNEL ? {channel: process.env.E2E_CHANNEL} : {};

export default defineConfig({
  testDir: './e2e-backend',
  timeout: 180_000,
  workers: 1,
  retries: ci ? 1 : 0,
  reporter: ci ? [['list'], ['html', {outputFolder: 'playwright-report/backend', open: 'never'}]] : 'list',
  use: {baseURL: 'http://127.0.0.1:5174', viewport: {width: 390, height: 844}, trace: ci ? 'retain-on-failure' : 'off', ...browser},
  webServer: [
    {command: `"${python}" ../tools/e2e_server.py --port 5000`, url: 'http://127.0.0.1:5000/api/v1/health',
     reuseExistingServer: false, timeout: 120_000},
    {command: 'npm run dev:local -- --port 5174 --strictPort', url: 'http://127.0.0.1:5174',
     reuseExistingServer: false, timeout: 120_000},
  ],
});
