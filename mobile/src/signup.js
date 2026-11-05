import * as verification from './screens/verification.js';
import * as vision from './signupVision.js';
import * as chemistry from './screens/chemistry.js';
import { editableFieldsForm, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } from './statsFields.js';

export const SIGNUP_STEPS = ['Vision', 'Stats', 'Chemistry', 'Verification'];

// Signup presentation for authenticated onboarding accounts.
// Initial persistence still uses the existing protected profile APIs.
export function createSignup({session, run, safe, finish, getBusy=()=>false}) {
  let step = 0, data = null, dirty = false, error = '', draft = [];
  let visionDraft = null;
  const key = () => SIGNUP_STEPS[step].toLowerCase();
  async function load() {
    data = step===3 ? await verification.load(session) : await session.get(`/api/v1/profile/${key()}`);
    if(step===0)data={...data,_signupVision:visionDraft||vision.empty()};
    dirty = false; error = ''; draft = [];
  }
  function ctx() {
    return {session, run, safe, data, busy:getBusy(), onboarding:true, patch(next) {
      data = next;
      if(step===0&&next._signupVision){visionDraft=next._signupVision;dirty=!!next._signupDirty;draft=[];}
      if(step===2){dirty=!next._saved;draft=[];}
      if (next._saved) { dirty = false; error = ''; draft = []; }
    }};
  }
  return {
    async begin() { step = 0; data = null; visionDraft=null; await load(); },
    async refreshStatus() {
      if(step!==3||!verification.canAutoRefresh(data)||document.activeElement?.closest?.('form')||document.querySelector('#avatar-consent:checked'))return false;
      const folds=[...document.querySelectorAll('.verification-fold[open]')].map(e=>e.id);
      try{const next=await verification.load(session);
      if(step!==3||!verification.canAutoRefresh(data))return false;
      if(!data.digilocker?.session?.identity&&next.digilocker?.session?.identity&&next.avatar?.can_capture&&!folds.includes('verification-avatar'))folds.push('verification-avatar');
      data={...next,_verificationFolds:folds};return true;}catch(error){if(error?.status===401)throw error;data={...data,_statusError:'Status updates paused. Check your connection.'};return step===3;}
    },
    render() {
      const body = !data ? '<p>Loading your profile…</p>'
        : step === 0 ? vision.render(ctx())
        : step === 2 ? chemistry.render(ctx())
        : step === 3 ? verification.render(ctx())
        : `<section class="card"><h1>Your Stats</h1><p>Tell us about yourself. Save your details to continue.</p>
          ${editableFieldsForm(data, safe, 'signup-stats')}
          ${(data.rows || []).filter(r=>!r.editable).map(r=>`<p class="hint">${safe(r.key.replaceAll('_',' '))}: ${safe(r.value)} · locked by your current journey</p>`).join('')}
          ${data._saved ? '<p class="save-note">Saved.</p>' : ''}
          ${data._error ? `<p class="warn">${safe(data._error)}</p>` : ''}</section>`;
      return `<section class="card signup-intro"><span class="eyebrow">CREATE YOUR PROFILE</span>
        <h2>Step ${step + 1} of 4 · ${SIGNUP_STEPS[step]}</h2>
        <p>Choose what matters to you, then complete your details and verification.</p>
        <ol class="signup-progress">${SIGNUP_STEPS.map((label,i)=>`<li ${i===step?'aria-current="step"':''}><span class="signup-step-number">${i+1}</span><span>${label}</span></li>`).join('')}</ol></section>
        ${body}${error ? `<p class="warn" role="alert">${safe(error)}</p>` : ''}
        <div class="signup-actions">
          ${step ? '<button id="signup-back" class="secondary" type="button">Previous step</button>' : ''}
          <button id="signup-next" class="primary" type="button">${step===3?'Go to Home':'Continue to '+SIGNUP_STEPS[step+1]}</button>
          ${step>0&&step<3?'<button id="signup-reload" class="text-button" type="button">Discard unsaved edits and reload this step</button>':''}
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
      if(step===1||step===2)root.querySelectorAll('form:not(#digilocker-start):not(#digilocker-complete):not(#signup-vision-form)').forEach(form=>{
        form.addEventListener('input', remember);
        form.addEventListener('change', remember);
      });
      if (step === 0) {
        vision.bind(root, ctx());
      }
      if (step === 2) chemistry.bind(root, ctx());
      if (step === 3) verification.bind(root, ctx());
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
        if(step===0&&delta===1){
          try{await vision.save(session,data);dirty=false;draft=[];error='';}
          catch(e){data={...data,_error:e.message};return;}
        }
        if (dirty) { error = 'Save your edits before continuing, or discard them using the link below.'; return; }
        if (step + delta === 4) { await finish(); return; }
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
