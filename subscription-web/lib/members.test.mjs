import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {handleMembers,signing} from './members.mjs';
class D1 {
 constructor(){this.db=new DatabaseSync(':memory:');this.db.exec(readFileSync(new URL('../drizzle/0000_big_odin.sql',import.meta.url),'utf8'));this.db.exec(readFileSync(new URL('../drizzle/0001_personal_preferences.sql',import.meta.url),'utf8'));}
 prepare(sql){const db=this.db;return {bind(...args){return {first:async()=>db.prepare(sql).get(...args)||null,all:async()=>({results:db.prepare(sql).all(...args)}),run:async()=>({meta:{changes:Number(db.prepare(sql).run(...args).changes)}})};}};}
 async batch(items){this.db.exec('BEGIN');try{const out=[];for(const item of items)out.push(await item.run());this.db.exec('COMMIT');return out;}catch(e){this.db.exec('ROLLBACK');throw e;}}
}
const origin='https://members.example',secret='local-test-key-'.repeat(4);
function fixture(){const DB=new D1(),env={DB,MEMBER_BRIDGE_SECRET:secret,MEMBER_PUBLIC_ORIGIN:origin};return {DB,env,async call(path,body,opts={}){const raw=body===undefined?'':JSON.stringify(body),headers={origin,...opts.headers};if(opts.signed){const stamp=String(Math.floor(Date.now()/1000)),nonce=opts.nonce||crypto.randomUUID().replaceAll('-','');Object.assign(headers,{'x-morning-time':stamp,'x-morning-nonce':nonce,'x-morning-signature':await signing(secret,stamp,nonce,'POST',path,raw)});}const response=await handleMembers(new Request(origin+path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:raw}),env);return {status:response.status,data:await response.json(),cookie:response.headers.get('set-cookie')?.split(';')[0],headers:response.headers};}};}
const admin=(f,path,body={})=>f.call('/api/admin/'+path,body,{signed:true});
const bridge=(f,path,body={})=>f.call('/api/bridge/'+path,body,{signed:true});
async function invited(f,address='one@example.com'){const result=await admin(f,'invite',{email:address,topics:['path tracking']});assert.equal(result.status,201);const job=(await bridge(f,'claim')).data.job;assert.equal(job.email,address);return {user:result.data.user,token:new URLSearchParams(new URL(job.url).hash.slice(1)).get('invite'),job};}
async function active(f,address){const data=await invited(f,address);const login=await f.call('/api/exchange',{token:data.token,consent:true});assert.equal(login.status,200);return {...data,cookie:login.cookie};}
test('invitation is dormant until explicit consent; tokens are hashed/encrypted; single-use',async()=>{const f=fixture(),u=await invited(f);assert.equal((await bridge(f,'subscribers')).data.users.length,0);assert.equal((await f.call('/api/exchange',{token:u.token})).status,400);const r=await f.call('/api/exchange',{token:u.token,consent:true});assert.equal(r.status,200);assert.match(r.headers.get('set-cookie'),/HttpOnly; SameSite=Strict.*Secure/);assert.equal((await f.call('/api/exchange',{token:u.token,consent:true})).status,400);assert.equal((await bridge(f,'subscribers')).data.users.length,1);const rows=f.DB.db.prepare('SELECT * FROM member_tokens').all();assert.ok(!JSON.stringify(rows).includes(u.token));assert.ok(!JSON.stringify(f.DB.db.prepare('SELECT * FROM member_outbox').all()).includes(u.token));});
test('two mailboxes maximum, duplicate invite does not consume capacity',async()=>{const f=fixture();await invited(f);await invited(f,'two@example.com');assert.equal((await admin(f,'invite',{email:'three@example.com'})).status,409);assert.equal((await admin(f,'invite',{email:'ONE@example.com'})).status,200);assert.equal(f.DB.db.prepare('SELECT count(*) n FROM members').get().n,2);});
test('unknown login is generic and cannot enqueue email; same-origin required',async()=>{const f=fixture();assert.equal((await f.call('/api/login',{email:'unknown@example.com'})).status,200);assert.equal(f.DB.db.prepare('SELECT count(*) n FROM member_outbox').get().n,0);assert.equal((await f.call('/api/login',{email:'one@example.com'},{headers:{origin:'https://attacker.example'}})).status,403);assert.equal((await f.call('/api/admin/state',{})).status,403);assert.equal((await f.call('/api/me')).status,401);});
test('session acts only on its user; pause and admin pause stop delivery',async()=>{const f=fixture(),a=await active(f),b=await active(f,'two@example.com');const opts={headers:{cookie:a.cookie}};assert.equal((await f.call('/api/preferences',{id:b.user.id,name:'Alice',topics:['active suspension']},opts)).status,200);assert.equal(f.DB.db.prepare('SELECT name FROM members WHERE id=?').get(b.user.id).name,'同学');await f.call('/api/status',{action:'pause'},opts);assert.equal((await bridge(f,'subscribers')).data.users.length,1);await f.call('/api/status',{action:'resume'},opts);await admin(f,'pause',{id:a.user.id,paused:true});assert.equal((await f.call('/api/status',{action:'resume'},opts)).status,409);assert.equal((await bridge(f,'active',{id:a.user.id,generation:f.DB.db.prepare('SELECT generation FROM members WHERE id=?').get(a.user.id).generation})).data.active,false);});
test('unsubscribe revokes sessions and pending mail, old links fail after reinvite',async()=>{const f=fixture(),a=await active(f);const url=(await bridge(f,'subscribers')).data.users[0].unsubscribe_url,token=new URLSearchParams(new URL(url).hash.slice(1)).get('unsubscribe');assert.equal((await f.call('/api/unsubscribe',{token})).status,200);assert.equal((await f.call('/api/me',undefined,{headers:{cookie:a.cookie}})).status,401);assert.equal((await bridge(f,'subscribers')).data.users.length,0);await admin(f,'invite',{email:'one@example.com'});assert.equal((await f.call('/api/unsubscribe',{token})).status,400);});
test('expired invitation fails and bridge requests cannot replay',async()=>{const f=fixture(),a=await invited(f);f.DB.db.exec('UPDATE member_tokens SET expires_at=1');assert.equal((await f.call('/api/exchange',{token:a.token,consent:true})).status,400);const nonce='a'.repeat(32);assert.equal((await f.call('/api/admin/state',{}, {signed:true,nonce})).status,200);assert.equal((await f.call('/api/admin/state',{}, {signed:true,nonce})).status,409);});
test('claimed email is never automatically reclaimed even after ambiguous result',async()=>{const f=fixture(),a=await invited(f);assert.equal((await bridge(f,'claim')).data.job,null);await bridge(f,'finish',{id:a.job.id,status:'unknown'});assert.equal((await bridge(f,'claim')).data.job,null);assert.equal((await admin(f,'state')).data.outbox[0].status,'unknown');});
test('logout revokes cookie; outage fails closed',async()=>{const f=fixture(),a=await active(f);await f.call('/api/logout',{}, {headers:{cookie:a.cookie}});assert.equal((await f.call('/api/me',undefined,{headers:{cookie:a.cookie}})).status,401);const response=await handleMembers(new Request(origin+'/api/me'),{});assert.equal(response.status,503);});

test('personal preferences persist per user and revoke stale sending snapshots',async()=>{
 const f=fixture(),a=await active(f),b=await active(f,'two@example.com'),opts={headers:{cookie:a.cookie}};
 const before=(await bridge(f,'subscribers')).data.users.find(u=>u.id===a.user.id);
 assert.equal(before.send_time,'08:00');assert.equal(before.difficulty,'beginner');
 const r=await f.call('/api/preferences',{name:'Alice',topics:['path tracking'],send_time:'23:55',frequency:'custom',weekdays:[6,0,6],difficulty:'advanced',length:'concise',preferences_version:1},opts);
 assert.equal(r.status,200);assert.deepEqual(r.data.user.weekdays,[0,6]);assert.equal(r.data.user.preferences_version,2);assert.ok(r.data.user.schedule_effective_at>0);
 assert.equal((await bridge(f,'active',{id:a.user.id,generation:before.generation,preferences_version:1})).data.active,false);
 assert.equal((await bridge(f,'active',{id:a.user.id,generation:before.generation,preferences_version:2})).data.active,true);
 assert.equal(f.DB.db.prepare('SELECT send_time FROM members WHERE id=?').get(b.user.id).send_time,'08:00');
 assert.equal((await f.call('/api/preferences',{topics:['path tracking'],preferences_version:1},opts)).status,409);
});
test('invalid clocks, empty custom days, and unknown learning modes never persist',async()=>{
 const f=fixture(),a=await active(f),opts={headers:{cookie:a.cookie}};
 for(const bad of [{send_time:'08:03'},{send_time:'24:00'},{send_time:805},{frequency:'custom',weekdays:[]},{frequency:'custom',weekdays:[7]},{difficulty:'expert'},{length:'unlimited'}]){
  assert.equal((await f.call('/api/preferences',{topics:['path tracking'],...bad},opts)).status,400);
 }
 assert.equal(f.DB.db.prepare('SELECT preferences_version FROM members WHERE id=?').get(a.user.id).preferences_version,1);
});
test('saving unchanged preferences keeps effective time; resume starts a new schedule version',async()=>{
 const f=fixture(),a=await active(f),opts={headers:{cookie:a.cookie}};
 const effective=f.DB.db.prepare('SELECT schedule_effective_at FROM members WHERE id=?').get(a.user.id).schedule_effective_at;
 const r=await f.call('/api/preferences',{name:'Changed',topics:['path tracking']},opts);
 assert.equal(r.data.user.preferences_version,1);assert.equal(r.data.user.schedule_effective_at,effective);
 await f.call('/api/status',{action:'pause'},opts);const resumed=await f.call('/api/status',{action:'resume'},opts);
 assert.equal(resumed.data.user.preferences_version,3);assert.ok(resumed.data.user.schedule_effective_at>0);
});
test('reordering keywords does not postpone delivery or change content version',async()=>{
 const f=fixture(),a=await active(f),opts={headers:{cookie:a.cookie}};
 const first=await f.call('/api/preferences',{topics:['vehicle control','path tracking']},opts);
 const second=await f.call('/api/preferences',{topics:['path tracking','vehicle control']},opts);
 assert.equal(second.data.user.preferences_version,first.data.user.preferences_version);
 assert.equal(second.data.user.schedule_effective_at,first.data.user.schedule_effective_at);
});
