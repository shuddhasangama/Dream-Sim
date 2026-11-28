// feat-delete: Settings -> Delete account, and the grace-period screen.
// The server decides everything (grace days, the due date); this only asks for a
// confirmation (password, or a code sent to the member's own phone) and shows state.
import { supportLine } from './config.js';
export function dueDate(epochSeconds) {
  return new Date(epochSeconds * 1000).toLocaleDateString('en-IN', {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'});
}

export function renderConfirm(state, safe) {
  const days = state?.grace_days ?? 30;
  return `<main class="container"><section class="card account-delete" aria-labelledby="delete-title">
    <h1 id="delete-title">Delete your account</h1>
    <p>Your profile is hidden at once and you are signed out on every device. After ${safe(days)} days everything is deleted
       permanently: profile, photos, avatars, Guru notes, files and sign-in details. Payment records the law requires are kept
       without your personal details. To recognise a returning member we keep only a one-way scrambled copy of your phone
       number (or email) and whether you left in good standing, for 2 years, then delete it.</p>
    <p>You can cancel by signing in within ${safe(days)} days.</p>
    ${state?._error ? `<p role="alert" class="warn">${safe(state._error)}</p>` : ''}
    ${state?.challenge_id
      ? `<form id="delete-code-form"><label>Code sent to your phone<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="10" required></label>
         <button class="secondary" type="submit">Delete my account</button></form>`
      : `<form id="delete-password-form"><label>Your password<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label>
         <button class="secondary" type="submit">Delete my account</button></form>
         <button type="button" id="delete-use-code" class="text-button">Use a code instead</button>`}
    <button type="button" id="delete-back" class="primary">Keep my account</button>
    ${supportLine()}
  </section></main>`;
}

export function renderScheduled(deletion, safe) {
  return `<main class="container"><section class="card account-delete" role="status">
    <h1>Your account is scheduled for deletion</h1>
    <p>Your account is scheduled for deletion on <strong>${safe(dueDate(deletion.due_at))}</strong>. Until then nobody can see your profile.</p>
    <p>Cancelling restores everything.</p>
    <button type="button" id="delete-cancel" class="primary">Cancel deletion</button>
    <button type="button" id="logout" class="secondary">Sign out</button>
    ${supportLine()}
  </section></main>`;
}

// One request per confirmation; the caller signs the member out locally afterwards
// (the server has already revoked every session).
export async function confirm(session, form) {
  return session.post('/api/v1/account/deletion', form);
}
