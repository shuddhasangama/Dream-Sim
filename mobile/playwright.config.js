import {defineConfig} from '@playwright/test';
// Preview-mode suite (mocked API). Locally: installed Microsoft Edge, as before.
// CI (process.env.CI): Playwright's own Chromium, one retry, trace + HTML report
// kept on failure (uploaded as artifacts by .github/workflows/ci.yml).
const ci = !!process.env.CI;
const channel = process.env.E2E_CHANNEL ?? (ci ? '' : 'msedge');
export default defineConfig({testDir:'./e2e',
  use:{baseURL:'http://127.0.0.1:5173',...(channel?{channel}:{}),viewport:{width:390,height:844},trace:ci?'retain-on-failure':'off'},
  webServer:{command:'npm run dev -- --port 5173 --strictPort',url:'http://127.0.0.1:5173',reuseExistingServer:false},
  retries:ci?1:0,
  reporter:ci?[['list'],['html',{outputFolder:'playwright-report/preview',open:'never'}]]:'list',
  workers:1});
