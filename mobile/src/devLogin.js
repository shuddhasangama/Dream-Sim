// EMULATOR DEV BUILDS ONLY (npm run build:emulator / sync:emulator).
//
// "Pick a local user" for the Android emulator against the local backend's
// local harness (backend local_harness.py, DHASHU_LOCAL_HARNESS=1). main.js
// imports this module only inside `if (import.meta.env.MODE === 'emulator')`,
// so Vite drops it from every other build: release bundles contain neither
// these paths nor the picker (checked by tests/devLogin.test.js).
//
// The backend issues the same access/refresh tokens as the real login, so the
// rest of the app (Session, vault, refresh) works unchanged; only the refresh
// and logout endpoints are swapped to the harness ones.

export const DEV_PATHS = Object.freeze({
  users: '/api/v1/dev/users',
  loginAs: '/api/v1/dev/login-as',
  refresh: '/api/v1/dev/refresh',
  logout: '/api/v1/dev/logout',
});
export const PICKER_TITLE = 'Pick a local user';

export function enableHarnessSession(session) {
  session.paths = {...session.paths, refresh: DEV_PATHS.refresh, logout: DEV_PATHS.logout};
}

export async function loadUsers(session) {
  const data = await session.raw(DEV_PATHS.users);
  return Array.isArray(data?.users)
    ? data.users.filter(u => typeof u?.user_id === 'string').map(u => ({user_id: u.user_id, journey_state: String(u.journey_state || '')}))
    : [];
}

export async function loginAs(session, userId) {
  if (typeof userId !== 'string' || !/^[A-Za-z0-9_:.-]{1,64}$/.test(userId)) throw new Error('Choose a local user.');
  const epoch = session.generation;
  const result = await session.raw(DEV_PATHS.loginAs, 'POST', {user_id: userId});
  await session.accept(result, epoch);
}

// state: {users: null | [{user_id, journey_state}], error: string}
export function pickerHtml(state, safe) {
  const users = state?.users;
  const body = state?.error
    ? `<p class="hint">${safe(state.error)}</p><button type="button" class="text-button" id="dev-login-retry">Try again</button>`
    : users === null || users === undefined
      ? '<p class="hint">Loading local users…</p>'
      : users.length === 0
        ? '<p class="hint">No users in the local database. Run ..\\dev-local.ps1 seed.</p>'
        : `<div class="dev-login-list">${users.map(u => `<button type="button" class="secondary" data-dev-user="${safe(u.user_id)}">${safe(u.user_id)}${u.journey_state ? ` · ${safe(u.journey_state)}` : ''}</button>`).join('')}</div>`;
  return `<section class="card dev-login" aria-label="${PICKER_TITLE}"><h2>${PICKER_TITLE}</h2>`
    + `<p class="hint">Emulator dev build · local backend only · no SMS or password.</p>${body}</section>`;
}

export function bindPicker(root, {onPick, onRetry}) {
  root.querySelectorAll('[data-dev-user]').forEach(button => button.addEventListener('click', () => onPick(button.dataset.devUser)));
  root.querySelector('#dev-login-retry')?.addEventListener('click', onRetry);
}
