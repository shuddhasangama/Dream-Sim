'use strict';
const $ = id => document.getElementById(id);
const labels={overview:'Overview',users:'Users',sessions:'Sessions',checks:'Verification & errors',marketing:'Marketing',audit:'Access audit'};
let section='overview',page=1,query='',csrf='',busy=false,serial=0;
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function date(value){if(value===null||value===undefined||value==='')return '—';let d;if(typeof value==='number'||/^\d{10}(\.\d+)?$/.test(String(value)))d=new Date(Number(value)*1000);else d=new Date(value);if(Number.isNaN(d.valueOf()))return String(value);return new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}).format(d)+' IST';}
function human(key){const names={user_id:'Account',bgv_status:'Verification',auth_enabled:'Login enabled',verified_phone:'Phone verified',last_seen_at:'Last active',created_at:'Created',signup_flow:'Signup flow',account_last_active_at:'Account last active'};return names[key]||key.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());}
const timeFields=new Set(['created_at','updated_at','occurred_at','signed_in_at','access_expires_at','expires_at','revoked_at','last_seen_at','account_last_active_at','paused_until']);
function table(title,rows){const root=$('report');if(title)root.append(el('h2',title));if(!rows.length){root.append(el('p','No records to show.','empty'));return;}
 const wrap=el('div',undefined,'table-wrap'),t=el('table'),thead=el('thead'),tr=el('tr'),keys=Object.keys(rows[0]);for(const k of keys)tr.append(el('th',human(k)));thead.append(tr);t.append(thead);const body=el('tbody');
 for(const row of rows){const r=el('tr');for(const k of keys){const td=el('td'),v=row[k];td.dataset.field=k;let text=v===null||v===undefined?(timeFields.has(k)?'—':'Not recorded'):timeFields.has(k)?(k==='paused_until'&&v===0?'Manual resume required':date(v)):typeof v==='boolean'?(v?'Yes':'No'):String(v);
 if(section==='users'&&k==='user_id'){const b=el('button',text,'quiet');b.addEventListener('click',()=>detail(text));td.append(b);}else if(k==='status'||k==='state'||k==='bgv_status'){const cls=['verified','matched','Access valid'].includes(text)?'good':['pending','queued','Refresh available'].includes(text)?'warn':'';td.append(el('span',text,'status '+cls));}else td.textContent=text;r.append(td);}body.append(r);}t.append(body);wrap.append(t);root.append(wrap);
}
function render(data){const root=$('report');root.replaceChildren();
 if(data.metrics){const cards=el('div',undefined,'cards');for(const m of data.metrics){const c=el('div',undefined,'card');c.append(el('p',m.label,'metric-label'),el('p',m.value===null?'Not recorded':Number(m.value).toLocaleString('en-IN'),'metric'),el('p',m.note,'note'));cards.append(c);}root.append(cards);}
 if(data.groups)table('Journey stages',data.groups);if(data.funnel)table('Recorded signup milestones',data.funnel);
 if(data.account)table('Account',data.account);if(data.checks)table('Recent verification records',data.checks);
 if(data.rows)table('',data.rows);if(data.pauses)table('Active provider pauses',data.pauses);if(data.errors)table('Recent application errors',data.errors);
 if(data.cities)table('Registrations by city',data.cities);if(data.payments)table('Captured payments by mode',data.payments);
 if(data.unavailable)table('Integrations still needed',data.unavailable.map(x=>({metric:x,status:'Not connected'})));
 const notes=el('div',undefined,'notes');for(const note of data.notes||[])notes.append(el('p',note));root.append(notes);
 $('updated').textContent='Updated '+date(data.generated_at);$('pagination').hidden=!('has_more' in data);$('page-number').textContent='Page '+page;$('previous').disabled=page<=1;$('next').disabled=!data.has_more;
}
async function detail(user_id){try{const data=await api('/api/user-summary',{method:'POST',body:JSON.stringify({user_id})});render(data);$('page-title').textContent='User support summary';}catch(error){$('report-error').textContent=error.message;$('report-error').hidden=false;}}
async function api(path,opts={}){const response=await fetch(path,{credentials:'same-origin',...opts,headers:{'Content-Type':'application/json',...(opts.method?{'X-CSRF-Token':csrf}:{}),...opts.headers}});let data;try{data=await response.json();}catch{data={error:'The dashboard service could not return this report.'};}if(!response.ok){if(response.status===401&&path!=='/api/login')showLogin();throw new Error(data.error||'Request failed.');}return data;}
function showLogin(){$('workspace').hidden=true;$('login').hidden=false;$('report').replaceChildren();csrf='';}
async function load(){const requestId=++serial;busy=true;$('refresh').disabled=true;$('report-error').hidden=true;$('report').setAttribute('aria-busy','true');
 try{const data=section==='users'&&query?await api('/api/search/users',{method:'POST',body:JSON.stringify({q:query,page})}):await api('/api/reports/'+section+'?page='+page);if(requestId===serial)render(data);}
 catch(error){if(requestId===serial){$('report-error').textContent=error.message;$('report-error').hidden=false;$('report').replaceChildren();$('pagination').hidden=true;}}
 finally{if(requestId===serial){busy=false;$('refresh').disabled=false;$('report').setAttribute('aria-busy','false');}}
}
async function openWorkspace(){const identity=await api('/api/session');csrf=identity.csrf;if(identity.demo)document.querySelector('header .eyebrow').textContent='LOCAL PREVIEW · SAMPLE DATA';$('admin-email').textContent=identity.email;$('admin-role').textContent=identity.role;$('navigation').replaceChildren();section=identity.sections.includes('overview')?'overview':identity.sections[0];
 for(const name of Object.keys(labels)){if(!identity.sections.includes(name))continue;const b=el('button',labels[name]);b.dataset.section=name;b.addEventListener('click',()=>select(name));$('navigation').append(b);} $('login').hidden=true;$('workspace').hidden=false;select(section);}
function select(name){section=name;page=1;query='';$('user-search').value='';$('page-title').textContent=labels[name];$('search-area').hidden=name!=='users';for(const b of $('navigation').children)b.classList.toggle('active',b.dataset.section===name);load();}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;$('login-error').textContent='';try{await api('/api/login',{method:'POST',body:JSON.stringify({email:$('email').value,password:$('password').value,code:$('code').value})});$('password').value='';$('code').value='';await openWorkspace();}catch(error){$('login-error').textContent=error.message;}finally{b.disabled=false;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{method:'POST',body:'{}'});serial++;showLogin();}catch(error){$('report-error').hidden=false;$('report-error').textContent=error.message;}});
$('refresh').addEventListener('click',()=>{if(!busy)load();});$('search-form').addEventListener('submit',e=>{e.preventDefault();query=$('user-search').value.trim();page=1;load();});$('clear-search').addEventListener('click',()=>{query='';$('user-search').value='';page=1;load();});$('previous').addEventListener('click',()=>{if(page>1&&!busy){page--;load();}});$('next').addEventListener('click',()=>{if(!busy){page++;load();}});
openWorkspace().catch(()=>showLogin());
