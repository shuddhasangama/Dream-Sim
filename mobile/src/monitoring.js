// Crash reporting for the app (mon-sentry). Active ONLY when the build sets
// VITE_SENTRY_DSN; otherwise Vite removes this code and the Sentry package from
// the bundle entirely (tests/monitoring.test.js checks the release bundle).
//
// Personal data never leaves the device: no default PII, no request bodies or
// headers, URLs without query strings, and every message/breadcrumb has emails
// and phone numbers masked. Tokens never appear in events.

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
// International (+country code) or Indian mobile (10 digits starting 6-9); not dates/timestamps.
const PHONE = /(?<![\w+])(?:\+\d{1,3}[\s-]?\d[\d\s-]{6,12}\d|[6-9]\d{4}[\s-]?\d{5})(?![\w-])/g;

export function mask(value) {
  return typeof value === 'string' ? value.replace(EMAIL, '[email]').replace(PHONE, '[phone]') : value;
}

function scrubDeep(value) {
  if (typeof value === 'string') return mask(value);
  if (Array.isArray(value)) return value.map(scrubDeep);
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, inner] of Object.entries(value)) {
      out[key] = /token|password|secret|authorization|cookie/i.test(key) ? '[filtered]' : scrubDeep(inner);
    }
    return out;
  }
  return value;
}

export function scrubEvent(event) {
  const copy = {...event};
  delete copy.user;
  if (copy.request) {
    const {url} = copy.request;
    copy.request = url ? {url: String(url).split('?')[0]} : {};
  }
  for (const key of ['message', 'exception', 'extra', 'contexts', 'breadcrumbs', 'tags']) {
    if (key in copy) copy[key] = scrubDeep(copy[key]);
  }
  return copy;
}

export async function startMonitoring(env = import.meta.env) {
  const dsn = env.VITE_SENTRY_DSN;
  if (!dsn) return false;
  const Sentry = await import('@sentry/browser');
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    environment: env.MODE,
    beforeSend: scrubEvent,
    beforeBreadcrumb: crumb => scrubDeep(crumb),
    tracesSampleRate: 0,
  });
  return true;
}
