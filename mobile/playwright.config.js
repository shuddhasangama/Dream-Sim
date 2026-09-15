import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',use:{baseURL:'http://127.0.0.1:5173',channel:'msedge',viewport:{width:390,height:844}},
  webServer:{command:'npm run dev -- --port 5173 --strictPort',url:'http://127.0.0.1:5173',reuseExistingServer:false},
  workers:1});
