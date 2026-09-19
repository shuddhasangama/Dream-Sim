// Chemistry (§2.6, spec item 11), ported from templates/chemistry.html.
// One bucket pick per activity, all from GET /api/v1/profile/chemistry's
// own activity_options/buckets/activities — never a hardcoded activity
// list or glyph set. The "overlap" card and the pacing/boundary answers
// that used to live on this page aren't in this endpoint's JSON shape
// (they're web-route-only additions) — the "what moved out of here" note
// below is kept as-is rather than inventing overlap data this build can't
// see.
//
// road-fixes-clock-spec.md §2 found and fixed a server-side bug here
// (evolution_api.chemistry_read forwarded the raw skills_json blob
// instead of its own `activities` key). round3-fixes-spec.md §1: that fix
// was reported done without ever independently re-reading the value back
// — "Saved" was shown on nothing stronger than "the PUT didn't throw",
// which cannot tell a genuine save apart from a 200 whose own response
// body silently doesn't match what was submitted. There is no client-side
// way to distinguish "the server's deployed code still has the old bug"
// from "the client's optimism is unearned" without actually reading the
// value back — so this now does exactly that: after the PUT succeeds, a
// SEPARATE GET confirms the server's own independent read-back matches
// what was submitted, and only THEN is "Saved" shown. Every request and
// response is logged (console.info/console.error) so a real device
// session can be inspected afterwards, not just this build's own preview.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Chemistry</h1></section><section class="card"><p>Loading…</p></section>';
  const { activities = {}, activity_options = [], buckets = [] } = data;

  return `<section class="intro"><span class="eyebrow">Chemistry</span><h1>What you'd actually do together</h1>
    <p class="lede">Hobbies, skills and activities. This is what Guru draws on when suggesting things to try together through the DREAM stages — the overlap matters more than the total.</p></section>

    <form id="activities-form">
      <section class="card">
        <div class="bucket-legend">${buckets.map((b) => `<span class="bucket-legend-item"><b>${safe(b[1])}</b> ${safe(b[2])}</span>`).join('')}</div>
        <div class="activity-table">${activity_options.map((a) => `<div class="activity-row">
          <span class="activity-name">${safe(a)}</span>
          <span class="activity-buckets">${buckets.map((b) => `<label class="bucket-pick" title="${safe(b[2])}"><input type="radio" name="act__${safe(a)}" value="${safe(b[0])}" ${activities[a] === b[0] ? 'checked' : ''}><span class="bucket-glyph b-${safe(b[0])}">${safe(b[1])}</span></label>`).join('')}</span>
        </div>`).join('')}</div>
        <button class="primary" type="submit">Save chemistry</button>
        ${data._saved ? '<p class="save-note">Saved.</p>' : ''}
        ${data._error ? `<p class="warn">${safe(data._error)}</p>` : ''}
      </section>
    </form>

    <section class="card"><div class="section-label">What moved out of here</div>
      <div class="hint">Intimacy expectations, openness to discussing sexual health and contraception, and your physical boundary preference used to sit on this page. They are not chemistry, and they should not be asked at sign-up. Boundaries open once a date is set; expectations open after your first date.</div>
    </section>`;
}

// Shallow map equality — {activity: bucket} has no nesting, so this is a
// real content comparison, not a reference check dressed up as one.
function activitiesEqual(a, b) {
  const ak = Object.keys(a || {}), bk = Object.keys(b || {});
  if (ak.length !== bk.length) return false;
  return ak.every((k) => a[k] === b[k]);
}

export function bind(root, ctx) {
  const { session, run, patch, data } = ctx;
  root.querySelector('#activities-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const picked = {};
      for (const [key, value] of form.entries()) picked[key.slice('act__'.length)] = value;

      console.info('[chemistry] PUT /api/v1/profile/chemistry/activities request', { activities: picked });
      let putResult;
      try {
        putResult = await session.put('/api/v1/profile/chemistry/activities', { activities: picked });
        console.info('[chemistry] PUT response', putResult);
      } catch (err) {
        // A validation_error (e.g. below the server's sort-at-least-N
        // minimum) carries the server's own explanation — shown here,
        // right by the button, instead of only in the page-level notice.
        // `activities: picked` keeps the user's own taps checked on
        // re-render — nothing was written, so there is nothing truer to
        // show, and re-picking twelve radios because one save failed is
        // its own kind of broken.
        console.error('[chemistry] PUT failed', err);
        patch({ ...data, activities: picked, _saved: false, _error: err.message || 'Could not save — try again.' });
        throw err;
      }

      // A 200 only proves the server accepted and answered the request —
      // it does not prove the write actually landed as sent (a stale
      // deployment could still return the old, wrong shape with a 200).
      // A fresh, independent GET is the same check "does it survive a
      // reload" would make manually, done automatically before "Saved"
      // is ever shown.
      let confirmed;
      try {
        confirmed = await session.get('/api/v1/profile/chemistry');
        console.info('[chemistry] confirmation GET response', confirmed);
      } catch (err) {
        console.error('[chemistry] confirmation GET failed', err);
        patch({ ...putResult, activities: picked, _saved: false, _error: 'Saved, but could not confirm — reload to check.' });
        return;
      }

      if (!activitiesEqual(confirmed.activities, picked)) {
        console.error('[chemistry] MISMATCH: server read-back does not match what was submitted', {
          submitted: picked, read_back: confirmed.activities,
        });
        // Keep the user's own picks checked (same reasoning as the PUT
        // failure above) — the error is explicit that this is NOT what
        // the server actually has, so nothing here is dishonest about
        // what's persisted, only about what's still on screen to retry.
        patch({ ...confirmed, activities: picked, _saved: false, _error: "That didn't actually save — the server's own copy doesn't match. Try again, or reload to see what's really there." });
        return;
      }

      patch({ ...confirmed, _saved: true, _error: null });
    });
  });
}
