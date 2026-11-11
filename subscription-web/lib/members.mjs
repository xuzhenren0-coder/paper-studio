/* Invite-only control plane. SMTP and model keys remain in Alibaba Cloud. */
export const LIMIT=2;
export const THEMES=[['vehicle dynamics','车辆动力学'],['lateral control','车辆横向控制'],['path tracking','路径跟踪'],['model predictive control','模型预测控制'],['active suspension','主动悬架'],['thermal management','热管理']];
const enc=new TextEncoder(),hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
const random=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
export const hash=async s=>hex(await crypto.subtle.digest('SHA-256',enc.encode(s)));
const b64=b=>btoa(String.fromCharCode(...new Uint8Array(b))).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
const unb64=s=>Uint8Array.from(atob(s.replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));
class UserError extends Error {constructor(message,status=400){super(message);this.status=status;}}
const fail=(message,status=400)=>{throw new UserError(message,status);};
const email=s=>{s=String(s||'').trim().toLowerCase();if(s.length>254||! /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$/.test(s))fail('请输入有效邮箱。');return s;};
const topics=items=>{if(!Array.isArray(items)||!items.length||items.length>3)fail('请配置1—3个研究关键词。');const out=[...new Set(items.map(v=>String(v).trim().toLowerCase()))];if(out.some(v=>v.length<2||v.length>100||! /^[a-z][a-z0-9 ()/.,-]*$/.test(v)))fail('关键词请使用简短英文。');return out;};
const one=(db,sql,...args)=>db.prepare(sql).bind(...args).first();
const all=async(db,sql,...args)=>(await db.prepare(sql).bind(...args).all()).results;
const run=(db,sql,...args)=>db.prepare(sql).bind(...args).run();
const changes=r=>r.meta?.changes??r.changes??0;
const json=(value,status=200,headers={})=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',...headers}});
const clean=u=>({id:u.id,email:u.email,name:u.name,topics:JSON.parse(u.topics),status:u.status,admin_paused:!!u.admin_paused,verified:!!u.verified_at,created:u.created_at,updated:u.updated_at,send_time:u.send_time||'08:00',frequency:u.frequency||'daily',weekdays:JSON.parse(u.weekdays||'[0,1,2,3,4,5,6]'),difficulty:u.difficulty||'beginner',length:u.length||'standard',preferences_version:u.preferences_version||1,schedule_effective_at:u.schedule_effective_at||0});
function preferences(body,u){
 const previous=clean(u),out={};
 out.send_time=body.send_time??previous.send_time;
 if(typeof out.send_time!=='string'||! /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(out.send_time)||Number(out.send_time.slice(-2))%5)fail('发送时间请选择5分钟刻度。');
 out.frequency=body.frequency??previous.frequency;
 if(!['daily','weekdays','custom'].includes(out.frequency))fail('发送频率无效。');
 let days=body.weekdays??previous.weekdays;
 if(!Array.isArray(days)||!days.length||days.some(x=>!Number.isInteger(x)||x<0||x>6))fail('请至少选择一个有效星期。');
 out.weekdays=out.frequency==='daily'?[0,1,2,3,4,5,6]:out.frequency==='weekdays'?[0,1,2,3,4]:[...new Set(days)].sort();
 out.difficulty=body.difficulty??previous.difficulty;out.length=body.length??previous.length;
 if(!['beginner','advanced'].includes(out.difficulty)||!['concise','standard'].includes(out.length))fail('学习偏好无效。');
 return out;
}
async function aes(secret){return crypto.subtle.importKey('raw',await crypto.subtle.digest('SHA-256',enc.encode('outbox:'+secret)),{name:'AES-GCM'},false,['encrypt','decrypt']);}
async function seal(secret,obj){const iv=crypto.getRandomValues(new Uint8Array(12));return b64(iv)+'.'+b64(await crypto.subtle.encrypt({name:'AES-GCM',iv},await aes(secret),enc.encode(JSON.stringify(obj))));}
async function open(secret,text){const [iv,body]=text.split('.');return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(iv)},await aes(secret),unb64(body))));}
export async function signing(secret,stamp,nonce,method,path,raw){const key=await crypto.subtle.importKey('raw',enc.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);return hex(await crypto.subtle.sign('HMAC',key,enc.encode([stamp,nonce,method,path,await hash(raw)].join('\n'))));}
async function bridgeAuth(req,env,raw,now){
 const stamp=req.headers.get('x-morning-time')||'',nonce=req.headers.get('x-morning-nonce')||'',signature=req.headers.get('x-morning-signature')||'';
 if(!/^\d{10}$/.test(stamp)||Math.abs(now-Number(stamp))>120||! /^[a-f0-9]{32,64}$/.test(nonce)||! /^[a-f0-9]{64}$/.test(signature))fail('服务身份验证失败。',403);
 const key=await crypto.subtle.importKey('raw',enc.encode(env.MEMBER_BRIDGE_SECRET),{name:'HMAC',hash:'SHA-256'},false,['verify']);
 if(!await crypto.subtle.verify('HMAC',key,Uint8Array.from(signature.match(/../g),h=>parseInt(h,16)),enc.encode([stamp,nonce,req.method,new URL(req.url).pathname,await hash(raw)].join('\n'))))fail('服务身份验证失败。',403);
 await run(env.DB,'DELETE FROM bridge_nonces WHERE expires_at < ?',now);
 if(changes(await run(env.DB,'INSERT OR IGNORE INTO bridge_nonces(nonce,expires_at) VALUES(?,?)',nonce,now+300))!==1)fail('服务请求已处理。',409);
}
async function session(req,env,now){const value=(req.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('morning_session='))?.slice(16);if(!value||! /^[a-f0-9]{64}$/.test(value))fail('请通过邮箱登录。',401);const u=await one(env.DB,'SELECT u.*,s.token_hash AS session_hash FROM member_sessions s JOIN members u ON u.id=s.member_id WHERE s.token_hash=? AND s.expires_at>?',await hash(value),now);if(!u||!u.verified_at||['unsubscribed','invited'].includes(u.status))fail('请重新通过邮箱登录。',401);return u;}
const cookie=(value,req,age=86400)=>`morning_session=${value}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${age}${new URL(req.url).protocol==='https:'?'; Secure':''}`;
const originFor=(env,req)=>{const u=new URL(env.MEMBER_PUBLIC_ORIGIN||new URL(req.url).origin);if(u.protocol!=='https:'&&!['127.0.0.1','localhost'].includes(u.hostname))fail('站点地址尚未配置。',503);return u.origin;};
async function identity(env){const token=random();return {generation:random().slice(0,32),unsubscribe_hash:await hash(token),unsubscribe_cipher:await seal(env.MEMBER_BRIDGE_SECRET,{token})};}
async function queue(env,u,purpose,now,req){
 const recent=await one(env.DB,'SELECT count(*) AS n,max(created_at) AS latest FROM member_outbox WHERE member_id=? AND created_at>?',u.id,now-3600);
 if(recent.n>=3||(recent.latest&&now-recent.latest<60))return false;
 const token=random(),job=crypto.randomUUID(),expiry=now+(purpose==='invite'?172800:900),payload=await seal(env.MEMBER_BRIDGE_SECRET,{purpose,url:originFor(env,req)+'/#'+purpose+'='+token});
 await env.DB.batch([
  env.DB.prepare("INSERT INTO member_outbox(id,member_id,payload,status,created_at,expires_at) SELECT ?,?,?,'pending',?,? WHERE (SELECT count(*) FROM member_outbox WHERE member_id=? AND created_at>?)<3 AND NOT EXISTS(SELECT 1 FROM member_outbox WHERE member_id=? AND created_at>?) AND EXISTS(SELECT 1 FROM members WHERE id=? AND generation=? AND status!='unsubscribed')").bind(job,u.id,payload,now,expiry,u.id,now-3600,u.id,now-60,u.id,u.generation),
  env.DB.prepare("UPDATE member_outbox SET status='cancelled' WHERE member_id=? AND status='pending' AND id!=? AND EXISTS(SELECT 1 FROM member_outbox WHERE id=?)").bind(u.id,job,job),
  env.DB.prepare('UPDATE member_tokens SET used_at=? WHERE member_id=? AND purpose=? AND used_at IS NULL AND EXISTS(SELECT 1 FROM member_outbox WHERE id=?)').bind(now,u.id,purpose,job),
  env.DB.prepare('INSERT INTO member_tokens(token_hash,member_id,generation,purpose,expires_at,used_at) SELECT ?,?,?,?, ?,NULL WHERE EXISTS(SELECT 1 FROM member_outbox WHERE id=?)').bind(await hash(token),u.id,u.generation,purpose,expiry,job)
 ]);return true;
}
async function exchange(env,u,token,now,req,consent){
 const digest=await hash(token),t=await one(env.DB,'SELECT * FROM member_tokens WHERE token_hash=?',digest);
 if(!t||t.used_at||t.expires_at<=now||t.generation!==u.generation)fail('链接已失效，请重新获取。');
 if(t.purpose==='invite'&&consent!==true)fail('请确认订阅后继续。');
 if(!['invite','login'].includes(t.purpose)||t.purpose==='login'&&(!u.verified_at||['unsubscribed','invited'].includes(u.status)))fail('链接已失效。');
 const secret=random(),hashed=await hash(secret);
 const result=await env.DB.batch([
  env.DB.prepare("INSERT INTO member_sessions(token_hash,member_id,expires_at) SELECT ?,t.member_id,? FROM member_tokens t JOIN members m ON m.id=t.member_id AND m.generation=t.generation WHERE t.token_hash=? AND t.used_at IS NULL AND t.expires_at>? AND t.generation=? AND m.status!='unsubscribed'").bind(hashed,now+86400,digest,now,u.generation),
  env.DB.prepare('UPDATE member_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL').bind(now,digest),
  env.DB.prepare("UPDATE members SET schedule_effective_at=CASE WHEN status='invited' THEN ? ELSE schedule_effective_at END,status=CASE WHEN status='invited' THEN 'active' ELSE status END,verified_at=coalesce(verified_at,?),updated_at=? WHERE id=? AND EXISTS(SELECT 1 FROM member_sessions WHERE token_hash=?)").bind(now,now,now,u.id,hashed)
 ]);
 if(changes(result[0])!==1)fail('链接已使用，请重新获取。');
 return json({user:clean(await one(env.DB,'SELECT * FROM members WHERE id=?',u.id))},200,{'Set-Cookie':cookie(secret,req)});
}
async function admin(path,body,req,env,now){
 if(path==='/api/admin/state')return json({limit:LIMIT,users:(await all(env.DB,'SELECT * FROM members ORDER BY created_at')).map(clean),outbox:await all(env.DB,'SELECT id,member_id,status,created_at,finished_at FROM member_outbox ORDER BY created_at DESC LIMIT 20')});
 if(['/api/admin/invite','/api/admin/bootstrap'].includes(path)){
  const address=email(body.email),list=topics(body.topics||['vehicle dynamics']);let u=await one(env.DB,'SELECT * FROM members WHERE email=?',address);
  if(u&&u.status!=='unsubscribed'){if(path.endsWith('invite')&&u.status==='invited')await queue(env,u,'invite',now,req);return json({user:clean(u),existing:true});}
  const data=await identity(env),name=String(body.name||'同学').trim().slice(0,30),id=u?.id||crypto.randomUUID();
  if(!u){if(changes(await run(env.DB,"INSERT INTO members(id,email,name,topics,status,generation,unsubscribe_hash,unsubscribe_cipher,created_at,updated_at) SELECT ?,?,?,?,'invited',?,?,?,?,? WHERE (SELECT count(*) FROM members) < ?",id,address,name,JSON.stringify(list),data.generation,data.unsubscribe_hash,data.unsubscribe_cipher,now,now,LIMIT))!==1)fail('最多可配置2个订阅邮箱。',409);}
  else await env.DB.batch([env.DB.prepare("UPDATE members SET name=?,topics=?,status='invited',generation=?,unsubscribe_hash=?,unsubscribe_cipher=?,verified_at=NULL,admin_paused=0,updated_at=? WHERE id=?").bind(name,JSON.stringify(list),data.generation,data.unsubscribe_hash,data.unsubscribe_cipher,now,id),env.DB.prepare('DELETE FROM member_sessions WHERE member_id=?').bind(id),env.DB.prepare('UPDATE member_tokens SET used_at=? WHERE member_id=? AND used_at IS NULL').bind(now,id)]);
  if(path.endsWith('bootstrap'))await run(env.DB,"UPDATE members SET status='active',verified_at=?,updated_at=? WHERE id=?",now,now,id);
  u=await one(env.DB,'SELECT * FROM members WHERE id=?',id);if(path.endsWith('invite'))await queue(env,u,'invite',now,req);return json({user:clean(u),queued:path.endsWith('invite')},201);
 }
 if(path==='/api/admin/pause'){const u=await one(env.DB,'SELECT * FROM members WHERE id=?',String(body.id||''));if(!u)fail('用户不存在。',404);if(typeof body.paused!=='boolean')fail('暂停设置无效。');if(Number(body.paused)!==u.admin_paused)await run(env.DB,'UPDATE members SET admin_paused=?,updated_at=?,schedule_effective_at=?,preferences_version=preferences_version+1 WHERE id=?',body.paused?1:0,now,now,u.id);return json({ok:true});}
 fail('接口不存在。',404);
}
async function bridge(path,body,req,env,now){
 if(path==='/api/bridge/subscribers'){const users=[];for(const u of await all(env.DB,"SELECT * FROM members WHERE status='active' AND verified_at IS NOT NULL AND admin_paused=0 ORDER BY created_at")){const token=await open(env.MEMBER_BRIDGE_SECRET,u.unsubscribe_cipher);users.push({...clean(u),generation:u.generation,unsubscribe_url:originFor(env,req)+'/#unsubscribe='+token.token});}return json({users});}
 if(path==='/api/bridge/active'){const u=await one(env.DB,'SELECT * FROM members WHERE id=?',String(body.id||''));return json({active:!!u&&u.status==='active'&&!!u.verified_at&&!u.admin_paused&&u.generation===body.generation&&(body.preferences_version===undefined||body.preferences_version===u.preferences_version)});}
 if(path==='/api/bridge/mail-active'){const job=await one(env.DB,"SELECT o.*,u.generation,u.status AS member_status FROM member_outbox o JOIN members u ON u.id=o.member_id WHERE o.id=? AND o.status='claimed' AND o.expires_at>?",String(body.id||''),now);if(!job||job.member_status==='unsubscribed')return json({active:false});const payload=await open(env.MEMBER_BRIDGE_SECRET,job.payload),token=new URLSearchParams(new URL(payload.url).hash.slice(1)).get(payload.purpose),t=await one(env.DB,'SELECT * FROM member_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>? AND generation=?',await hash(token),now,job.generation);return json({active:!!t});}
 if(path==='/api/bridge/claim'){const job=await one(env.DB,"SELECT o.*,u.email,u.name FROM member_outbox o JOIN members u ON o.member_id=u.id WHERE o.status='pending' AND o.expires_at>? AND u.status!='unsubscribed' ORDER BY o.created_at LIMIT 1",now);if(!job||changes(await run(env.DB,"UPDATE member_outbox SET status='claimed' WHERE id=? AND status='pending'",job.id))!==1)return json({job:null});return json({job:{id:job.id,email:job.email,name:job.name,...await open(env.MEMBER_BRIDGE_SECRET,job.payload)}});}
 if(path==='/api/bridge/finish'){if(!['accepted','unknown','rejected'].includes(body.status))fail('无效结果。');await run(env.DB,"UPDATE member_outbox SET status=?,finished_at=? WHERE id=? AND status='claimed'",body.status,now,String(body.id||''));return json({ok:true});}
 fail('接口不存在。',404);
}
async function unsubscribe(env,u,now){await env.DB.batch([env.DB.prepare("UPDATE members SET status='unsubscribed',updated_at=? WHERE id=?").bind(now,u.id),env.DB.prepare('DELETE FROM member_sessions WHERE member_id=?').bind(u.id),env.DB.prepare('UPDATE member_tokens SET used_at=? WHERE member_id=? AND used_at IS NULL').bind(now,u.id),env.DB.prepare("UPDATE member_outbox SET status='cancelled' WHERE member_id=? AND status='pending'").bind(u.id)]);}
export async function handleMembers(req,env){
 try{
  const path=new URL(req.url).pathname,now=Math.floor(Date.now()/1000);
  if(path==='/api/health')return json({ok:true,feature:'members-v1',limit:LIMIT});
  if(!env.DB||!env.MEMBER_BRIDGE_SECRET||env.MEMBER_BRIDGE_SECRET.length<32)return json({error:'订阅服务尚未完成配置。'},503);
  const raw=req.method==='GET'?'':await req.text();if(enc.encode(raw).length>8192)fail('请求过长。',413);
  if(path.startsWith('/api/admin/')||path.startsWith('/api/bridge/')){if(req.method!=='POST')fail('请求方式无效。',405);await bridgeAuth(req,env,raw,now);const body=JSON.parse(raw||'{}');return path.startsWith('/api/admin/')?await admin(path,body,req,env,now):await bridge(path,body,req,env,now);}
  if(req.method==='GET'&&path==='/api/me')return json({user:clean(await session(req,env,now))});
  if(req.method!=='POST')fail('接口不存在。',404);
  if(req.headers.get('origin')!==new URL(req.url).origin)fail('请求来源无效。',403);
  const body=JSON.parse(raw||'{}');
  if(path==='/api/login'){let address='';try{address=email(body.email);}catch{}const u=address?await one(env.DB,'SELECT * FROM members WHERE email=?',address):null;if(u&&u.status!=='unsubscribed')await queue(env,u,u.status==='invited'?'invite':'login',now,req);return json({message:'如该邮箱已受邀，登录或确认邮件将在稍后送达。'});}
  if(path==='/api/exchange'){const token=String(body.token||'');if(!/^[a-f0-9]{64}$/.test(token))fail('链接无效。');const t=await one(env.DB,'SELECT * FROM member_tokens WHERE token_hash=?',await hash(token));const u=t?await one(env.DB,'SELECT * FROM members WHERE id=?',t.member_id):null;if(!u)fail('链接已失效。');return await exchange(env,u,token,now,req,body.consent);}
  if(path==='/api/unsubscribe'&&body.token){const token=String(body.token);if(!/^[a-f0-9]{64}$/.test(token))fail('链接无效。');const u=await one(env.DB,'SELECT * FROM members WHERE unsubscribe_hash=?',await hash(token));if(!u)fail('链接已失效。');await unsubscribe(env,u,now);return json({status:'unsubscribed',message:'已退订晨读。'},200,{'Set-Cookie':cookie('',req,0)});}
  const u=await session(req,env,now);
  if(path==='/api/logout'){await run(env.DB,'DELETE FROM member_sessions WHERE token_hash=?',u.session_hash);return json({ok:true},200,{'Set-Cookie':cookie('',req,0)});}
  if(path==='/api/preferences'){
   const list=topics(body.topics),name=String(body.name||'同学').trim().slice(0,30),p=preferences(body,u),previous=clean(u);
   const changed=JSON.stringify([...list].sort())!==JSON.stringify([...previous.topics].sort())||Object.keys(p).some(k=>JSON.stringify(p[k])!==JSON.stringify(previous[k]));
   const version=u.preferences_version+(changed?1:0),effective=changed?now:u.schedule_effective_at;
   if(body.preferences_version!==undefined&&body.preferences_version!==u.preferences_version)fail('设置已更新，请刷新后重试。',409);
   if(changes(await run(env.DB,'UPDATE members SET name=?,topics=?,send_time=?,frequency=?,weekdays=?,difficulty=?,length=?,preferences_version=?,schedule_effective_at=?,updated_at=? WHERE id=? AND preferences_version=?',name,JSON.stringify(list),p.send_time,p.frequency,JSON.stringify(p.weekdays),p.difficulty,p.length,version,effective,now,u.id,u.preferences_version))!==1)fail('设置已更新，请刷新后重试。',409);
   return json({user:clean(await one(env.DB,'SELECT * FROM members WHERE id=?',u.id))});
  }
  if(path==='/api/status'){if(!['pause','resume','unsubscribe'].includes(body.action))fail('设置无效。');if(body.action==='unsubscribe'){await unsubscribe(env,u,now);return json({status:'unsubscribed'},200,{'Set-Cookie':cookie('',req,0)});}if(body.action==='resume'&&u.admin_paused)fail('管理员已暂停该订阅，请联系邀请人。',409);await run(env.DB,'UPDATE members SET status=?,updated_at=?,schedule_effective_at=?,preferences_version=preferences_version+1 WHERE id=?',body.action==='pause'?'paused':'active',now,now,u.id);return json({user:clean(await one(env.DB,'SELECT * FROM members WHERE id=?',u.id))});}
  fail('接口不存在。',404);
 }catch(e){return json({error:e instanceof UserError?e.message:e instanceof SyntaxError?'请求格式无效。':'暂时无法处理，请稍后再试。'},e instanceof UserError?e.status:e instanceof SyntaxError?400:503);}
}
