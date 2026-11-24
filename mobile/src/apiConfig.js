// The ONE place that decides which server the app talks to.
//
// Used at build time by vite.config.js (to fail a bad build loudly and to
// fill in the CSP) and at run time by main.js (to pick the transport and the
// LOCAL / PREVIEW badge). Pure functions only, so node:test can cover them.
//
// Modes (Vite --mode). Not named 'local': Vite reserves .local for env files.
//   development  (npm run dev)       browser preview, in-browser mock data, no server
//   localbackend (npm run dev:local) browser + local Flask backend via the Vite proxy
//   emulator     (npm run build:emulator) native dev build -> http://10.0.2.2:5000
//   production   (npm run build)     release; VITE_API_BASE_URL must be a public https origin
//
// No production server address lives in this file: release builds get it
// only from VITE_API_BASE_URL (set in codemagic.yaml).

export const LOCAL_BACKEND_MODE = 'localbackend';
export const LOCAL_BACKEND = 'http://127.0.0.1:5000';
export const EMULATOR_DEFAULT = 'http://10.0.2.2:5000';
// Paths the dev server forwards to LOCAL_BACKEND in LOCAL_BACKEND_MODE. /pool and
// /login give the backend's cookie sign-in; /static serves that page's CSS.
export const LOCAL_PROXY_PATHS = ['/api', '/pool', '/login', '/logout', '/static'];
// The only hosts a non-release (dev) build may talk to.
export const DEV_HOSTS = new Set(['10.0.2.2', 'localhost', '127.0.0.1']);

export class ApiConfigError extends Error {
  constructor(message) { super(message); this.name = 'ApiConfigError'; }
}

function parseOrigin(raw, label) {
  if (typeof raw !== 'string' || raw.trim() === '') throw new ApiConfigError(`${label}: VITE_API_BASE_URL is missing.`);
  let url;
  try { url = new URL(raw.trim()); } catch { throw new ApiConfigError(`${label}: VITE_API_BASE_URL is not a valid URL.`); }
  if (url.username || url.password) throw new ApiConfigError(`${label}: VITE_API_BASE_URL must not contain credentials.`);
  if ((url.pathname !== '/' && url.pathname !== '') || url.search || url.hash) {
    throw new ApiConfigError(`${label}: VITE_API_BASE_URL must be an origin only (no path, query or fragment).`);
  }
  return url;
}

// True for loopback, emulator, private-network, link-local and local-only names.
export function isPrivateHost(hostname) {
  const host = String(hostname).toLowerCase().replace(/^\[|\]$/g, '').replace(/\.$/, '');
  if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal')) return true;
  if (host === '0.0.0.0' || host === '::' || host === '::1') return true;
  if (/^(fc|fd)[0-9a-f]{2}:/.test(host) || host.startsWith('fe80:') || host.startsWith('::ffff:')) return true;
  const ipv4 = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4) {
    const [a, b] = ipv4.slice(1, 3).map(Number);
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254)
      || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127);
  }
  if (/^\d+$/.test(host) || /^0x/i.test(host)) return true; // numeric host forms: refuse rather than decode
  return !host.includes('.'); // single-label names only resolve on a local network
}

// Release builds: https, public host, origin only. Throws otherwise.
export function validateReleaseBaseUrl(raw) {
  const url = parseOrigin(raw, 'Release build');
  if (url.protocol !== 'https:') throw new ApiConfigError('Release build: VITE_API_BASE_URL must use https.');
  if (isPrivateHost(url.hostname)) throw new ApiConfigError('Release build: VITE_API_BASE_URL must not be localhost, 10.0.2.2 or a private address.');
  return url.origin;
}

// Dev (non-release) native builds: only this laptop, as seen from the emulator or device.
export function validateDevBaseUrl(raw) {
  const url = parseOrigin(raw, 'Dev build');
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new ApiConfigError('Dev build: VITE_API_BASE_URL must be http or https.');
  if (!DEV_HOSTS.has(url.hostname)) throw new ApiConfigError(`Dev build: VITE_API_BASE_URL host must be one of ${[...DEV_HOSTS].join(', ')}.`);
  return url.origin;
}

// Build time (vite.config.js). Returns the origin baked into the bundle, or ''
// when the app talks to no remote origin (preview mock / same-origin proxy).
export function buildApiOrigin({ command, mode, baseUrl }) {
  if (mode === 'production') return validateReleaseBaseUrl(baseUrl);
  if (mode === 'emulator') return validateDevBaseUrl(baseUrl || EMULATOR_DEFAULT);
  if (mode === 'development' || mode === LOCAL_BACKEND_MODE) {
    if (command !== 'serve') throw new ApiConfigError(`Mode "${mode}" is for the dev server only; use "npm run build" or "npm run build:emulator".`);
    return '';
  }
  throw new ApiConfigError(`Unknown Vite mode "${mode}". Use development, ${LOCAL_BACKEND_MODE}, emulator or production.`);
}

// Run time (main.js). kind: preview | local-proxy | remote | unsupported.
export function resolveApiConfig({ dev, native, mode, baseUrl }) {
  if (mode === 'production') {
    return { kind: native ? 'remote' : 'unsupported', baseUrl: validateReleaseBaseUrl(baseUrl), badge: null, release: true };
  }
  if (!native && dev && mode === LOCAL_BACKEND_MODE) {
    return { kind: 'local-proxy', baseUrl: '', badge: 'LOCAL · backend 127.0.0.1:5000', release: false };
  }
  if (!native && dev) {
    return { kind: 'preview', baseUrl: '', badge: 'PREVIEW · Local preview · no messages sent · code 123456', release: false };
  }
  const origin = validateDevBaseUrl(baseUrl || EMULATOR_DEFAULT);
  return { kind: native ? 'remote' : 'unsupported', baseUrl: origin, badge: `LOCAL · ${new URL(origin).host}`, release: false };
}
