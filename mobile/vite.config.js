import {defineConfig, loadEnv} from 'vite';
import {buildApiOrigin, LOCAL_BACKEND, LOCAL_BACKEND_MODE, LOCAL_PROXY_PATHS} from './src/apiConfig.js';

const ENV_PREFIXES = ['VITE_', 'DHASHU_'];
// index.html carries this placeholder where the API origin belongs in the CSP.
const CSP_PLACEHOLDER = '__DHASHU_API_ORIGIN__';

export default defineConfig(({command, mode}) => {
  // Throws (failing the build or dev server loudly) when the server address is
  // missing or unsafe for this mode — see apiConfig.js. Release builds need
  // VITE_API_BASE_URL (codemagic.yaml); nothing is guessed.
  const apiOrigin = buildApiOrigin({command, mode, baseUrl: loadEnv(mode, process.cwd(), ENV_PREFIXES).VITE_API_BASE_URL});
  return {
    // road-fixes-clock-spec.md §7.8: DHASHU_SIMULATED_CLOCK is a build-time
    // convenience switch, not a security boundary — the server's own
    // journey/status simulated_clock flag is what actually gates the
    // controls (main.js never trusts this alone). Vite only exposes
    // VITE_-prefixed vars to client code by default; this lets the build
    // keep the same env var name the backend uses rather than a renamed one.
    envPrefix: ENV_PREFIXES,
    // The bundle gets exactly the validated origin ('' for preview/local proxy).
    define: {'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiOrigin)},
    // `npm run dev:local`: same-origin proxy to the local Flask backend so its
    // session cookie works without any CORS change on the backend.
    server: mode === LOCAL_BACKEND_MODE
      ? {proxy: Object.fromEntries(LOCAL_PROXY_PATHS.map(path => [path, {target: LOCAL_BACKEND, changeOrigin: false}]))}
      : undefined,
    plugins: [{
      name: 'api-origin-csp',
      transformIndexHtml: {
        order: 'pre',
        handler(html) {
          if (!html.includes(CSP_PLACEHOLDER)) throw new Error('index.html is missing the CSP API origin placeholder.');
          return html.replaceAll(' ' + CSP_PLACEHOLDER, apiOrigin ? ' ' + apiOrigin : '');
        },
      },
    }, {
      name: 'local-preview-csp',
      apply: 'serve',
      transformIndexHtml(html) {
        return html.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")
          .replace("connect-src 'self'", "connect-src 'self' ws://127.0.0.1:5173");
      },
    }],
  };
});
