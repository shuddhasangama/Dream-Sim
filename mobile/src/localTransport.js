// Browser + local backend transport (apiConfig kind 'local-proxy', `npm run dev:local`).
//
// Requests stay same-origin (http://127.0.0.1:5173/...) and the Vite dev
// server forwards them to the local Flask backend, so the backend's session
// cookie works with no CORS change. Paths are relative only: this transport
// cannot reach any other origin. Never sends an Authorization header.
export function sameOriginTransport(fetchImpl = (...args) => fetch(...args)) {
  return async (path, method = 'GET', data) => {
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) throw new Error('Same-origin paths only.');
    const init = { method, credentials: 'same-origin', redirect: 'manual', headers: { Accept: 'application/json' } };
    if (data !== undefined && method !== 'GET') {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(data);
    }
    const response = await fetchImpl(path, init);
    let body = null;
    try { body = await response.json(); } catch { body = null; }
    return { status: response.status, data: body };
  };
}
