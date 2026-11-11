'use client';
import {useState,useEffect} from 'react';
const themes=[['vehicle dynamics','车辆动力学'],['lateral control','车辆横向控制'],['path tracking','路径跟踪'],['model predictive control','模型预测控制'],['active suspension','主动悬架'],['thermal management','热管理']];
type User={id:string,email:string,name:string,topics:string[],status:string,admin_paused:boolean,send_time:string,frequency:string,weekdays:number[],difficulty:string,length:string,preferences_version:number};
type ApiResults={
 me:{user:User};exchange:{user:User};preferences:{user:User};status:{user:User};
 login:{message:string};unsubscribe:{status:string};logout:{ok:boolean};
};
const allDays=[0,1,2,3,4,5,6];
function preferenceKey(preferences:Pick<User,'name'|'topics'|'send_time'|'frequency'|'weekdays'|'difficulty'|'length'>){
 const frequency=preferences.frequency||'daily';
 return JSON.stringify([
  preferences.name.trim(),[...preferences.topics].sort(),preferences.send_time||'08:00',
  frequency,frequency==='custom'?[...(preferences.weekdays||allDays)].sort():[],
  preferences.difficulty||'beginner',preferences.length||'standard'
 ]);
}
class ApiError extends Error {
 constructor(message:string,readonly status:number){super(message);}
}
export default function Page(){
 const [user,setUser]=useState<User|null>(null),[email,setEmail]=useState(''),[name,setName]=useState(''),[selected,setSelected]=useState<string[]>([]),[extra,setExtra]=useState(''),[pending,setPending]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(false),[link,setLink]=useState<{purpose:string,token:string}|null>(null),[consent,setConsent]=useState(false),[confirmStop,setConfirmStop]=useState(false),[loading,setLoading]=useState(true);
 const [sendTime,setSendTime]=useState('08:00'),[frequency,setFrequency]=useState('daily'),[weekdays,setWeekdays]=useState<number[]>(allDays),[difficulty,setDifficulty]=useState('beginner'),[length,setLength]=useState('standard');
 const [loadFailed,setLoadFailed]=useState(false),[loadAttempt,setLoadAttempt]=useState(0);
 const adopt=(u:User)=>{setUser(u);setName(u.name);setSelected(u.topics.filter(t=>themes.some(v=>v[0]===t)));setExtra(u.topics.filter(t=>!themes.some(v=>v[0]===t)).join(', '));setSendTime(u.send_time||'08:00');setFrequency(u.frequency||'daily');setWeekdays(u.weekdays||allDays);setDifficulty(u.difficulty||'beginner');setLength(u.length||'standard');};
 const topics=[...selected,...extra.split(',').map(value=>value.trim()).filter(Boolean)];
 const draft={name,topics,send_time:sendTime,frequency,weekdays,difficulty,length};
 const dirty=!!user&&preferenceKey(draft)!==preferenceKey(user);
 async function api<Path extends keyof ApiResults>(path:Path,body?:unknown,signal?:AbortSignal):Promise<ApiResults[Path]>{
  const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal});
  if(!response.ok){
   const data=await response.json().catch(()=>null) as {error?:string}|null;
   throw new ApiError(data?.error||'暂时无法处理',response.status);
  }
  return response.json() as Promise<ApiResults[Path]>;
 }
 async function action(task:()=>Promise<void>){if(pending)return;setPending(true);setMessage('');setError(false);try{await task();}catch(e){setError(true);setMessage(e instanceof Error?e.message:'暂时无法处理');}finally{setPending(false);}}
 useEffect(()=>{
  const request=new AbortController();
  const consume=()=>{
   const params=new URLSearchParams(location.hash.slice(1));
   for(const purpose of ['invite','login','unsubscribe']){
    const token=params.get(purpose);
    if(!token)continue;
    request.abort();
    setLink({purpose,token});setConsent(false);setMessage('');setLoadFailed(false);
    history.replaceState(null,'',location.pathname);
    setLoading(false);
    return true;
   }
   return false;
  };
  if(!consume()){
   api('me',undefined,request.signal).then(result=>{
    if(!request.signal.aborted)adopt(result.user);
   }).catch(cause=>{
    if(request.signal.aborted)return;
    if(cause instanceof ApiError&&cause.status===401)setUser(null);
    else setLoadFailed(true);
   }).finally(()=>{if(!request.signal.aborted)setLoading(false);});
  }
  addEventListener('hashchange',consume);
  return()=>{request.abort();removeEventListener('hashchange',consume);};
 },[loadAttempt]);
 const toggle=(term:string)=>{if(selected.includes(term))setSelected(selected.filter(x=>x!==term));else if(selected.length+extra.split(',').filter(x=>x.trim()).length<3)setSelected([...selected,term]);else{setError(true);setMessage('最多配置3个关键词。');}};
 return <main><header><a href="/" className="brand">研读<span>晨读</span></a><span className="edition">车辆工程 · 邀请试用</span></header><section className="card">
 {loading?<p role="status">正在读取订阅…</p>:loadFailed?<>
  <h1>暂时无法读取晨读订阅</h1>
  <button className="primary" onClick={()=>{setLoadFailed(false);setLoading(true);setLoadAttempt(attempt=>attempt+1);}}>重新加载</button>
 </>:link?<>
  <p className="eyebrow">邮箱确认</p><h1>{link.purpose==='invite'?'开启你的论文晨读':link.purpose==='unsubscribe'?'退订晨读':'登录晨读管理'}</h1>
  {link.purpose==='invite'?<><p className="intro">论文节选、中文译文和学习问题。默认每天08:00，可自行调整。</p><label className="check"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>我愿意接收晨读邮件，随时可以暂停或退订。</label></>:null}
  {link.purpose==='unsubscribe'?<p className="intro">只停止你的订阅。</p>:null}
  <button className="primary" disabled={pending||link.purpose==='invite'&&!consent} onClick={()=>action(async()=>{if(link.purpose==='unsubscribe'){await api('unsubscribe',{token:link.token});setUser(null);setMessage('已退订晨读。');setLink(null);}else{const r=await api('exchange',{token:link.token,consent});adopt(r.user);setLink(null);setMessage('邮箱已验证。');}})}>{pending?'处理中…':link.purpose==='invite'?'确认订阅':link.purpose==='unsubscribe'?'确认退订':'登录'}</button>
 </>:user?<>
  <div className="heading"><div><p className="eyebrow">我的订阅</p><h1>晨读偏好</h1></div><span className={'status '+(user.status==='active'&&!user.admin_paused?'active':'')}>{user.admin_paused?'管理员已暂停':user.status==='active'?'已订阅':'已暂停'}</span></div>
  <p className="email">{user.email}</p>
  <fieldset className="preference-fields" aria-label="编辑晨读偏好" disabled={pending}>
  <label htmlFor="name">称呼</label><input id="name" value={name} maxLength={30} onChange={e=>setName(e.target.value)}/>
  <label>研究方向</label><div className="themes">{themes.map(([term,label])=><button key={term} className={selected.includes(term)?'chosen':''} aria-pressed={selected.includes(term)} onClick={()=>toggle(term)}>{label}</button>)}</div>
  <label htmlFor="extra">其他英文关键词</label><input id="extra" value={extra} placeholder="例如：friction estimation" maxLength={250} onChange={e=>setExtra(e.target.value)}/><small>合计最多3个关键词。</small>
  <div className="preferences-grid">
   <div><label htmlFor="send-time">发送时间 · 北京时间</label><select id="send-time" value={sendTime} onChange={e=>setSendTime(e.target.value)}>{Array.from({length:288},(_,i)=>{const v=String(Math.floor(i/12)).padStart(2,'0')+':'+String(i%12*5).padStart(2,'0');return <option key={v} value={v}>{v}</option>;})}</select></div>
   <div><label htmlFor="frequency">发送日期</label><select id="frequency" value={frequency} onChange={e=>setFrequency(e.target.value)}><option value="daily">每天</option><option value="weekdays">周一至周五</option><option value="custom">自选星期</option></select></div>
  </div>
  {frequency==='custom'?<div className="themes weekdays" aria-label="发送星期">{['一','二','三','四','五','六','日'].map((label,i)=><button key={i} aria-label={'周'+label} aria-pressed={weekdays.includes(i)} className={weekdays.includes(i)?'chosen':''} onClick={()=>setWeekdays(weekdays.includes(i)?weekdays.filter(d=>d!==i):[...weekdays,i].sort())}>{label}</button>)}</div>:null}
  <div className="preferences-grid">
   <div><label htmlFor="difficulty">讲解难度</label><select id="difficulty" value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="beginner">入门</option><option value="advanced">进阶</option></select></div>
   <div><label htmlFor="length">内容篇幅</label><select id="length" value={length} onChange={e=>setLength(e.target.value)}><option value="concise">精简 · 100—110词</option><option value="standard">标准 · 130—150词＋导引</option></select></div>
  </div>
  <button className="primary" disabled={!dirty} onClick={()=>action(async()=>{
   const result=await api('preferences',{...draft,preferences_version:user.preferences_version});
   adopt(result.user);
  })}>保存偏好</button>
  <p className={'preference-save-state'+(dirty?' dirty':'')} role="status">{dirty?'偏好有未保存的更改':'偏好已保存'}</p>
  </fieldset>
  <div className="controls"><button disabled={pending||user.admin_paused} onClick={()=>action(async()=>{
   const {user:updated}=await api('status',{action:user.status==='active'?'pause':'resume'});
   if(!dirty)adopt(updated);
   else if(preferenceKey(user)===preferenceKey(updated))setUser(updated);
   else{
    setUser({...user,status:updated.status,admin_paused:updated.admin_paused});
    setError(true);
    setMessage('订阅状态已更新。另一处已修改偏好，当前草稿仍保留。');
    return;
   }
   setMessage(updated.status==='active'?'已恢复订阅。':'已暂停订阅。');
  })}>{user.status==='active'?'暂停晨读':'恢复晨读'}</button><button disabled={pending} onClick={()=>setConfirmStop(!confirmStop)}>退订</button><button disabled={pending} onClick={()=>action(async()=>{await api('logout',{});setUser(null);setEmail('');setMessage('已退出。');})}>退出登录</button></div>
  {confirmStop?<div className="stop"><p>退订后需重新接受邀请才能开通。</p><button disabled={pending} onClick={()=>action(async()=>{await api('status',{action:'unsubscribe'});setUser(null);setConfirmStop(false);setMessage('已退订晨读。');})}>确认退订</button><button onClick={()=>setConfirmStop(false)}>取消</button></div>:null}
 </>:<>
  <p className="eyebrow">论文晨读</p><h1>让阅读成为每天的习惯</h1><p className="intro">受邀后，用邮箱管理你的研究兴趣与晨读订阅。</p>
  <form onSubmit={e=>{e.preventDefault();action(async()=>{const r=await api('login',{email});setMessage(r.message);});}}><label htmlFor="email">受邀邮箱</label><input id="email" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required placeholder="你的邮箱地址"/><button className="primary" disabled={pending}>{pending?'处理中…':'发送登录链接'}</button></form>
 </>}
 {message?<p className={error?'message error':'message'} role={error?'alert':'status'}>{message}</p>:null}
 </section><footer>仅保存订阅邮箱、兴趣和发送所需记录。论文与笔记仍留在你的本机。</footer></main>;
}
