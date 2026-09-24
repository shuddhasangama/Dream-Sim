import * as vision from './screens/vision.js';
import * as chemistry from './screens/chemistry.js';
import { editableFieldsForm, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } from './statsFields.js';

export const SIGNUP_STEPS = ['Vision', 'Stats', 'Chemistry'];

// A rehearsal of onboarding for an authenticated, already associated
// profile. The normal profile APIs remain the authority for edit eligibility.
export function createSignup({session, run, safe, finish}) {
  let step = 0, data = null, dirty = false, error = '', draft = [];
  const key = () => SIGNUP_STEPS[step].toLowerCase();
  async function load() {
    data = await session.get(`/api/v1/profile/${key()}`);
    dirty = false; error = ''; draft = [];
  }
  function ctx() {
    return {session, run, safe, data, onboarding:true, patch(next) {
      data = next;
      if (next._saved) { dirty = false; error = ''; draft = []; }
    }};
  }
  return {
    async begin() { step = 0; data = null; await load(); },
    render() {
      const body = !data ? '<p>Loading your profile…</p>'
        : step === 0 ? vision.render(ctx())
        : step === 2 ? chemistry.render(ctx())
        : `<section class="card"><h1>Your Stats</h1><p>Your existing values are filled in. Editing a verified field may reopen its check.</p>
          ${editableFieldsForm(data, safe, 'signup-stats')}
          ${(data.rows || []).filter(r=>!r.editable).map(r=>`<p class="hint">${safe(r.key.replaceAll('_',' '))}: ${safe(r.value)} · locked by your current journey</p>`).join('')}
          ${data._saved ? '<p class="save-note">Saved.</p>' : ''}
          ${data._error ? `<p class="warn">${safe(data._error)}</p>` : ''}</section>`;
      return `<section class="card signup-intro"><span class="eyebrow">GUIDED SIGN UP · EXISTING BETA PROFILE</span>
        <h2>Step ${step + 1} of 3 · ${SIGNUP_STEPS[step]}</h2>
        <p>We filled this in from your profile. Review it, save any edits, then continue. Existing journey and verification rules still apply.</p>
        <ol class="signup-progress">${SIGNUP_STEPS.map((label,i)=>`<li ${i===step?'aria-current="step"':''}>${label}</li>`).join('')}</ol></section>
        ${body}${error ? `<p class="warn" role="alert">${safe(error)}</p>` : ''}
        <div class="signup-actions">
          ${step ? '<button id="signup-back" class="secondary" type="button">Previous step</button>' : ''}
          <button id="signup-next" class="primary" type="button">${step===2?'Finish sign up':'Continue to '+SIGNUP_STEPS[step+1]}</button>
          <button id="signup-reload" class="text-button" type="button">Discard unsaved edits and reload this step</button>
        </div>`;
    },
    bind(root) {
      const inputs = ()=>[...root.querySelectorAll('form input, form select, form textarea')];
      if (dirty && draft.length) inputs().forEach((input,i)=>{
        if(draft[i]) { input.value=draft[i].value; input.checked=draft[i].checked; }
      });
      const remember = ()=>{
        dirty = true;
        draft = inputs().map(input=>({value:input.value,checked:input.checked}));
      };
      root.querySelectorAll('form').forEach(form=>{
        form.addEventListener('input', remember);
        form.addEventListener('change', remember);
      });
      if (step === 0) {
        vision.bind(root, ctx());
        const selected=root.querySelector('#change-pillar')?.value;
        root.querySelectorAll('.change-options').forEach(el=>el.hidden=el.dataset.pillar!==selected);
      }
      if (step === 2) chemistry.bind(root, ctx());
      root.querySelector('#signup-stats')?.addEventListener('submit', e=>{
        e.preventDefault();
        const form = e.target;
        run(async()=>{
          const {fields, errors, entered} = changedFields(form, data);
          if (errors) { data = {...withSubmittedValues(data, entered), _fieldErrors: errors, _saved:false}; return; }
          try {
            if (Object.keys(fields).length) await session.patch('/api/v1/profile/stats', {fields});
            const confirmed = await session.get('/api/v1/profile/stats');
            const values = Object.fromEntries(confirmed.rows.map(r=>[r.key,r.value]));
            if (!Object.keys(fields).every(k=>fieldsEqual(values[k],fields[k]))) throw new Error('Could not confirm your saved values. Reload and check.');
            data = {...confirmed, _saved:true}; dirty = false; error = ''; draft = [];
          } catch (e) {
            const parsed = fieldErrorsFromServer(e.message, data);
            data = {...withSubmittedValues(data, entered), _saved:false, _fieldErrors:parsed.byField, _error:parsed.general || e.message};
          }
        });
      });
      async function move(delta) {
        if (dirty) { error = 'Save your edits before continuing, or discard them using the link below.'; return; }
        if (step + delta === 3) { await finish(); return; }
        const previous = step;
        step += delta;
        try { await load(); } catch (e) { step = previous; throw e; }
      }
      root.querySelector('#signup-next')?.addEventListener('click', ()=>run(()=>move(1)));
      root.querySelector('#signup-back')?.addEventListener('click', ()=>run(()=>move(-1)));
      root.querySelector('#signup-reload')?.addEventListener('click', ()=>run(load));
    },
  };
}
