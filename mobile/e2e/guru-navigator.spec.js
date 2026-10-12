import {test,expect} from '@playwright/test';
async function mount(page,module,data){
 await page.goto('/');
 await page.evaluate(async({module,data})=>{
  const screen=await import(`/src/screens/${module}.js`);
  const root=document.createElement('main');root.className='container';document.body.replaceChildren(root);window.sent=[];
  const ctx={data,safe:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),journey:{user:{user_id:'owner'}},session:{post:async(path,body)=>{window.sent.push({path,body});return data.navigator;},put:async(path,body)=>{window.sent.push({path,body});return data;}},run:async fn=>{await fn();},patch:()=>{},refreshJourney:async()=>{}};
  root.innerHTML=screen.render(ctx);screen.bind(root,ctx);
 },{module,data});
}
test('Debrief adds short flags and permits three greens but only two reds',async({page})=>{
 await mount(page,'debrief',{plan_id:'plan-one',feedback_open:true,my_feedback:{green_flags:[],red_flags:[]},green_flag_options:['Listened','Kind','On time'],red_flag_options:['Late','Rude','Distracted']});
 await page.getByRole('button',{name:'Listened',exact:true}).click();
 await expect(page.getByRole('button',{name:'Save feedback'})).toBeDisabled();
 await page.getByLabel('Add a green flag').fill('Thoughtful');
 await page.locator('[data-add-flag="green"]').click();
 await page.getByRole('button',{name:'Kind',exact:true}).click();
 for(const name of ['Late','Rude','Distracted'])await page.getByRole('button',{name,exact:true}).click();
 await page.getByRole('button',{name:'Save feedback'}).click();
 const call=await page.evaluate(()=>window.sent[0]);
 expect(call.body.green_flags).toEqual(['Listened','Thoughtful','Kind']);expect(call.body.red_flags).toEqual(['Late','Rude']);
 await expect(page.getByLabel('Add a green flag')).toHaveAttribute('maxlength','16');
});
test('Guru separates private send and shared response and fits small screen',async({page})=>{
 await page.setViewportSize({width:375,height:812});
 await mount(page,'guru',{headline:'Choose date',topic_stage:'planning',navigator:{enabled:true,history:[{role:'user',text:'<script>private</script>'}],memories:[],remember:false,topics:[{id:'planning',label:'Plan your date together'}],shared_topics:[],discussions:[{id:'abc',topic:'planning',title:'Plan your date together',status:'active',revision:3,my_perspective:'',partner_perspective:'Saturday suits me',both_responded:false}]}});
 await page.getByLabel('Your thoughts').fill('My private question');await page.getByRole('button',{name:'Send privately'}).click();
 await page.locator('[data-shared-form="perspective"] textarea').fill('Sunday works better');await page.getByRole('button',{name:'Share perspective'}).click();
 const calls=await page.evaluate(()=>window.sent);
 expect(calls[0].path).toBe('/api/v1/guru/private');expect(calls[0].body.text).toBe('My private question');
 expect(calls[1]).toEqual({path:'/api/v1/guru/discussions/abc',body:{action:'perspective',revision:3,text:'Sunday works better'}});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:'test-results/guru-small-screen.png',fullPage:true});
});
