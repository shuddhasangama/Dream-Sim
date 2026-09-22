import {test,expect} from '@playwright/test';

async function login(page) {
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
}

test('Marriage adds all pillars; editors start collapsed; Week video plays',async({page})=>{
  await login(page);
  await page.locator('summary',{hasText:'Vision'}).click();
  await expect(page.locator('#detail-form')).toBeHidden();
  await expect(page.locator('#change-form')).toBeHidden();
  await page.getByRole('button',{name:'Choose Marriage'}).click();
  const chips=page.locator('.chips');
  await expect(chips).toContainText('Kids · Naturally');
  await expect(chips).toContainText('Travel together');
  await expect(chips).toContainText('Cohabitate');
  await expect(chips).not.toContainText('Adoption');
  await expect(chips).not.toContainText('Surrogacy');
  await page.locator('.topnav').getByRole('button',{name:'Week',exact:true}).click();
  await page.locator('details.tw-video summary').click();
  const video=page.locator('.tw-video-player');
  await expect(video).toHaveAttribute('src','/media/calendar-explainer.mp4');
  await video.evaluate(el=>el.play());
  await expect.poll(()=>video.evaluate(el=>el.currentTime)).toBeGreaterThan(0);
});

test('all four scales align labels, track and own-value marker under strict style CSP',async({page})=>{
  await login(page);
  await page.evaluate(()=>{
    const meta=document.createElement('meta');
    meta.httpEquiv='Content-Security-Policy';meta.content="style-src 'self'";
    document.head.append(meta);
  });
  await page.locator('.topnav').getByRole('button',{name:'REACH',exact:true}).click();
  await page.locator('details.more-filters').evaluate(el=>el.open=true);
  for(const width of [375,430]) {
    await page.setViewportSize({width,height:900});
    for(const [key,value] of [['age',38],['height_cm',169],['weight_kg',66],['waist_in',31]]) {
      const result=await page.locator(`[data-lever="${key}"]`).evaluate((card,value)=>{
        const track=card.querySelector('.slider-track').getBoundingClientRect();
        const marker=card.querySelector('.slider-self').getBoundingClientRect();
        const low=card.querySelector('.scale-min').getBoundingClientRect();
        const high=card.querySelector('.scale-max').getBoundingClientRect();
        const min=+card.dataset.min,max=+card.dataset.max;
        return {left:Math.abs(low.x+low.width/2-track.x),right:Math.abs(high.x+high.width/2-track.right),
          marker:Math.abs(marker.x+marker.width/2-(track.x+(value-min)/(max-min)*track.width)),
          vertical:Math.abs(marker.y+marker.height/2-(track.y+track.height/2))};
      },value);
      for(const error of Object.values(result)) expect(error,`${key} at ${width}`).toBeLessThan(1);
    }
  }
  await page.screenshot({path:'test-results/reach-scales.png',fullPage:true});
});
