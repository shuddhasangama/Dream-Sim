// Chemistry (§2.6, spec item 11), ported from templates/chemistry.html.
// One bucket pick per activity, all from GET /api/v1/profile/chemistry's
// own activity_options/buckets/activities — never a hardcoded activity
// list or glyph set. The "overlap" card and the pacing/boundary answers
// that used to live on this page aren't in this endpoint's JSON shape
// (they're web-route-only additions) — the "what moved out of here" note
// below is kept as-is rather than inventing overlap data this build can't
// see.
//
// road-fixes-clock-spec.md §2: selections looked like they weren't
// persisting. The actual bug was server-side (evolution_api.chemistry_read
// forwarded the raw skills_json blob instead of its own `activities` key,
// so a save's own re-read never showed anything checked) — fixed there.
// The gap on THIS side was that a rejected save (e.g. the server's own
// "sort at least N activities" minimum) only ever surfaced in the
// page-level notice bar, far from the button that failed. `_saved`/
// `_error` are transient flags folded into the patched data so success
// and failure both show right next to the Save button, not just at the
// top of the screen.

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

export function bind(root, ctx) {
  const { session, run, patch, data } = ctx;
  root.querySelector('#activities-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const picked = {};
      for (const [key, value] of form.entries()) picked[key.slice('act__'.length)] = value;
      try {
        const result = await session.put('/api/v1/profile/chemistry/activities', { activities: picked });
        patch({ ...result, _saved: true, _error: null });
      } catch (err) {
        // A validation_error (e.g. below the server's sort-at-least-N
        // minimum) carries the server's own explanation — shown here,
        // right by the button, instead of only in the page-level notice.
        patch({ ...data, _saved: false, _error: err.message || 'Could not save — try again.' });
        throw err;
      }
    });
  });
}
