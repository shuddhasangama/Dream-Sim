import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { Session } from './session.js';
import { previewTransport } from './preview.js';
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
let challenge=null, phone='', busy=false, message='', dashboard=null, profile=null;
const safe = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render() {
  root.innerHTML = `<header><span class="mark">D</span><strong>DHASHU</strong><span class="beta">BETA</span></header>
    ${preview?'<aside class="preview">Local preview · no messages sent · code 123456</aside>':''}
    ${dashboard?home():signin()}
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
  root.querySelector('#reload')?.addEventListener('click',()=>run(load));
  root.querySelector('#logout')?.addEventListener('click',()=>run(async()=>{
    dashboard=null;profile=null;challenge=null;phone='';
    const revoked=await session.logout();
    message=revoked?'You have signed out.':'Signed out on this device. The server could not be reached to revoke the session; it will expire automatically.';
  }));
}
function signin() {
  return `<section class="intro"><span class="eyebrow">A LITTLE CLOSER</span><h1>${challenge?'Check your messages':'Welcome to<br>DhaShu.'}</h1><p>${challenge?'Enter the code sent to your approved number.':'A thoughtful space for your next chapter. Sign in with your invited beta number.'}</p></section>
    <form class="card"><label for="credential">${challenge?'Verification code':'Phone number'}</label>
    ${challenge?'<input id="credential" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" minlength="4" maxlength="10" required placeholder="Enter SMS code">':`<input id="credential" name="phone" type="tel" autocomplete="tel" maxlength="16" required placeholder="+91 followed by your number" value="${safe(phone)}">`}
    <button class="primary" ${busy?'disabled':''}>${challenge?'Sign in':'Send SMS code'} <span aria-hidden="true">→</span></button>
    ${challenge?`<button type="button" id="change" class="secondary" ${busy?'disabled':''}>Change number / request a new code</button>`:'<p class="hint">Include your country code. Beta access is by invitation.</p>'}</form>`;
}
function home() {
  const user=dashboard.user, stats=profile?.stats||{};
  const stage=String(user.journey_state||'').replaceAll('_',' ');
  return `<div class="toolbar"><span class="badge">${user.bgv_status==='verified'?'● Verified profile':'Verification pending'}</span><button id="logout" class="text-button" ${busy?'disabled':''}>Sign out</button></div>
    <section class="intro"><span class="eyebrow">YOUR CHAPTER · ${safe(stage)}</span><h1>${safe(user.display_name||'Your profile')}</h1><p>A little clarity for what comes next.</p></section>
    <section class="card guidance"><span class="eyebrow">NEXT FOR YOU</span><h2>${safe(dashboard.next_action?.headline||'Welcome back')}</h2><p>${safe(dashboard.next_action?.body||'Review your profile and take your next step when ready.')}</p></section>
    <section class="card"><h2>Your vision</h2><div class="chips">${(profile?.visions||[]).map(v=>`<span>${safe(v.key)} · ${safe(Array.isArray(v.stance)?v.stance.join(', '):v.stance)}</span>`).join('')||'<p>Your vision is still taking shape.</p>'}</div></section>
    <section class="card"><h2>Your details</h2><dl>${['age','city','profession','diet'].filter(k=>stats[k]!=null).map(k=>`<div><dt>${safe(k)}</dt><dd>${safe(stats[k])}</dd></div>`).join('')}</dl></section>
    <button id="reload" class="secondary" ${busy?'disabled':''}>Refresh dashboard</button>
    <p class="hint">This first beta build includes sign-in and your dashboard. Journey actions will follow.</p>`;
}
async function load() {
  const [nextDashboard,nextProfile]=await Promise.all([session.get('/api/v1/dashboard'),session.get('/api/v1/profile')]);
  dashboard=nextDashboard;profile=nextProfile;
}
async function run(action) {
  if(busy)return;busy=true;message='';render();
  try {await action();}
  catch(e) {message=e.message||'Something went wrong. Please try again.';if(e.status===401){dashboard=null;profile=null;}}
  finally {busy=false;render();}
}
render();
run(async()=>{if(await session.restore())await load();});
