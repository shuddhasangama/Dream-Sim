import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { Session, classify } from './session.js';
import { previewTransport } from './preview.js';
import { createNav, primaryTabs, secondaryTabs, labelFor, wireHardwareBack, wireKeyboardScroll, PRIMARY_TAB_KEYS } from './nav.js';
import * as homeScreen from './screens/home.js';
import * as boundariesScreen from './screens/boundaries.js';
import * as reachScreen from './screens/reach.js';
import * as weekScreen from './screens/week.js';
import * as calendarScreen from './screens/calendar.js';
import * as planScreen from './screens/plan.js';
import * as ceremonyScreen from './screens/ceremony.js';
import * as identityScreen from './screens/identity.js';
import * as avatarScreen from './screens/avatar.js';
import * as verificationScreen from './screens/verification.js';
import * as debriefScreen from './screens/debrief.js';
import * as gateScreen from './screens/gate.js';
import * as afterDateScreen from './screens/afterDate.js';
import * as guruScreen from './screens/guru.js';
import * as visionScreen from './screens/vision.js';
import * as chemistryScreen from './screens/chemistry.js';
import * as relationshipScreen from './screens/relationship.js';
import * as roadScreen from './screens/road.js';
import { editableFieldsForm, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } from './statsFields.js';
import { createSignup } from './signup.js';
import { howItWorks, bindHowItWorks } from './howItWorks.js';
import { renderRehearsal, progressKey } from './rehearsal.js';
import './style.css';
import './bone.css';

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
let accountSecurity=null;
let passwordSetup=false, codeLogin=false;
let authIntent='login', signupActive=false, screenDirty=false, clockPending=false;
const signup = createSignup({session, run, getBusy:()=>busy, safe: value=>safe(value), finish: async()=>{
  if(profile?.stats?.signup_version===3)await session.post('/api/v1/signup/complete',{});
  await load(); signupActive=false; screenDirty=false; nav.resetTo('dashboard');
}});
// The currently-displayed non-dashboard screen's own data, and why it can't
// be shown when it can't (ineligible, or eligible but not on this build yet
// — §2's "api_available" distinction from §1's journey/status contract).
let screenData=null, screenBlocked=null, screenUnavailable=false;
// round3-fixes-spec.md §2/§3, then design_handoff_app_ui_pulse/README.md
// (Home's "Stats" ring): no standalone Stats screen — Home edits its own
// Stats ring inline. Non-null while that editor is open; holds
// GET /api/v1/profile/stats's own shape (plus, on a save failure,
// _saved/_error like chemistry.js).
let dashboardStats=null;
// Loaded alongside journey+profile — Home's Stats ring reads it directly.
let statsSummary=null;
// GET /api/v1/week's last response, loaded alongside journey+profile so
// Home's "Next up" card has a real source (design_handoff_app_ui_pulse/
// README.md) rather than inventing one. Read-only (§2.2) — never triggers
// week/prepare; only actually opening the Week tab does that.
let weekSummary=null;
// round4-fixes-spec.md §2: Vision and Chemistry's own data — eagerly
// loaded (see load() below) so Home's Vision/Chemistry rings have a real
// percentage the moment the screen first paints, not only once a person
// taps a ring open. `open` is purely the "is the edit flow expanded on
// Home right now" flag; `data`/`error` are this fold's own last GET.
const FOLDS=['vision','chemistry'];
const newFolds=()=>Object.fromEntries(FOLDS.map(k=>[k,{open:false,data:null,error:null}]));
let folds=newFolds();
// design_handoff_app_ui_pulse/README.md: the avatar (top-right of Home)
// opens a profile/settings sheet — Sign out lives there now, plus any
// stage-gated surface (Verify/Relationship/Journey) the floating tab bar
// has no room for. A plain UI overlay, not server state.
let avatarSheetOpen=false;
const safe = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Bundled up for Home's Stats ring, which reuses this module's editor
// exactly as the old Dashboard/REACH inline editors already did.
const statsFields = { editableFieldsForm, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues };

const nav = createNav(render);

// ── screen registry (§1) ───────────────────────────────────────────────
// Unimplemented surfaces show an honest availability message, never raw API data. Bespoke screens are
// pure functions of ctx (below) — no import of main.js, so no import cycle.
const screens = {
  verify: verificationScreen,
  avatar: avatarScreen,
  gate: gateScreen,
  after_date: afterDateScreen,
  escalations: afterDateScreen,
  next_level: afterDateScreen,
  expectations: boundariesScreen,
  dashboard: homeScreen,
  reach: reachScreen,
  week: weekScreen,
  calendar: calendarScreen,
  boundaries: boundariesScreen,
  plan: planScreen,
  ceremony: ceremonyScreen,
  identity: identityScreen,
  debrief: debriefScreen,
  guru: guruScreen,
  vision: visionScreen,
  chemistry: chemistryScreen,
  relationship: relationshipScreen,
  journey: relationshipScreen,
  road: roadScreen,
};
// design_handoff_app_ui_pulse/README.md: Vision, Stats and Chemistry are
// Home's three rings, not screens or tabs of their own any more — a link
// to any of them (Guru's next-action, a stale bookmark) lands on Home with
// that ring selected and its editor expanded. See openHomeRing() below.
const DASHBOARD_RING_KEYS = ['vision', 'chemistry', 'stats'];

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
    patch(next) { screenData = next; if(nav.current.key==='verify')screenDirty=false; },
    // For a mutation that can change eligibility/tabs (e.g. mutual interest
    // creating a lock-in, which closes REACH) — refetches journey/status
    // without touching this screen's own already-patched data.
    async refreshJourney() { journey = await session.get('/api/v1/journey/status'); },
    // Home-only extras (harmless on every other screen — nothing else
    // reads them). `folds`/`screens` are the SAME live objects main.js
    // itself holds, not copies, so a screen module's own patch() (e.g.
    // vision.js/chemistry.js's own bind()) mutating folds[key].data is
    // visible on the very next render without any extra plumbing here.
    folds, dashboardStats, statsSummary, weekSummary, screens, statsFields,
    openAvatarSheet() { avatarSheetOpen = true; render(); },
    toggleFold(key, open) { if (folds[key]) folds[key].open = open; },
    setDashboardStats(next) { dashboardStats = next; },
    getDashboardStats() { return dashboardStats; },
    async refreshProfile() {
      profile = await session.get('/api/v1/profile');
      try { statsSummary = await session.get('/api/v1/profile/stats'); } catch { /* Home shows what it already has. */ }
    },
  };
}

function render() {
  const signedIn = !!journey;
  const current = nav.current;
  const tabs = signedIn ? primaryTabs(journey.surfaces) : [];
  root.innerHTML = `<header class="brandbar">
      ${signedIn&&!signupActive&&!passwordSetup?'<button type="button" id="profile-settings" class="text-button" aria-label="Profile and settings">Settings</button>':''}<span class="brandmark"><span class="brand-glyph" aria-hidden="true"><svg viewBox="22 22 56 56"><path d="M34 28h14a22 22 0 0 1 0 44H34z" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="46" cy="50" r="5" fill="#E8735A"/></svg></span><span class="brand-name">DhaShu</span></span>
      ${signedIn&&!signupActive&&!passwordSetup ? `<span class="verify-pill ${journey.user.bgv_status==='verified'?'is-verified':'is-pending'}"><span class="verify-dot" aria-hidden="true"></span>${journey.user.bgv_status==='verified'?'Verified':'Not verified'}</span>` : ''}
    </header>
    ${preview?'<aside class="preview">Local preview · no messages sent · code 123456</aside>':''}
    ${passwordSetup ? `<main class="container"><section class="card"><h1>Set your password</h1><p>Next time, sign in with your phone number and this password.</p><form id="password-form"><label>Password<input name="password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><label>Confirm password<input name="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><p class="hint">Use 12 or more characters. A memorable passphrase works well.</p><button class="primary" ${busy?'disabled':''}>Save password and continue</button><button type="button" id="password-new-code" class="text-button">Request a new verification code</button></form></section></main>` : signedIn ? signupActive ? `<main class="container">${signup.render()}</main>` : renderChrome(current, tabs) : `<main class="container">${signin()}</main>`}
    <p id="notice" role="status" class="notice">${safe(message)}</p>
    ${busy?'<div class="loading" role="status">Please wait…</div>':''}
    ${signedIn && !signupActive ? '' : '<footer>Connection. Clarity. Together.</footer>'}`;
  root.querySelector('#password-form')?.addEventListener('submit',e=>{
    e.preventDefault();const f=new FormData(e.target),password=String(f.get('password')||'');
    if(password!==f.get('confirmation')){message='Passwords do not match.';root.querySelector('#notice').textContent=message;return;}
    run(async()=>{await session.setPassword(password);passwordSetup=false;await load();await resumeSignup();message='Password saved. You are signed in.';});
  });
  root.querySelector('#use-code')?.addEventListener('click',()=>{codeLogin=true;message='Use a code to set or reset your password.';render();});
  root.querySelector('#password-new-code')?.addEventListener('click',()=>{passwordSetup=false;codeLogin=true;challenge=null;journey=null;profile=null;message='Enter your phone number for a fresh code.';render();});
  const form=root.querySelector('#signin-form');
  form?.addEventListener('submit', e=>{
    e.preventDefault(); if(busy)return;
    const fields=new FormData(form);
    if(challenge) {
      const code=String(fields.get('code')||'').trim();
      run(async()=>{
        await session.verify(challenge,code);challenge=null;screenDirty=false;await load();
        passwordSetup=true;
        if(preview&&!new URLSearchParams(location.search).has('passwordFlow')){passwordSetup=false;await resumeSignup();}
      });
    } else {
      phone=String(fields.get('phone')||'').trim();
      if(authIntent==='login'&&!codeLogin){const password=String(fields.get('password')||'');run(async()=>{await session.passwordLogin(phone,password);await load();await resumeSignup();});}
      else run(async()=>{const result=authIntent==='signup'?await session.requestCode(phone,true):await session.recoveryCode(phone);challenge=result.challenge_id;message='If delivery is available for this contact, a code will arrive shortly.';});
    }
  });
  root.querySelector('#change')?.addEventListener('click',()=>{challenge=null;message='';render();});
  root.querySelectorAll('[data-auth-intent]').forEach(button=>button.addEventListener('click',()=>{
    phone = root.querySelector('input[name="phone"]')?.value || phone;
    authIntent=button.dataset.authIntent;codeLogin=false; message=''; render();
  }));
  root.querySelector('#profile-settings')?.addEventListener('click',()=>{avatarSheetOpen=true;render();});
  bindHowItWorks(root);
  if (signedIn && signupActive) signup.bind(root);
  else if (signedIn) bindChrome(current);
  if(signedIn && !signupActive) root.querySelectorAll('main form').forEach(form=>{
    form.addEventListener('input',()=>{screenDirty=true;});
    form.addEventListener('change',()=>{screenDirty=true;});
    form.addEventListener('click',e=>{if(e.target.closest('button[type="button"]'))screenDirty=true;});
  });
}

// design_handoff_app_ui_pulse/README.md ("Global changes"): the old text
// nav + stage-chip row are gone from every screen's own chrome — the
// floating tab bar and Home's own stepper (homeScreen.render) are what's
// left. What stays here, unchanged, is the toolbar's "← Back" (still only
// for a screen actually PUSHED on top of a tab — see navigateTo()'s
// resetTo-vs-push split below, which is what keeps depth at 1 for the four
// primary tabs) and the rehearsal/accelerated-test banners.
function renderChrome(current, tabs) {
  const screen = screens[current.key];
  const ctx = buildCtx();
  const body = screenBlocked ? blockedScreen(current.key)
    : screenUnavailable ? unavailableScreen(current.key)
    : screen ? screen.render(ctx)
    : genericScreen(current.key);
  return `<main class="container ${tabs.length ? 'has-tabbar' : ''}">
      ${renderRehearsal(journey.async_rehearsal, safe, journey.clock)}
      ${journey.accelerated_test?.enabled ? `<aside class="card accelerated-banner"><strong>Accelerated test · shared clock</strong><p>${safe(journey.clock.day)} ${String(journey.clock.hour).padStart(2,'0')}:00 · Week ${safe(journey.clock.week)} · ${journey.accelerated_test.finished?'30-minute run complete': '3 real minutes per checkpoint'}</p><p class="hint">${clockPending?'Your journey has changed. Your unsaved screen is preserved. Save your edits, then refresh.':'Make your own choices at each step. Both partners must respond.'}</p><button id="refresh-clock" class="secondary" type="button">Refresh current step</button></aside>` : ''}
      <div class="toolbar">
        ${nav.depth>1?'<button id="back" class="text-button">← Back</button>':'<span></span>'}
      </div>
      ${body}
    </main>
    ${tabs.length ? renderTabBar(current, tabs) : ''}
    ${renderAvatarSheet()}`;
}

function renderTabBar(current, tabs) {
  const icons={dashboard:'<path d="M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10"/>',reach:'<circle cx="12" cy="12" r="9"/><path d="m16 8-2 6-6 2 2-6z"/>',week:'<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M8 3v4M16 3v4M3.5 10h17"/>',guru:'<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4A2.5 2.5 0 0 1 4 13.5z"/>'};
  return `<nav class="p-tabbar" aria-label="Sections">${tabs.map(t=>`<button type="button" class="p-tab ${t.key===current.key?'is-active':''}" data-nav="${safe(t.key)}" ${t.key===current.key?'aria-current="page"':''}><svg class="p-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[t.key]||''}</svg>${safe(t.label)}</button>`).join('')}</nav>`;
}

function renderAvatarSheet() {
  if (!avatarSheetOpen) return '';
  const extra = secondaryTabs(journey.surfaces);
  return `<div class="p-sheet-backdrop" data-close-avatar></div>
    <div class="p-sheet" role="dialog" aria-label="Profile and settings">
      <div class="p-sheet-handle" aria-hidden="true"></div>
      <div class="p-sheet-name">${safe(journey.user.display_name || 'Your profile')}</div>
      <div class="p-sheet-stage">${safe(String(journey.user.journey_state||'').replaceAll('_',' '))}${journey.clock?.week!=null?` · Week ${safe(journey.clock.week)}`:''}</div>
      ${extra.length ? `<div class="p-sheet-links">${extra.map(t=>`<button type="button" class="p-sheet-link" data-nav="${safe(t.key)}">${safe(t.label)}</button>`).join('')}</div>` : ''}
      <button type="button" id="set-member-password" class="secondary">Set / reset login password</button>
      <button type="button" id="logout" class="secondary" ${busy?'disabled':''}>Sign out</button>
    </div>`;
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
  root.querySelector('[data-close-avatar]')?.addEventListener('click', () => { avatarSheetOpen=false; render(); });
  root.querySelector('#set-member-password')?.addEventListener('click',()=>run(async()=>{
    const status=await session.get('/api/v1/auth/password/status');
    if(status.can_set){passwordSetup=true;avatarSheetOpen=false;return;}
    const result=await session.recoveryCode(status.phone);
    challenge=result.challenge_id;phone=status.phone;codeLogin=true;authIntent='login';journey=null;profile=null;avatarSheetOpen=false;
    message='Enter the SMS code to set or reset your password.';
  }));
  root.querySelector('#logout')?.addEventListener('click',()=>run(async()=>{
    journey=null;profile=null;challenge=null;phone='';passwordSetup=false;codeLogin=false;signupActive=false;authIntent='login';screenDirty=false;folds=newFolds();weekSummary=null;avatarSheetOpen=false;nav.resetTo('dashboard');
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

async function resumeSignup() {
  if(authIntent==='signup'||journey.user.signup_version===3&&!journey.user.signup_submitted){
    if(preview||journey.user.journey_state==='onboarding'){signupActive=true;await signup.begin();}
    else {authIntent='login';message='Your account already exists. Your profile is available from Home.';}
  }
}
function signin() {
  const passwordLogin=authIntent==='login'&&!codeLogin&&!challenge;
  return `${howItWorks(safe)}<section class="intro"><span class="eyebrow">A LITTLE CLOSER</span><h1>${challenge?'Check your messages':'Welcome to<br>DhaShu.'}</h1><p>${challenge?'Enter your verification code.':authIntent==='signup'?'Start with your own phone number.':'Sign in with your password.'}</p></section>
    ${!challenge?`<div class="auth-options" role="group" aria-label="Choose how to enter"><button type="button" class="${authIntent==='login'?'primary':'secondary'}" data-auth-intent="login">Log in</button><button type="button" class="${authIntent==='signup'?'primary':'secondary'}" data-auth-intent="signup">Sign up</button></div>`:''}
    <form id="signin-form" class="card"><label for="credential">${challenge?'Verification code':authIntent==='signup'?'Phone number':'Phone number'}</label>
    ${challenge?'<input id="credential" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" maxlength="10" required>':`<input id="credential" name="phone" type="tel" autocomplete="username" maxlength="254" required placeholder="${authIntent==='signup'?'+91 followed by your number':'+91 followed by your number'}" value="${safe(phone)}">`}
    ${passwordLogin?'<label>Password<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label>':''}
    <button class="primary" ${busy?'disabled':''}>${challenge||passwordLogin?'Sign in':authIntent==='signup'?'Send SMS code':'Send recovery code'} <span aria-hidden="true">→</span></button>
    ${challenge?'<button type="button" id="change" class="secondary">Change contact / request a new code</button>':passwordLogin?'<button type="button" id="use-code" class="text-button">First password / forgot password? Use a code</button>':'<p class="hint">SMS requires your registered phone number and country code.</p>'}</form>`;
}

// ── generic fallback (§1: never a blank screen) ───────────────────────────
function blockedScreen(key) {
  return `<section class="intro"><h1>${safe(labelFor(key))}</h1></section><section class="card"><p>${safe(screenBlocked)}</p></section>`;
}
function unavailableScreen(key) {
  return `<section class="intro"><h1>${safe(labelFor(key))}</h1></section><section class="card"><p>This isn't part of this beta build yet.</p></section>`;
}
function genericScreen(key) {
  return `<section class="intro"><h1>${safe(labelFor(key))}</h1></section><section class="card"><p>This activity does not yet have a mobile screen. Your progress is saved. Return Home or open Guru for available next steps.</p></section>`;
}

// ── navigation + loading ───────────────────────────────────────────────
// design_handoff_app_ui_pulse/README.md: tab switching is instant and never
// grows a back-stack ("Tab switch: instant, preserving each tab's scroll
// position") — a primary tab reached with no extra params resets the whole
// stack onto it, exactly like tapping it fresh; a screen reached WITH
// params (or one that isn't a primary tab at all — calendar, plan, road…)
// still pushes/pops normally, so "← Back" keeps meaning something there.
function navigateTo(key, params) {
  if (busy) return;
  screenDirty=false;clockPending=false;
  if (DASHBOARD_RING_KEYS.includes(key)) { openHomeRing(key); return; }
  screenData=null; screenBlocked=null; screenUnavailable=false; dashboardStats=null; avatarSheetOpen=false;
  if (!params && PRIMARY_TAB_KEYS.includes(key)) nav.resetTo(key);
  else nav.push(key, params);
  run(() => loadScreen(key, params));
}
function openHomeRing(key) {
  screenData=null; screenBlocked=null; screenUnavailable=false; avatarSheetOpen=false;
  if (nav.current.key !== 'dashboard') nav.resetTo('dashboard');
  homeScreen.selectRing(key);
  if (key === 'stats') { dashboardStats=null; run(async () => { dashboardStats = await session.get('/api/v1/profile/stats'); }); return; }
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
function goBack() {
  if (busy) return;
  screenData=null; screenBlocked=null; screenUnavailable=false; dashboardStats=null;
  if (nav.pop()) run(() => loadScreen(nav.current.key, nav.current.params));
}
async function loadScreen(key, params) {
  screenBlocked=null; screenUnavailable=false; screenData=null;
  if (key === 'dashboard') { await load(); return; }
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
  try{accountSecurity=await session.get('/api/v1/auth/password/status');}catch{accountSecurity=null;}
  if (journey?.async_rehearsal?.start_request) {
    const req=journey.async_rehearsal.start_request;
    await session.post(req.path,req.body);
    journey=await session.get('/api/v1/journey/status');
  }
  try { statsSummary=await session.get('/api/v1/profile/stats'); } catch { statsSummary=null; }
  // design_handoff_app_ui_pulse/README.md: Home's Vision/Stats/Chemistry
  // rings need a real percentage the moment the screen first paints, not
  // only once a person taps one open — so these two load unconditionally
  // now (they used to wait for the fold to be opened).
  await Promise.all(FOLDS.map(loadFold));
  // Read-only (§2.2) — feeds Home's "Next up" card, never triggers
  // week/prepare (only actually opening the Week tab does that).
  try { weekSummary = await session.get('/api/v1/week'); } catch { weekSummary = null; }
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
  if (busy || !journey || document.hidden) return;
  if(signupActive){try{const changed=await signup.refreshStatus();if(changed&&signupActive&&!busy)render();}catch{}return;}
  // A newly captured private selfie is unsaved screen memory. App-resume or
  // clock polling must not replace its preview while the person reviews it.
  if (nav.current.key==='avatar' && screenData?._stagedSelfie) return;
  try {
    if(nav.current.key==='verify' && verificationScreen.canAutoRefresh(screenData) && !document.querySelector('#avatar-consent:checked') && !screenDirty && !document.activeElement?.closest?.('form')) {
      const nextVerification=await verificationScreen.load(session);
      if(nav.current.key==='verify' && !busy && !screenDirty && !document.activeElement?.closest?.('form') && JSON.stringify(nextVerification)!==JSON.stringify(screenData)) {screenData={...nextVerification,_verificationFolds:[...root.querySelectorAll('.verification-fold[open]')].map(e=>e.id)};render();}
    }
    const next = await session.get('/api/v1/journey/status');
    if (progressKey(next) === progressKey(journey)) return;
    if (nav.current.key==='reach' && !next.surfaces?.find(s=>s.key==='reach')?.eligible) {
      journey=next;screenDirty=false;clockPending=false;
      message='REACH is now paused for match review or your date. Unsaved filters were not applied.';
      nav.resetTo('dashboard');render();return;
    }
    if (screenDirty || root.querySelector('video') && [...root.querySelectorAll('video')].some(v=>!v.paused)) {
      clockPending=true;
      const hint=root.querySelector('.accelerated-banner .hint, .rehearsal-banner .hint');
      if(hint) hint.textContent='Your journey has changed. Your unsaved screen is preserved. Save your edits, then refresh.';
      return;
    }
    await run(async()=>{await reloadCurrent();clockPending=false;});
  } catch {
    if(nav.current.key==='verify'&&screenData&&!busy){screenData={...screenData,_statusError:'Status updates paused. Check your connection.'};render();}
  }
}
setInterval(refreshAcceleratedClock, 15000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshAcceleratedClock();});
if(native) import('@capacitor/app').then(({App})=>App.addListener('appStateChange',({isActive})=>{if(isActive)refreshAcceleratedClock();}));
wireHardwareBack(native, nav, () => {
  if (window.confirm('Exit DhaShu?')) import('@capacitor/app').then(({App})=>App.exitApp());
});
render();
run(async()=>{if(await session.restore()){await load();if(!preview){const status=await session.get('/api/v1/auth/password/status');if(!status.password_set){if(status.can_set)passwordSetup=true;else{phone=status.phone;codeLogin=true;journey=null;profile=null;message='Set your login password: request a fresh code once.';}return;}}if(profile?.stats?.signup_version===3&&!profile.stats.signup_submitted){signupActive=true;await signup.begin();}}});
