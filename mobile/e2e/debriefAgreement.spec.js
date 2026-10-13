import {test,expect} from '@playwright/test';
test('discussion saves without accepting, and explicit acceptance refreshes the journey',async({page})=>{
  await page.goto('/');
  await page.evaluate(async()=>{
    const screen=await import('/src/screens/debrief.js');
    document.body.innerHTML='<main id="agreement-test"></main>';
    const root=document.querySelector('#agreement-test');
    window.calls=[];
    const ctx={safe:String,data:{plan_id:'plan:test',my_feedback:{},next_step:{needs_response:true,message:'Your match would like another date.',options:['continue','discuss','end']}},
      session:{post:async(path,body)=>{window.calls.push({path,body});return ctx.data;}},
      run:fn=>fn(),patch:()=>{},refreshJourney:async()=>{window.refreshed=true;},navigateTo:key=>{window.destination=key;}};
    root.innerHTML=screen.render(ctx);screen.bind(root,ctx);
  });
  await page.getByRole('button',{name:'Discuss with Guru',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.destination)).toBe('guru');
  expect(await page.evaluate(()=>window.calls[0].body)).toEqual({choice:'discuss'});
  await page.getByRole('button',{name:'Yes, another date',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.calls.length)).toBe(2);
  expect(await page.evaluate(()=>window.calls[1].body)).toEqual({choice:'continue'});
  expect(await page.evaluate(()=>window.refreshed)).toBe(true);
});
