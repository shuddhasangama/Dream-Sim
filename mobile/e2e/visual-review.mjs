// Local browser acceptance. Start Vite on 5179, then run this file with Node.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const output=fileURLToPath(new URL('../../data/visual-review/',import.meta.url));
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:390,height:844}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/visual-review.html',r=>r.fulfill({contentType:'text/html',body:'<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/src/style.css"><link rel="stylesheet" href="/src/bone.css"><link rel="stylesheet" href="/src/brand-review.css"></head><body><div id="app"><header class="brandbar"><span class="brandmark"><span class="brand-name">DhaShu</span></span></header><main class="container" id="fixture"></main></div></body></html>'}));
await page.goto('http://127.0.0.1:5179/visual-review.html');
await page.evaluate(async()=>{
 const {createSignup}=await import('/src/signup.js');
 const safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
 const preset={signup_presets:[{key:'grow',choices:{Intimacy:['Emotional'],Kids:[],Cohabitate:[],'Travel together':[]},kids_intent:'want'},{key:'two',choices:{Intimacy:['Emotional'],Cohabitate:[],'Travel together':[]},kids_intent:'no'},{key:'explore',choices:{Intimacy:['Emotional'],'Travel together':[]},kids_intent:'undecided'},{key:'custom',choices:{Intimacy:['Emotional']},kids_intent:'undecided'}],signup_pillar_options:{Intimacy:['Emotional','Physical']}};
 const chemistry={activities:{},activity_options:['Cooking','Hiking','Running','Yoga'],custom_activities:[],partner_any:[],buckets:[['good','★','Already good at it'],['improve','↑','Want to improve'],['maybe','?','Never considered, so maybe'],['no','×','Not my cup of tea']]};
 const stats={modern:true,next_step:1,values:{},options:{gender:['female','male'],cities:[{name:'Bangalore'}],fields:{diet:['Vegetarian','Any'],cuisine:['Indian','Italian'],budget:['500–1000']},neighbourhoods_by_city:{Bangalore:[{id:'a',name:'Indiranagar'},{id:'b',name:'Koramangala'},{id:'c',name:'Whitefield'},{id:'d',name:'Jayanagar'}]}}};
 let step=0;window.savedStats=null;
 const session={get:async path=>path.endsWith('/signup/state')?{...stats,next_step:step}:path.endsWith('/vision')?preset:chemistry,put:async(path,body)=>{
  if(path.endsWith('/template')){step=1;return {schema_version:2,template_key:body.template,goals:Object.entries(body.pillars).map(([key,stance])=>({key,stance}))};}
  if(path.endsWith('/signup/stats')){window.savedStats=body;step=2;stats.values=body;return stats;}
  Object.assign(chemistry,body);return chemistry;
 }};
 const root=document.querySelector('#fixture');let wizard;
 const draw=()=>{root.innerHTML=wizard.render();wizard.bind(root);};
 wizard=createSignup({session,safe,run:async f=>{await f();draw();},finish:()=>{}});await wizard.begin();draw();
});
await page.locator('[data-signup-plan="two"]').click();
assert.equal(await page.locator('[data-signup-plan="two"]').getAttribute('aria-pressed'),'true');
await mkdir(output,{recursive:true});
await page.evaluate(()=>document.fonts.ready);
await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
await page.screenshot({path:output+'vision.png',fullPage:true});
await page.locator('#signup-next').click();
await page.locator('[name=age]').fill('29');await page.locator('[name=gender]').selectOption('female');await page.locator('[name=city]').selectOption('Bangalore');
assert.equal(await page.locator('#signup-next').count(),0);
await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
await page.screenshot({path:output+'stats.png',fullPage:true});
await page.locator('#signup-date-preferences>summary').click();
await page.locator('[name=s__neighbourhoods]').nth(0).check();await page.locator('[name=s__neighbourhoods]').nth(1).check();
await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
await page.screenshot({path:output+'date-preferences.png',fullPage:true});
await page.locator('#date-preferences-later').click();
await page.locator('#signup-stats-modern button[type=submit]').click();
await page.locator('#activities-form').waitFor();
assert.equal(await page.evaluate(()=>savedStats.age),29);
assert.deepEqual(await page.evaluate(()=>savedStats.fields.neighbourhoods),['a','b']);
await page.locator('.activity-row summary').filter({hasText:'Cooking'}).click();
await page.getByRole('radio',{name:'Cooking: Already good at it',exact:true}).check();
await page.locator('.activity-row summary').filter({hasText:'Hiking'}).click();
assert.equal(await page.locator('.activity-row[open]').count(),1);
await page.getByRole('radio',{name:'Hiking: Want to improve',exact:true}).check();
assert.match(await page.locator('.activity-row summary').filter({hasText:'Cooking'}).innerText(),/Already good at it/);
await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
await page.screenshot({path:output+'chemistry.png',fullPage:true});
for(const width of [320,390,430]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
await page.locator('#activities-form button[type=submit]').click();await page.getByText('Saved.',{exact:true}).waitFor();
assert.deepEqual(errors,[]);await browser.close();console.log('PASS: Vision selection, Stats save-and-continue, deferred date preferences, Chemistry persistence, three viewport widths.');
