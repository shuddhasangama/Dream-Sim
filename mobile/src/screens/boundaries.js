// Greeting preferences use the existing stage-gated own-profile API.
export async function load(session) {
  return session.get('/api/v1/profile/chemistry');
}

export function render({data, safe}) {
  if (!data) return '<section class="intro"><h1>Boundaries</h1><p>Loading…</p></section>';
  const selected = data.answers?.physical_boundary;
  return `<section class="intro"><h1>How would you like to be greeted?</h1>
    <p>A preference, not permission. You can change your mind at any time.</p></section>
    <section class="card"><form id="boundary-form">
    ${(data.options?.physical_boundary || []).map(value => `<label class="checkbox-row"><input type="radio" name="greeting" value="${safe(value)}" ${selected === value ? 'checked' : ''} required> ${safe(value.replaceAll('-', ' '))}</label>`).join('')}
    <button type="submit" class="primary">Save greeting preference</button>
    ${data.saved ? '<p role="status">Saved.</p>' : ''}</form></section>`;
}

export function bind(root, ctx) {
  root.querySelector('#boundary-form')?.addEventListener('submit', e => {
    e.preventDefault();
    const value = new FormData(e.target).get('greeting');
    ctx.run(async () => {
      const data = await ctx.session.put('/api/v1/profile/chemistry/entries/physical_boundary', {value});
      ctx.patch({...data, saved:true});
      await ctx.refreshJourney();
    });
  });
}
