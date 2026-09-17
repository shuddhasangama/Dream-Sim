import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { Session, classify } from './session.js';
import { previewTransport } from './preview.js';
import { createNav, visibleTabs, labelFor, wireHardwareBack, wireKeyboardScroll } from './nav.js';
import * as reachScreen from './screens/reach.js';
import * as weekScreen from './screens/week.js';
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
};

// What every screen module receives. `data` is this screen's own GET result
// (or null for dashboard, which uses journey/profile directly); `patch`
// lets a screen update its own local copy of `data` after a mutation
// without a full reload (e.g. optimistic-ish but still server-confirmed —
// every screen actually assigns the server's own response, never a guess).
function buildCtx() {
  return {
    session, journey, profile, data: screenData, busy, safe,
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
  root.innerHTML = `<header><span class="mark">D</span><strong>DHASHU</strong><span class="beta">BETA</span></header>
    ${preview?'<aside class="preview">Local preview · no messages sent · code 123456</aside>':''}
    ${signedIn ? renderChrome(current, tabs) : signin()}
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
  return `<div class="toolbar">
      ${nav.depth>1?'<button id="back" class="text-button">← Back</button>':'<span></span>'}
      <button id="logout" class="text-button" ${busy?'disabled':''}>Sign out</button>
    </div>
    ${body}
    ${tabs.length?`<nav class="tabbar" aria-label="Sections">${tabs.map(t=>`<button class="tab ${t.key===current.key?'active':''}" data-nav="${safe(t.key)}">${safe(t.label)}</button>`).join('')}</nav>`:''}`;
}

function bindChrome(current) {
  root.querySelector('#back')?.addEventListener('click', goBack);
  root.querySelector('#logout')?.addEventListener('click',()=>run(async()=>{
    journey=null;profile=null;challenge=null;phone='';nav.resetTo('dashboard');
    const revoked=await session.logout();
    message=revoked?'You have signed out.':'Signed out on this device. The server could not be reached to revoke the session; it will expire automatically.';
  }));
  root.querySelectorAll('[data-nav]').forEach(btn=>btn.addEventListener('click',()=>navigateTo(btn.dataset.nav)));
  if (!screenBlocked && !screenUnavailable) screens[current.key]?.bind?.(root, buildCtx());
}

function signin() {
  return `<section class="intro"><span class="eyebrow">A LITTLE CLOSER</span><h1>${challenge?'Check your messages':'Welcome to<br>DhaShu.'}</h1><p>${challenge?'Enter the code sent to your approved number.':'A thoughtful space for your next chapter. Sign in with your invited beta number.'}</p></section>
    <form class="card"><label for="credential">${challenge?'Verification code':'Phone number'}</label>
    ${challenge?'<input id="credential" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" minlength="4" maxlength="10" required placeholder="Enter SMS code">':`<input id="credential" name="phone" type="tel" autocomplete="tel" maxlength="16" required placeholder="+91 followed by your number" value="${safe(phone)}">`}
    <button class="primary" ${busy?'disabled':''}>${challenge?'Sign in':'Send SMS code'} <span aria-hidden="true">→</span></button>
    ${challenge?`<button type="button" id="change" class="secondary" ${busy?'disabled':''}>Change number / request a new code</button>`:'<p class="hint">Include your country code. Beta access is by invitation.</p>'}</form>`;
}

// ── dashboard (unchanged content, now driven by journey/status) ──────────
function renderDashboard() {
  const user=journey.user, stats=profile?.stats||{};
  const stage=String(user.journey_state||'').replaceAll('_',' ');
  const indicator = journey.stage_indicator;
  const next = journey.next_action;
  return `<section class="intro"><span class="eyebrow">YOUR CHAPTER · ${safe(stage)}</span><h1>${safe(user.display_name||'Your profile')}</h1><p>A little clarity for what comes next.</p></section>
    <span class="badge">${user.bgv_status==='verified'?'● Verified profile':'Verification pending'}</span>
    ${indicator?.show?`<div class="stage-track" role="list" aria-label="${safe(indicator.label)}">${(indicator.stages||[]).map(s=>`<span role="listitem" class="stage-node ${safe(s.state)}">${safe(s.label)}</span>`).join('')}</div>`:''}
    <section class="card guidance"><span class="eyebrow">NEXT FOR YOU</span><h2>${safe(next?.headline||'Welcome back')}</h2><p>${safe(next?.body||'Review your profile and take your next step when ready.')}</p>
      ${next?.destination && next.destination.eligible && next.destination.request ? `<button id="next-action" class="primary" ${busy?'disabled':''}>${safe(next.cta||'Continue')} <span aria-hidden="true">→</span></button>` : ''}</section>
    <section class="card"><h2>Your vision</h2><div class="chips">${(profile?.visions||[]).map(v=>`<span>${safe(v.key)} · ${safe(Array.isArray(v.stance)?v.stance.join(', '):v.stance)}</span>`).join('')||'<p>Your vision is still taking shape.</p>'}</div></section>
    <section class="card"><h2>Your details</h2><dl>${['age','city','profession','diet'].filter(k=>stats[k]!=null).map(k=>`<div><dt>${safe(k)}</dt><dd>${safe(stats[k])}</dd></div>`).join('')}</dl></section>
    <button id="reload" class="secondary" ${busy?'disabled':''}>Refresh dashboard</button>`;
}
function bindDashboard() {
  root.querySelector('#reload')?.addEventListener('click',()=>run(load));
  root.querySelector('#next-action')?.addEventListener('click',()=>navigateTo(journey.next_action.destination.key));
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
  nav.push(key, params);
  run(() => loadScreen(key, params));
}
function goBack() {
  if (busy) return;
  if (nav.pop()) run(() => loadScreen(nav.current.key, nav.current.params));
}
async function loadScreen(key) {
  screenBlocked=null; screenUnavailable=false; screenData=null;
  if (key === 'dashboard') { await load(); return; }
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
