import {defineConfig} from 'vite';
export default defineConfig({
  // road-fixes-clock-spec.md §7.8: DHASHU_SIMULATED_CLOCK is a build-time
  // convenience switch, not a security boundary — the server's own
  // journey/status simulated_clock flag is what actually gates the
  // controls (main.js never trusts this alone). Vite only exposes
  // VITE_-prefixed vars to client code by default; this lets the build
  // keep the same env var name the backend uses rather than a renamed one.
  envPrefix: ['VITE_', 'DHASHU_'],
  plugins:[{
  name:'local-preview-csp',apply:'serve',
  transformIndexHtml(html) {
    return html.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")
      .replace("connect-src 'self'", "connect-src 'self' ws://127.0.0.1:5173");
  },
}]});
