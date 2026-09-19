import test from 'node:test';
import assert from 'node:assert/strict';
import {Session} from '../src/session.js';
const token=n=>({access_token:'access-'+n,refresh_token:'refresh-'+n,expires_in:900});
const ok=data=>({status:200,data:{data,error:null}});
function setup(send,now=()=>0) {
  let value=null;
  const vault={read:async()=>value,write:async v=>{value=v;},clear:async()=>{value=null;}};
  return {session:new Session(send,vault,now),vault};
}
test('OTP verifies, persists only refresh, and authenticated reads use bearer',async()=>{
  const calls=[];const {session,vault}=setup(async(...args)=>{calls.push(args);return ok(args[0].endsWith('verify')?token(1):{challenge_id:'one'});});
  await session.requestCode('+919999999999');await session.verify('one','123456');await session.get('/api/v1/profile');
  assert.equal(await vault.read(),'refresh-1');assert.equal(calls[2][3],'access-1');
  await assert.rejects(session.requestCode('123'),/country code/);
});
test('simultaneous expired reads rotate refresh once',async()=>{
  let time=0,count=0;const {session}=setup(async(path)=>{
    if(path.endsWith('refresh')){count++;await new Promise(r=>setTimeout(r,10));return ok(token(2));}
    return ok({user_id:'owner'});
  },()=>time);
  await session.accept(token(1),0);time=901000;
  await Promise.all([session.get('/api/v1/me'),session.get('/api/v1/profile')]);assert.equal(count,1);
});
test('lost rotation response erases persistent credential and never retries',async()=>{
  let calls=0;const {session,vault}=setup(async()=>{calls++;throw Error('offline');});
  await session.accept(token(1),0);await assert.rejects(session.refresh());
  assert.equal(await vault.read(),null);assert.equal(session.tokens,null);assert.equal(calls,1);
});
test('restart consumes persisted refresh before sending it',async()=>{
  const {session,vault}=setup(async()=>{assert.equal(await vault.read(),null);return ok(token(2));});
  await vault.write('refresh-1');assert.equal(await session.restore(),true);assert.equal(await vault.read(),'refresh-2');
});
test('logout clears device credentials even when server is offline',async()=>{
  const {session,vault}=setup(async()=>{throw Error('offline');});await session.accept(token(1),0);
  assert.equal(await session.logout(),false);assert.equal(await vault.read(),null);assert.equal(session.tokens,null);
});
test('revoked access fails closed without replaying protected request',async()=>{
  let calls=0;const {session,vault}=setup(async()=>{calls++;return {status:401,data:{error:{message:'Revoked'}}};});
  await session.accept(token(1),0);await assert.rejects(session.get('/api/v1/profile'));assert.equal(calls,1);assert.equal(await vault.read(),null);
});
test('reject foreign URLs and malformed server responses',async()=>{
  const {session}=setup(async()=>({status:200,data:'<html>'}));
  await assert.rejects(session.raw('https://other.example'),/Invalid API path/);
  await assert.rejects(session.raw('/api/v1/me'),/Unexpected server response/);
});
test('logout waits for rotation then revokes the newly issued access token',async()=>{
  let sent;const {session,vault}=setup(async(path,method,body,access)=>{
    if(path.endsWith('refresh')){await new Promise(r=>setTimeout(r,10));return ok(token(2));}
    sent=access;return ok({logged_out:true});
  });
  await session.accept(token(1),0);await Promise.all([session.refresh(),session.logout()]);
  assert.equal(sent,'access-2');assert.equal(await vault.read(),null);
});

test('real journey IDs reach transport in raw and encoded form', async()=>{
  const calls=[];
  const {session}=setup(async path=>{calls.push(path);return ok({id:'date'});});
  for(const id of ['lockin:owner|partner:1', encodeURIComponent('lockin:owner|partner:1')]) {
    await session.raw(`/api/v1/lock-ins/${id}/calendar`);
    await session.raw(`/api/v1/date-plans/plan:${id}/agreement`);
  }
  assert.equal(calls.length,4);
});
test('path validation still rejects traversal, encoded separators and external URLs',async()=>{
  const {session}=setup(async()=>{assert.fail('Invalid path reached transport');});
  for(const path of ['https://other.example/api/v1/me','/api/v1/../me','/api/v1/%2e%2e/me','/api/v1/id%2Fother','/api/v1/id%5cother','/api/v1/id%253Aother','/api/v1/me?x=1','/api/v1/me#x','/api/v1/%zz']) {
    await assert.rejects(session.raw(path),/Invalid API path/);
  }
});
