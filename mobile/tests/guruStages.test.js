import test from 'node:test';
import assert from 'node:assert/strict';
import { chipsFor, answerFor } from '../src/screens/guru.js';

test('Guru separates waiting, match, confirmed date and Debrief', () => {
  assert.deepEqual(chipsFor({topic_stage:'matching'}).map(x=>x.id), ['values','matching']);
  assert.ok(chipsFor({topic_stage:'match_available'}).some(x=>x.id==='match'));
  assert.ok(!chipsFor({topic_stage:'before_date'}).some(x=>x.id==='reflect'));
  assert.ok(chipsFor({topic_stage:'debrief'}).some(x=>x.id==='reflect'));
  assert.ok(!chipsFor({topic_stage:'post_debrief'}).some(x=>x.id==='reflect'));
  assert.ok(!chipsFor({topic_stage:'repeat_planning'}).some(x=>x.id==='match'));
});
test('every stage topic opens guidance; closed routes never become links', async () => {
  for (const stage of ['matching','match_available','planning','repeat_planning','agreement','before_date','debrief','post_debrief','relationship']) {
    const data={topic_stage:stage};
    assert.ok(chipsFor(data).length<=3);
    for(const topic of chipsFor(data)) {
      const answer=await answerFor(topic.id,data,[]);
      assert.ok(answer.answer.length>20);
      assert.equal(answer.actionLabel,null);
    }
  }
});
test('preparation uses supplied shared Chemistry, not demographic assumptions', async () => {
  const answer=await answerFor('prepare',{date_context:{prompts:[{title:'Enjoy together',body:'You both enjoy Cooking.'}]}},[]);
  assert.match(answer.answer,/Cooking/);
});
