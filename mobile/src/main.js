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
import * as statsScreen from './screens/stats.js';
import './style.css';

const native = Capacitor.isNativePlatform();
const preview = import.meta.env.DEV && !Capacitor.isNativePlatform();
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
// The currently-displayed non-dashboard screen's own data, and why it can't
// be shown when it can't (ineligible, or eligible but not on this build yet
// — §2's "api_available" distinction from §1's journey/status contract).
let screenData=null, screenBlocked=null, screenUnavailable=false;
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
  stats: statsScreen,
};

// What every screen module receives. `data` is this screen's own GET result
// (or null for dashboard, which uses journey/profile directly); `patch`
// lets a screen update its own local copy of `data` after a mutation
// without a full reload (e.g. optimistic-ish but still server-confirmed —
// every screen actually assigns the server's own response, never a guess).
function buildCtx() {
  return {
    session, journey, profile, data: screenData, busy, safe,
    params: nav.current.params,
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
    ${signedIn ? renderChrome(current, tabs) : `<main class="container">${signin()}</main>`}
    <p id="notice" role="status" class="notice">${safe(message)}</p>
    ${busy?'<div class="loading" role="status">Please wait…</div>':''}
    <footer>Connection. Clarity. Together.</footer>`;
  const form=root.querySelector('form');
  form?.addEventListener('submit', e=>{
    e.preventDefault(); if(busy)return;
    const fields=new FormData(form);
    if(challenge) {
      const code=String(fields.get('code')||'').trim();
      run(async()=>{await session.verify(challenge,code);challenge=null;await load();});
    } else {
      phone=String(fields.get('phone')||'').trim();
      run(async()=>{const result=await session.requestCode(phone);challenge=result.challenge_id;message='If this number is approved, a code will arrive shortly.';});
    }
  });
  root.querySelector('#change')?.addEventListener('click',()=>{challenge=null;message='';render();});
  if (signedIn) bindChrome(current);
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
      <div class="toolbar">
        ${nav.depth>1?'<button id="back" class="text-button">← Back</button>':'<span></span>'}
      </div>
      ${body}
    </main>`;
}

function bindChrome(current) {
  root.querySelector('#back')?.addEventListener('click', goBack);
  root.querySelector('#logout')?.addEventListener('click',()=>run(async()=>{
    journey=null;profile=null;challenge=null;phone='';nav.resetTo('dashboard');
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
  return `<section class="intro"><span class="eyebrow">A LITTLE CLOSER</span><h1>${challenge?'Check your messages':'Welcome to<br>DhaShu.'}</h1><p>${challenge?'Enter the code sent to your approved number.':'A thoughtful space for your next chapter. Sign in with your invited beta number.'}</p></section>
    <form class="card"><label for="credential">${challenge?'Verification code':'Phone number'}</label>
    ${challenge?'<input id="credential" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" minlength="4" maxlength="10" required placeholder="Enter SMS code">':`<input id="credential" name="phone" type="tel" autocomplete="tel" maxlength="16" required placeholder="+91 followed by your number" value="${safe(phone)}">`}
    <button class="primary" ${busy?'disabled':''}>${challenge?'Sign in':'Send SMS code'} <span aria-hidden="true">→</span></button>
    ${challenge?`<button type="button" id="change" class="secondary" ${busy?'disabled':''}>Change number / request a new code</button>`:'<p class="hint">Include your country code. Beta access is by invitation.</p>'}</form>`;
}

// ── dashboard, matching templates/dashboard.html's own field list ────────
// Every stat row the web dashboard shows, in its exact order — an
// editorial choice already made there, not one this client invents.
const DASHBOARD_STAT_ROWS = [
  ['age', 'Age', ''], ['height_cm', 'Height', ' cm'], ['weight_kg', 'Weight', ' kg'],
  ['waist_in', 'Waist', ' in'], ['income_band', 'Income band', ''], ['diet', 'Diet', ''],
  ['education', 'Education', ''], ['nationality', 'Nationality', ''], ['religion', 'Religion', ''],
];
function renderDashboard() {
  const user=journey.user, stats=profile?.stats||{};
  const stage=String(user.journey_state||'').replaceAll('_',' ');
  const next = journey.next_action;
  return `<section class="intro"><span class="eyebrow">Your file</span><h1>${safe(user.display_name||'Your profile')}</h1><div class="micro">Stage: ${safe(stage)}${journey.clock?.week!=null?` · Week ${safe(journey.clock.week)}`:''}</div></section>
    <section class="card guidance"><span class="eyebrow">NEXT FOR YOU</span><h2>${safe(next?.headline||'Welcome back')}</h2><p>${safe(next?.body||'Review your profile and take your next step when ready.')}</p>
      ${next?.destination && next.destination.eligible && next.destination.request ? `<button id="next-action" class="primary" ${busy?'disabled':''}>${safe(next.cta||'Continue')} <span aria-hidden="true">→</span></button>` : ''}</section>
    <section class="card"><div class="micro">Vision</div><div class="chip-row">${(profile?.visions||[]).map(v=>`<span class="chip">${safe(v.key)}${v.stance?' — '+safe(Array.isArray(v.stance)?v.stance.join(', '):v.stance):''}</span>`).join('')||'<p class="hint">Your vision is still taking shape.</p>'}</div></section>
    <section class="card"><div class="micro">Stats</div><div class="stat-rows">${DASHBOARD_STAT_ROWS.filter(([k])=>stats[k]!=null).map(([k,label,unit])=>`<div class="stat-row"><span>${safe(label)}</span><span>${safe(stats[k])}${unit}</span></div>`).join('')||'<p class="hint">Nothing on file yet.</p>'}</div>
      <button id="edit-stats" class="secondary" type="button" style="margin-top:14px;">Edit stats</button></section>`;
}
function bindDashboard() {
  root.querySelector('#next-action')?.addEventListener('click',()=>navigateTo(journey.next_action.destination.key));
  root.querySelector('#edit-stats')?.addEventListener('click',()=>navigateTo('stats'));
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
  screenData=null; screenBlocked=null; screenUnavailable=false;
  nav.push(key, params);
  run(() => loadScreen(key, params));
}
function goBack() {
  if (busy) return;
  screenData=null; screenBlocked=null; screenUnavailable=false;
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
}
async function reloadCurrent() {
  await load();
  if (nav.current.key !== 'dashboard') await loadScreen(nav.current.key, nav.current.params);
}
async function load() {
  const [nextJourney,nextProfile]=await Promise.all([session.get('/api/v1/journey/status'),session.get('/api/v1/profile')]);
  journey=nextJourney;profile=nextProfile;
}
async function run(action) {
  if(busy)return;busy=true;message='';render();
  try {await action();}
  catch(e) {
    const c = classify(e);
    message = c.message;
    if (c.kind === 'auth') { journey=null;profile=null;nav.resetTo('dashboard'); }
    else if (c.kind === 'conflict') { try { await reloadCurrent(); } catch {} }
  }
  finally {busy=false;render();}
}

wireKeyboardScroll();
wireHardwareBack(native, nav, () => {
  if (window.confirm('Exit DhaShu?')) import('@capacitor/app').then(({App})=>App.exitApp());
});
render();
run(async()=>{if(await session.restore())await load();});
