import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { Session, classify } from './session.js';
import { previewTransport } from './preview.js';
import { createNav, visibleTabs, labelFor, wireHardwareBack, wireKeyboardScroll } from './nav.js';
import * as reachScreen from './screens/reach.js';
import * as weekScreen from './screens/week.js';
import * as calendarScreen from './screens/calendar.js';
import * as planScreen from './screens/plan.js';
import * as ceremonyScreen from './screens/ceremony.js';
import * as debriefScreen from './screens/debrief.js';
import * as guruScreen from './screens/guru.js';
import * as visionScreen from './screens/vision.js';
import * as chemistryScreen from './screens/chemistry.js';
import * as relationshipScreen from './screens/relationship.js';
import * as roadScreen from './screens/road.js';
import { editableFieldsForm, groupedStatRows, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } from './statsFields.js';
import { createSignup } from './signup.js';
import { howItWorks, bindHowItWorks } from './howItWorks.js';
import { renderRehearsal, progressKey } from './rehearsal.js';
import './style.css';

const native = Capacitor.isNativePlatform();
const preview = import.meta.env.DEV && !Capacitor.isNativePlatform();
// road-fixes-clock-spec.md §7.8: a build-time convenience switch, never
// the sole gate (screens still require journey.simulated_clock from the
// server too — see week.js). Preview always allows it through: it never
// talks to a real backend, so there's nothing this would protect there.
const simulatedClockBuild = preview || String(import.meta.env.DHASHU_SIMULATED_CLOCK).toLowerCase() === 'true';
const Vault = registerPlugin('SessionVault');
const API = 'https://dream-sim-production.up.railway.app';
let temporary = null;
const vault = native ? {
  read:async () => (await Vault.read()).value,
  write:async value => Vault.write({value}),
  clear:async () => Vault.clear(),
} : {read:async()=>temporary,write:async value=>{temporary=value;},clear:async()=>{temporary=null;}};
const transport = preview ? previewTransport() : async (path,method,data,token) => {
  if (!native) throw new Error('Please use the installed DhaShu app.');
  return CapacitorHttp.request({url:API+path,method,data,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},
    connectTimeout:15000,readTimeout:15000,disableRedirects:true,responseType:'json'});
};
const session = new Session(transport,vault);
const root = document.querySelector('#app');
let challenge=null, phone='', busy=false, message='', journey=null, profile=null;
let authIntent='login', signupActive=false, screenDirty=false, clockPending=false;
const signup = createSignup({session, run, safe: value=>safe(value), finish: async()=>{
  await load(); signupActive=false; screenDirty=false; nav.resetTo('dashboard');
}});
// The currently-displayed non-dashboard screen's own data, and why it can't
// be shown when it can't (ineligible, or eligible but not on this build yet
// — §2's "api_available" distinction from §1's journey/status contract).
let screenData=null, screenBlocked=null, screenUnavailable=false;
// round3-fixes-spec.md §2/§3: no standalone Stats screen any more — the
// Dashboard edits its own Stats card inline. Non-null while that editor
// is open; holds GET /api/v1/profile/stats's own shape (plus, on a save
// failure, _saved/_error like chemistry.js).
let dashboardStats=null;
// Read-only Stats display's own rows (each carries the server's verified/
// declared `group`), loaded alongside journey+profile.
let statsSummary=null;
// round4-fixes-spec.md §2: Vision and Chemistry are set-once data, so they
// live on the Dashboard as collapsible sections (collapsed by default)
// rather than separate tabs. Each fold hosts the SAME screen module it
// always had — same render/bind, same validation, same save — fed its own
// data from the surface's own request path. `open` survives re-renders;
// `data` is loaded on first expand (and refreshed whenever the Dashboard
// itself is reloaded).
const FOLDS=['vision','chemistry'];
const newFolds=()=>Object.fromEntries(FOLDS.map(k=>[k,{open:false,data:null,error:null}]));
let folds=newFolds();
const safe = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const nav = createNav(render);

// ── screen registry (§1) ───────────────────────────────────────────────
// Every surface key not listed here still works via the generic fallback —
// it shows exactly what the server's read model returned, so nothing is
// ever a blank screen even before its bespoke UI exists. Bespoke screens are
// pure functions of ctx (below) — no import of main.js, so no import cycle.
const screens = {
  dashboard: { render: renderDashboard, bind: bindDashboard },
  reach: reachScreen,
  week: weekScreen,
  calendar: calendarScreen,
  plan: planScreen,
  ceremony: ceremonyScreen,
  debrief: debriefScreen,
  guru: guruScreen,
  vision: visionScreen,
  chemistry: chemistryScreen,
  relationship: relationshipScreen,
  journey: relationshipScreen,
  road: roadScreen,
};

// What every screen module receives. `data` is this screen's own GET result
// (or null for dashboard, which uses journey/profile directly); `patch`
// lets a screen update its own local copy of `data` after a mutation
// without a full reload (e.g. optimistic-ish but still server-confirmed —
// every screen actually assigns the server's own response, never a guess).
function buildCtx() {
  return {
    session, journey, profile, data: screenData, busy, safe,
    params: nav.current.params, simulatedClockBuild,
    run, navigateTo, goBack,
    patch(next) { screenData = next; },
    // For a mutation that can change eligibility/tabs (e.g. mutual interest
    // creating a lock-in, which closes REACH) — refetches journey/status
    // without touching this screen's own already-patched data.
    async refreshJourney() { journey = await session.get('/api/v1/journey/status'); },
  };
}

function render() {
  const signedIn = !!journey;
  const current = nav.current;
  const tabs = signedIn ? visibleTabs(journey.surfaces) : [];
  root.innerHTML = `<header class="brandbar">
      <span class="brandmark"><span class="brand-glyph" aria-hidden="true">D</span><span class="brand-name">DhaShu</span></span>
      ${signedIn ? `<span class="verify-pill ${journey.user.bgv_status==='verified'?'is-verified':'is-pending'}"><span class="verify-dot" aria-hidden="true"></span>${journey.user.bgv_status==='verified'?'Verified':'Not verified'}</span>` : ''}
    </header>
    ${preview?'<aside class="preview">Local preview · no messages sent · code 123456</aside>':''}
    ${signedIn ? signupActive ? `<main class="container">${signup.render()}</main>` : renderChrome(current, tabs) : `<main class="container">${signin()}</main>`}
    <p id="notice" role="status" class="notice">${safe(message)}</p>
    ${busy?'<div class="loading" role="status">Please wait…</div>':''}
    <footer>Connection. Clarity. Together.</footer>`;
  const form=root.querySelector('#signin-form');
  form?.addEventListener('submit', e=>{
    e.preventDefault(); if(busy)return;
    const fields=new FormData(form);
    if(challenge) {
      const code=String(fields.get('code')||'').trim();
      run(async()=>{
        await session.verify(challenge,code);challenge=null;screenDirty=false;await load();
        if(authIntent==='signup') { signupActive=true; await signup.begin(); }
      });
    } else {
      phone=String(fields.get('phone')||'').trim();
      run(async()=>{const result=await session.requestCode(phone);challenge=result.challenge_id;message='If this number is approved, a code will arrive shortly.';});
    }
  });
  root.querySelector('#tester-login')?.addEventListener('click',()=>{
    if(busy)return;
    phone=String(root.querySelector('input[name="phone"]')?.value||'').trim();
    run(async()=>{
      await session.testerLogin(phone); challenge=null; screenDirty=false; await load();
      if(authIntent==='signup') { signupActive=true; await signup.begin(); }
    });
  });
  root.querySelector('#change')?.addEventListener('click',()=>{challenge=null;message='';render();});
  root.querySelectorAll('[data-auth-intent]').forEach(button=>button.addEventListener('click',()=>{
    phone = root.querySelector('input[name="phone"]')?.value || phone;
    authIntent=button.dataset.authIntent; message=''; render();
  }));
  bindHowItWorks(root);
  if (signedIn && signupActive) signup.bind(root);
  else if (signedIn) bindChrome(current);
  if(signedIn && !signupActive) root.querySelectorAll('main form').forEach(form=>{
    form.addEventListener('input',()=>{screenDirty=true;});
    form.addEventListener('change',()=>{screenDirty=true;});
    form.addEventListener('click',e=>{if(e.target.closest('button[type="button"]'))screenDirty=true;});
  });
}

function renderChrome(current, tabs) {
  const screen = screens[current.key];
  const ctx = buildCtx();
  const body = screenBlocked ? blockedScreen(current.key)
    : screenUnavailable ? unavailableScreen(current.key)
    : screen ? screen.render(ctx)
    : genericScreen(current.key);
  const indicator = journey.stage_indicator;
  return `<div class="chrome-sticky">
      ${tabs.length?`<nav class="topnav" aria-label="Sections">${tabs.map(t=>`<button class="navlink ${t.key===current.key?'is-active':''}" data-nav="${safe(t.key)}">${safe(t.label)}</button>`).join('')}<button id="logout" class="navlink" ${busy?'disabled':''}>Sign out</button></nav>`:''}
      ${indicator?.show?`<div class="stage-bar" role="list" aria-label="${safe(indicator.label)}">${(indicator.stages||[]).map(s=>`<span role="listitem" class="stage-pip ${safe(s.state)}">${safe(s.label)}</span>`).join('')}</div>`:''}
    </div>
    <main class="container">
      ${renderRehearsal(journey.async_rehearsal, safe, journey.clock)}
      ${journey.accelerated_test?.enabled ? `<aside class="card accelerated-banner"><strong>Accelerated test · shared clock</strong><p>${safe(journey.clock.day)} ${String(journey.clock.hour).padStart(2,'0')}:00 · Week ${safe(journey.clock.week)} · ${journey.accelerated_test.finished?'30-minute run complete': '3 real minutes per checkpoint'}</p><p class="hint">${clockPending?'Time has advanced. Your unsaved screen is preserved. Save your edits, then refresh.':'Make your own choices at each step. Both partners must respond.'}</p><button id="refresh-clock" class="secondary" type="button">Refresh current step</button></aside>` : ''}
      <div class="toolbar">
        ${nav.depth>1?'<button id="back" class="text-button">← Back</button>':'<span></span>'}
      </div>
      ${body}
    </main>`;
}

function bindChrome(current) {
  root.querySelector('#rehearsal-slots')?.addEventListener('submit',(event)=>{
    event.preventDefault();
    const slots=new FormData(event.target).getAll('slot').map(value=>{
      const [day,meal_slot]=value.split('|'); return {day,meal_slot};
    });
    const path=journey?.async_rehearsal?.draft_availability?.path;
    if (!path) return;
    run(async()=>{await session.put(path,{slots});screenDirty=false;await reloadCurrent();message='Weekend availability saved.';});
  });
  root.querySelector('#rehearsal-ready')?.addEventListener('click',()=>{
    if (screenDirty) { message='Save your edits before advancing the test journey.'; render(); return; }
    const action=journey?.async_rehearsal?.request;
    if (!action || busy) return;
    run(async()=>{await session.post(action.path,action.body);await reloadCurrent();});
  });
  root.querySelector('#refresh-clock')?.addEventListener('click',()=>{
    if(screenDirty && !window.confirm('Refresh this screen and discard any unsaved edits?')) return;
    run(async()=>{await reloadCurrent();screenDirty=false;clockPending=false;});
  });
  root.querySelector('#back')?.addEventListener('click', goBack);
  root.querySelector('#logout')?.addEventListener('click',()=>run(async()=>{
    journey=null;profile=null;challenge=null;phone='';signupActive=false;authIntent='login';screenDirty=false;folds=newFolds();nav.resetTo('dashboard');
    const revoked=await session.logout();
    message=revoked?'You have signed out.':'Signed out on this device. The server could not be reached to revoke the session; it will expire automatically.';
  }));
  root.querySelectorAll('[data-nav]').forEach(btn=>btn.addEventListener('click',()=>navigateTo(btn.dataset.nav)));
  // Dashboard binds off journey/profile, not screenData, so it's always
  // ready. Screens with no journey/status surface of their own (e.g.
  // ceremony) load via screen.load and still need binding even though
  // screenData tracks the generic-surface path only. Every other screen's
  // bind() assumes real data (its own render() shows "Loading…" and offers
  // no interactive elements otherwise), so it must wait for screenData to
  // actually be populated.
  const screen = screens[current.key];
  const ready = current.key === 'dashboard' || screenData || screen?.load;
  if (!screenBlocked && !screenUnavailable && ready) screen?.bind?.(root, buildCtx());
}

function signin() {
  return `${howItWorks(safe)}<section class="intro"><span class="eyebrow">A LITTLE CLOSER</span><h1>${challenge?'Check your messages':'Welcome to<br>DhaShu.'}</h1><p>${challenge?'Enter the code sent to your approved number.':authIntent==='signup'?'Try guided sign up using your associated beta profile. Sign in, then review Vision, Stats and Chemistry.':'A thoughtful space for your next chapter. Sign in with your invited beta number.'}</p></section>
    ${!challenge?`<div class="auth-options" role="group" aria-label="Choose how to enter"><button type="button" class="${authIntent==='login'?'primary':'secondary'}" data-auth-intent="login" aria-pressed="${authIntent==='login'}">Log in</button><button type="button" class="${authIntent==='signup'?'primary':'secondary'}" data-auth-intent="signup" aria-pressed="${authIntent==='signup'}">Sign up</button></div>`:''}
    <form id="signin-form" class="card"><label for="credential">${challenge?'Verification code':'Phone number'}</label>
    ${challenge?'<input id="credential" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" minlength="4" maxlength="10" required placeholder="Enter SMS code">':`<input id="credential" name="phone" type="tel" autocomplete="tel" maxlength="16" required placeholder="+91 followed by your number" value="${safe(phone)}">`}
    <button class="primary" ${busy?'disabled':''}>${challenge?'Sign in':'Send SMS code'} <span aria-hidden="true">→</span></button>
    ${!challenge?`<button type="button" id="tester-login" class="secondary" ${busy?'disabled':''}>Continue as tester without SMS</button><p class="hint">Only for profiles explicitly enabled for OTP-free testing.</p>`:''}
    ${challenge?`<button type="button" id="change" class="secondary" ${busy?'disabled':''}>Change number / request a new code</button>`:'<p class="hint">Include your country code. Beta access is by invitation.</p>'}</form>`;
}

// ── dashboard, matching templates/dashboard.html's own field list ────────
// Every stat row the web dashboard shows, in its exact order — an
// editorial choice already made there, not one this client invents.
const DASHBOARD_STAT_ROWS = [
  ['age', 'Age', ''], ['height_cm', 'Height', ' cm'], ['weight_kg', 'Weight', ' kg'],
  ['waist_in', 'Waist', ' in'], ['income_band', 'Salary band', ''], ['diet', 'Diet', ''],
  ['education', 'Education', ''], ['nationality', 'Nationality', ''], ['profession', 'Profession', ''],
  ['religion', 'Religion', ''],
  ['has_children', 'Already has children', ''], ['children_count', 'Number of children', ''],
];
function renderDashboard() {
  const user=journey.user, stats=profile?.stats||{};
  const stage=String(user.journey_state||'').replaceAll('_',' ');
  const next = journey.next_action;
  return `${howItWorks(safe)}<section class="intro"><span class="eyebrow">Your file</span><h1>${safe(user.display_name||'Your profile')}</h1><div class="micro">Stage: ${safe(stage)}${journey.clock?.week!=null?` · Week ${safe(journey.clock.week)}`:''}</div></section>
    <section class="card guidance"><span class="eyebrow">NEXT FOR YOU</span><h2>${safe(next?.headline||'Welcome back')}</h2><p>${safe(next?.body||'Review your profile and take your next step when ready.')}</p>
      ${next?.destination && next.destination.eligible && next.destination.request ? `<button id="next-action" class="primary" ${busy?'disabled':''}>${safe(next.cta||'Continue')} <span aria-hidden="true">→</span></button>` : ''}</section>
    <section class="card"><div class="micro">Stats</div>
      ${dashboardStats ? `${editableFieldsForm(dashboardStats, safe, 'dashboard-stats-form')}
        <button id="cancel-edit-stats" class="secondary" type="button" style="margin-top:8px;">${dashboardStats._saved ? 'Done' : 'Cancel'}</button>
        ${dashboardStats._saved ? '<p class="save-note">Saved.</p>' : ''}
        ${dashboardStats._error ? `<p class="warn">${safe(dashboardStats._error)}</p>` : ''}`
        : `${groupedStatRows(statsSummary?.rows || DASHBOARD_STAT_ROWS.map(([k])=>({key:k,value:stats[k]})), DASHBOARD_STAT_ROWS, safe).trim() || '<p class="hint">Nothing on file yet.</p>'}
        <button id="edit-stats" class="secondary" type="button" style="margin-top:14px;">Edit stats</button>`}
    </section>
    ${FOLDS.map(renderFold).join('')}`;
}
function bindDashboard() {
  bindFolds();
  root.querySelector('#next-action')?.addEventListener('click',()=>navigateTo(journey.next_action.destination.key));

  root.querySelector('#edit-stats')?.addEventListener('click',()=>run(async()=>{
    dashboardStats = await session.get('/api/v1/profile/stats');
  }));
  root.querySelector('#cancel-edit-stats')?.addEventListener('click',()=>run(async()=>{ dashboardStats=null; }));

  root.querySelector('#dashboard-stats-form')?.addEventListener('submit',(e)=>{
    e.preventDefault();
    run(async()=>{
      const { fields, errors, entered } = changedFields(e.target, dashboardStats);
      if (errors) {
        dashboardStats = {...withSubmittedValues(dashboardStats, entered), _saved:false, _error:null, _fieldErrors:errors};
        return;
      }
      if (!Object.keys(fields).length) {
        dashboardStats = {...dashboardStats, _saved:false, _error:'Nothing changed yet — edit a field, then save.', _fieldErrors:null};
        return;
      }
      console.info('[dashboard] PATCH /api/v1/profile/stats request', {fields});
      try {
        await session.patch('/api/v1/profile/stats', {fields});
      } catch (err) {
        console.error('[dashboard] PATCH failed', err);
        const parsed = fieldErrorsFromServer(err.message, dashboardStats);
        dashboardStats = {...withSubmittedValues(dashboardStats, entered), _saved:false, _fieldErrors:parsed.byField, _error: parsed.general || (parsed.byField ? null : 'Could not save — try again.')};
        return;
      }
      // Same independent-reconfirm discipline as chemistry.js: a 200
      // does not prove the write landed as sent.
      let confirmed;
      try {
        confirmed = await session.get('/api/v1/profile/stats');
        console.info('[dashboard] confirmation GET response', confirmed);
      } catch (err) {
        console.error('[dashboard] confirmation GET failed', err);
        dashboardStats = {...withSubmittedValues(dashboardStats, fields), _saved:false, _error:'Saved, but could not confirm — reload to check.'};
        return;
      }
      const byKey = Object.fromEntries((confirmed.rows||[]).map(r=>[r.key,r.value]));
      const mismatched = Object.keys(fields).filter(k=>!fieldsEqual(byKey[k], fields[k]));
      if (mismatched.length) {
        console.error('[dashboard] MISMATCH: server read-back does not match what was submitted', {submitted:fields, read_back:byKey, mismatched});
        dashboardStats = {...withSubmittedValues(confirmed, fields), _saved:false, _error:"That didn't actually save — the server's own copy doesn't match. Try again, or reload to see what's really there."};
        return;
      }
      // Stay open with an explicit confirmation (same as chemistry.js)
      // rather than silently collapsing back to the read-only view —
      // "Cancel" below doubles as "Done" once there is something saved.
      // Refresh the read-only summary in the background so it is current
      // whenever the person does close the editor.
      dashboardStats = {...confirmed, _saved:true, _error:null, _fieldErrors:null};
      profile = await session.get('/api/v1/profile');
      statsSummary = confirmed;
    });
  });
}

// ── generic fallback (§1: never a blank screen) ───────────────────────────
function blockedScreen(key) {
  return `<section class="intro"><h1>${safe(labelFor(key))}</h1></section><section class="card"><p>${safe(screenBlocked)}</p></section>`;
}
function unavailableScreen(key) {
  return `<section class="intro"><h1>${safe(labelFor(key))}</h1></section><section class="card"><p>This isn't part of this beta build yet.</p></section>`;
}
function genericScreen(key) {
  return `<section class="intro"><h1>${safe(labelFor(key))}</h1></section><section class="card"><pre class="raw">${safe(JSON.stringify(screenData, null, 2))}</pre></section>`;
}

// ── navigation + loading ───────────────────────────────────────────────
function navigateTo(key, params) {
  if (busy) return;
  screenDirty=false;clockPending=false;
  // Vision/Chemistry no longer have screens of their own — any link to
  // them (Guru tiles, next-action CTAs) lands on the Dashboard with that
  // section expanded.
  if (FOLDS.includes(key)) { openFold(key); return; }
  screenData=null; screenBlocked=null; screenUnavailable=false; dashboardStats=null;
  nav.push(key, params);
  run(() => loadScreen(key, params));
}
function openFold(key) {
  screenData=null; screenBlocked=null; screenUnavailable=false; dashboardStats=null;
  if (nav.current.key !== 'dashboard') nav.resetTo('dashboard');
  folds[key].open = true;
  run(loadOpenFolds);
}
async function loadFold(key) {
  const f = folds[key], surface = journey?.surfaces?.find(s=>s.key===key);
  f.error = null;
  if (!surface || !surface.eligible || !surface.request) { f.data = null; return; }
  try { f.data = await session.get(surface.request.path); }
  catch (e) { f.data = null; f.error = classify(e).message; }
}
const loadOpenFolds = () => Promise.all(FOLDS.filter(k=>folds[k].open).map(loadFold));
function foldCtx(key) {
  const f = folds[key];
  return { ...buildCtx(), data: f.data, patch(next) { f.data = next; } };
}
function renderFold(key) {
  const f = folds[key], surface = journey.surfaces?.find(s=>s.key===key);
  if (!surface) return '';
  const body = !f.open ? ''
    : !surface.eligible ? `<p class="hint">${safe(surface.blocked_reason||"This isn't available right now.")}</p>`
    : !surface.request ? "<p class=\"hint\">This isn't part of this beta build yet.</p>"
    : f.error ? `<p class="warn">${safe(f.error)}</p>`
    : screens[key].render(foldCtx(key));
  return `<details class="dash-fold" data-fold="${key}" ${f.open?'open':''}><summary><strong>${safe(labelFor(key))}</strong></summary><div class="fold-body" data-fold-body="${key}">${body}</div></details>`;
}
function bindFolds() {
  for (const key of FOLDS) {
    const el = root.querySelector(`details[data-fold="${key}"]`);
    if (!el) continue;
    const f = folds[key];
    el.addEventListener('toggle', () => {
      if (el.open === f.open) return;
      f.open = el.open;
      if (f.open && !f.data) run(()=>loadFold(key));
    });
    const surface = journey.surfaces?.find(s=>s.key===key);
    if (f.open && f.data && surface?.eligible) screens[key].bind?.(el.querySelector('.fold-body'), foldCtx(key));
  }
}
function goBack() {
  if (busy) return;
  screenData=null; screenBlocked=null; screenUnavailable=false; dashboardStats=null;
  if (nav.pop()) run(() => loadScreen(nav.current.key, nav.current.params));
}
async function loadScreen(key, params) {
  screenBlocked=null; screenUnavailable=false; screenData=null;
  if (key === 'dashboard') { await load(); await loadOpenFolds(); return; }
  // A screen reached with its own params (e.g. ceremony, which has no
  // journey/status surface entry of its own — its real path always needs a
  // specific plan id) supplies its own loader instead of the generic
  // surface lookup below.
  const screen = screens[key];
  if (screen?.load) { screenData = await screen.load(session, params); return; }
  const surface = journey?.surfaces?.find(s=>s.key===key);
  if (!surface || !surface.eligible) { screenBlocked = surface?.blocked_reason || "This isn't available right now."; return; }
  if (!surface.request) { screenUnavailable = true; return; }
  screenData = await session.get(surface.request.path);
  // A screen may finish loading with a one-off setup step (Week: prepare).
  // Done here — on navigation — never from render().
  if (key === 'week') screenData = await weekScreen.ensurePrepared(session, screenData);
}
async function reloadCurrent() {
  await load();
  if (nav.current.key !== 'dashboard') await loadScreen(nav.current.key, nav.current.params);
}
async function load() {
  const [nextJourney,nextProfile]=await Promise.all([session.get('/api/v1/journey/status'),session.get('/api/v1/profile')]);
  journey=nextJourney;profile=nextProfile;
  if (journey?.async_rehearsal?.start_request) {
    const req=journey.async_rehearsal.start_request;
    await session.post(req.path,req.body);
    journey=await session.get('/api/v1/journey/status');
  }
  try { statsSummary=await session.get('/api/v1/profile/stats'); } catch { statsSummary=null; }
}
async function run(action) {
  if(busy)return;busy=true;message='';render();
  try {await action();}
  catch(e) {
    const c = classify(e);
    message = c.message;
    if (c.kind === 'auth') { journey=null;profile=null;signupActive=false;nav.resetTo('dashboard'); }
    else if (c.kind === 'conflict') { try { await reloadCurrent(); } catch {} }
  }
  finally {busy=false;render();}
}

wireKeyboardScroll();
// Poll server time on both native platforms. Never advance time from a device,
// overwrite an edited form, or interrupt a playing walkthrough.
async function refreshAcceleratedClock() {
  if (busy || !(journey?.accelerated_test?.enabled || journey?.async_rehearsal?.enabled) || signupActive || document.hidden) return;
  try {
    const next = await session.get('/api/v1/journey/status');
    if (progressKey(next) === progressKey(journey)) return;
    if (screenDirty || root.querySelector('video') && [...root.querySelectorAll('video')].some(v=>!v.paused)) {
      clockPending=true;
      const hint=root.querySelector('.accelerated-banner .hint, .rehearsal-banner .hint');
      if(hint) hint.textContent='Time has advanced. Your unsaved screen is preserved. Save your edits, then refresh.';
      return;
    }
    await run(async()=>{await reloadCurrent();clockPending=false;});
  } catch { /* Normal user actions report connectivity/auth errors. */ }
}
setInterval(refreshAcceleratedClock, 15000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshAcceleratedClock();});
if(native) import('@capacitor/app').then(({App})=>App.addListener('appStateChange',({isActive})=>{if(isActive)refreshAcceleratedClock();}));
wireHardwareBack(native, nav, () => {
  if (window.confirm('Exit DhaShu?')) import('@capacitor/app').then(({App})=>App.exitApp());
});
render();
run(async()=>{if(await session.restore())await load();});
