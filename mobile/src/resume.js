// feat-resume: what happens when the app goes to the background and comes back.
//
// Background: private screens are covered at once (also keeps them out of the
// OS app-switcher snapshot).
// Return: the session is checked BEFORE anything private is shown again —
// an access token that expired while away is refreshed first; if the session
// cannot be renewed (expired refresh, revoked, account locked) the member goes
// back to sign-in and the private screen is never re-shown. Only then is the
// current screen reloaded with fresh data.
// Calls are serialized: rapid background/foreground flips run one check at a time.

export function createResumeGuard({session, isSignedIn, setCovered, onResumed, onSignedOut}) {
  let chain = Promise.resolve();
  async function step(active) {
    if (!active) { if (isSignedIn()) setCovered(true); return 'covered'; }
    if (!isSignedIn()) { setCovered(false); return 'signed-out'; }
    setCovered(true);
    let ok = false;
    try { ok = await session.resume(); } catch { ok = false; }
    if (!ok) { await onSignedOut(); setCovered(false); return 'expired'; }
    try { await onResumed(); } finally { setCovered(false); }
    return 'resumed';
  }
  return {
    handle(active) {
      const next = chain.then(() => step(active), () => step(active));
      chain = next.catch(() => {});
      return next;
    },
  };
}
