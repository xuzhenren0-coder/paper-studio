import {PaperReader} from '/reader.js';
import {initDiscovery} from '/discovery-ui.js';
import {initLearningFlow} from '/learning-flow.js';
import {feedbackIsStale,feedbackLabels,feedbackStatuses,renderFeedback,studySnapshot} from '/feedback-view.js';
const $=id=>document.getElementById(id);
const state={view:'home',paper:null,papers:[],notes:{},runs:[],workspace:'assistant',practice:'translation',panelOpen:true,context:null,selection:null,configured:false,busy:false,restoring:false};
const fields=['question','translationSource','translationAttempt','translationRevision','translationReflection','studyGoal','studyQuestion','answerProblem','answerMethod','answerEvidence','answerLimit','personalNotes'];
const taskNames={preview:'论文导读',ask:'追问',explain:'选段解释',translate:'选段翻译',translation:'翻译练习反馈',feedback:'自主解释反馈',critique:'辅助批判',summary:'结构化草稿'};
const mobile=()=>matchMedia('(max-width:840px)').matches;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let panelMotionId = 0;
let panelReadPosition = null;
let saveTimer,saveQueue=Promise.resolve(),saving=false,dirty=false,openSerial=0,toastTimer;
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5000);}
function localRead(key){try{return localStorage.getItem(key)}catch{return null}}
function localWrite(key,value){try{localStorage.setItem(key,value)}catch{}}
async function api(path,body,headers={}){const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Request':'1',...headers},body:body instanceof ArrayBuffer?body:JSON.stringify(body)};const r=await fetch(path,options);const data=await r.json();if(!r.ok)throw Error(data.error||'操作失败');return data;}
const reader=new PaperReader($('readerScroll'),$('pdfPages'),{
 onPosition:position=>{if(!state.paper||state.view!=='reader')return;$('pageInput').value=position.page;$('zoomLabel').textContent=Math.round(position.scale*100)+'%';$('columnMode').value=position.column||'';if(!state.restoring){state.notes.readerPosition=position;queueSave();}},
 onSelection:selection=>showSelection(selection),
 onStatus:message=>{$('readerStatus').textContent=message;$('readerStatus').classList.toggle('ready',message==='可直接选择原文文字');},
 onOutline:items=>renderOutline(items),
 onNavigation:available=>{$('sourceBack').hidden=!available;}
});
async function locateEvidence(item){finishPanelMotion();state.returnPanel=state.panelOpen;if(mobile())setPanel(false);try{const found=await reader.locate(typeof item==='number'?{page:item}:item);if(found===false)toast('未定位到原句，已跳到对应页。');}catch{toast('未定位到原句，请核对对应页。');}}
$('sourceBack').onclick = async () => {
 try {
  finishPanelMotion();
  await reader.returnToReading();
  if (!reader.navigation.length && state.returnPanel) {
   setPanel(true, {save:false});
   state.returnPanel = false;
  }
 } catch (error) { toast(error.message); }
};
function capture(){const n={...state.notes};for(const f of fields)n[f]=$(f).value;n.activeWorkspace=state.workspace;n.practice=state.practice;n.context=state.context;n.readerPosition=state.view==='reader'?(panelReadPosition||reader.position()):(state.parkedPosition||n.readerPosition||{page:1});n.currentPage=n.readerPosition.page;
 if(mobile())n.mobilePanelOpen=state.panelOpen;else n.panelOpen=state.panelOpen;
 state.notes=n;return structuredClone(n);}
function queueSave(){if(!state.paper||state.restoring)return;dirty=true;$('saveStatus').textContent='正在保存…';clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveNow().catch(()=>{}),650);}
function saveNow(){if(!state.paper)return Promise.resolve();clearTimeout(saveTimer);saveTimer=null;const pid=state.paper.id,body=capture();dirty=false;
 saveQueue=saveQueue.catch(()=>{}).then(async()=>{saving=true;try{await api('/api/notes',{paper_id:pid,body});if(state.paper?.id===pid&&!dirty){$('saveStatus').textContent='已保存到本机';studyUI.refresh();}}finally{saving=false;}}).catch(e=>{if(state.paper?.id===pid){dirty=true;$('saveStatus').textContent='保存失败';}toast('保存失败：'+e.message);throw e;});return saveQueue;}
async function flush(){if(dirty||saveTimer)await saveNow();else await saveQueue;}
window.addEventListener('beforeunload',e=>{if(dirty||saving||state.busy){e.preventDefault();e.returnValue='';}});

function finishPanelMotion() {
 ++panelMotionId;
 $('workArea').classList.remove('panel-motion');
 panelReadPosition = null;
 reader.settleResize();
}
function setPanel(open, {save = true, motion = true} = {}) {
 const area = $('workArea');
 const panel = $('toolPanel');
 const changed = state.panelOpen !== open;
 const animate = motion && !reducedMotion.matches && state.view === 'reader' && !state.restoring;
 if (changed && animate && !mobile()) {
  panelReadPosition ??= reader.position();
  reader.pauseResize();
  area.classList.add('panel-motion');
  // Establish the start track sizes before changing the layout state.
  void area.offsetWidth;
 }
 area.classList.toggle('panel-snap', !animate);
 state.panelOpen = open;
 area.classList.toggle('panel-open', open);
 if (!open && panel.contains(document.activeElement)) $('panelToggle').focus({preventScroll:true});
 panel.inert = !open;
 $('panelToggle').classList.toggle('active', open);
 $('panelToggle').setAttribute('aria-expanded', String(open));
 $('focusBtn').textContent = open ? '专注阅读' : '退出专注';
 if (!animate) {
  finishPanelMotion();
  void area.offsetWidth;
  area.classList.remove('panel-snap');
 } else if (changed && !mobile()) {
  const ticket = ++panelMotionId;
  const transitions = area.getAnimations();
  Promise.allSettled(transitions.map(animation => animation.finished)).then(() => {
   if (ticket === panelMotionId) finishPanelMotion();
  });
 }
 if (save) queueSave();
}
function setCompact(compact) {
 const panel = $('toolPanel');
 panel.classList.toggle('compact', compact);
 for (const child of panel.children) {
  if (!child.classList.contains('panel-top')) child.inert = compact;
 }
 $('compactPanel').textContent = compact ? '继续作答' : '收起看原文';
 $('compactPanel').setAttribute('aria-expanded', String(!compact));
}
function setWorkspace(name,{open=true,save=true}={}){setCompact(false);if(!['study','assistant','practice','notes'].includes(name))name='study';state.workspace=name;document.querySelectorAll('[data-workspace]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.workspace===name)));document.querySelectorAll('[data-view]').forEach(v=>v.hidden=v.dataset.view!==name);if(open)setPanel(true,{save:false});$('aiError').hidden=true;if(save)queueSave();}
function setPractice(name,{save=true}={}){state.practice=name==='feedback'?'feedback':'translation';document.querySelectorAll('[data-practice]').forEach(b=>b.classList.toggle('selected',b.dataset.practice===state.practice));document.querySelectorAll('[data-practice-view]').forEach(v=>v.hidden=v.dataset.practiceView!==state.practice);$('practiceResults').hidden=state.practice!=='translation';if(save)queueSave();}
function setContext(context,{save=true}={}){state.context=context;$('contextBlock').hidden=!context;if(context){$('contextLabel').textContent=`PDF 第 ${context.page} 页 · 所选原文`;$('contextText').textContent=context.text;$('contextBlock').open=true;}$('questionScope').textContent=context?'针对选中的原文提问':'结合当前页与相关片段';if(save)queueSave();}
function showSelection(selection){if(state.view!=='reader')selection=null;state.selection=selection;const menu=$('selectionMenu');if(!selection){menu.hidden=true;$('selectionExtras').hidden=true;return;}menu.hidden=false;$('selectionExtras').hidden=true;$('selectionMore').setAttribute('aria-expanded','false');const width=menu.offsetWidth||260;const x=Math.max(8,Math.min(innerWidth-width-8,(selection.rect.left+selection.rect.right-width)/2));const above=selection.rect.top-menu.offsetHeight-9;const y=above>100?above:Math.min(innerHeight-menu.offsetHeight-12,selection.rect.bottom+9);menu.style.left=x+'px';menu.style.top=Math.max(60,y)+'px';}
async function selectionAction(action){const s=state.selection;if(!s)return;if(s.text.length>6000){toast('选区过长，请每次选择不超过 6000 字符的句段。');return;}
 if(s.page!==s.endPage&&action!=='note'){toast('跨页选文可能混入页眉和图注，请在同一页选择句段后操作。');return;}
 const context={text:s.text,page:s.page,locator:s.locator};
 if(action==='practice'){await studyUI.beginTranslation(context);setContext(context);showSelection(null);setPractice('translation');setWorkspace('practice');$('translationAttempt').focus();return;}
 setContext(context);showSelection(null);
 if(action==='evidence'){studyUI.showEvidence();return;}
 if(action==='note'){appendNote(`> ${s.text.replace(/\n/g,'\n> ')}\n\n来源：PDF 第 ${s.page}${s.endPage!==s.page?'—'+s.endPage:''} 页`);setWorkspace('notes');toast('原文摘录已加入笔记。');return;}
 setWorkspace('assistant');
 if(action==='ask'){$('question').focus();return;}
 await runAI(action);
}
$('selectionMenu').addEventListener('pointerdown',e=>e.preventDefault());
for(const b of document.querySelectorAll('[data-selection]'))b.onclick=()=>selectionAction(b.dataset.selection).catch(e=>toast(e.message));
$('selectionMore').onclick=()=>{const extras=$('selectionExtras');extras.hidden=!extras.hidden;$('selectionMore').setAttribute('aria-expanded',String(!extras.hidden));if(!extras.hidden){const r=$('selectionMenu').getBoundingClientRect();extras.style.left=Math.min(innerWidth-160,r.right-145)+'px';extras.style.top=Math.max(60,Math.min(innerHeight-150,r.bottom+5))+'px';}};
document.addEventListener('pointerdown',e=>{if(!$('selectionMenu').contains(e.target)&&!e.target.closest('.textLayer'))showSelection(null);});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){showSelection(null);if(!document.querySelector('dialog[open]')&&mobile())setPanel(false);}});
function appendNote(text){$('personalNotes').value=[$('personalNotes').value.trim(),text].filter(Boolean).join('\n\n---\n\n');queueSave();}
async function refreshLibrary(){state.papers=await api('/api/papers');$('paperCount').textContent=state.papers.length;const list=$('library');list.replaceChildren();if(!state.papers.length)list.append(el('p','empty-library','还没有论文，导入第一篇开始阅读。'));
 for(const p of state.papers){const b=el('button','paper-item'+(p.id===state.paper?.id?' active':''));b.append(el('b','',p.title),el('small','',new Date(p.created*1000).toLocaleDateString('zh-CN')+' · 本地论文'));b.onclick=()=>openPaper(p.id).catch(e=>toast(e.message));list.append(b);}renderHome();}
async function openPaper(id){
 finishPanelMotion();
 const serial=++openSerial;await flush();const [paper,note,runs]=await Promise.all([api('/api/papers/'+id),api('/api/papers/'+id+'/notes'),api('/api/papers/'+id+'/runs')]);if(serial!==openSerial)return;
 await discoveryUI.hide({restore:false});
 if(serial!==openSerial)return;
 state.parkedPosition=null;
 state.restoring=true;state.paper=paper;state.notes=note.body;state.runs=runs;fields.forEach(f=>$(f).value=note.body[f]||'');
 setView('reader');$('paperTitle').textContent=paper.title;$('paperTitle').title=paper.title+' · 点击查看来源';$('pageTotal').textContent='/ '+paper.pages.length;$('pageInput').max=paper.pages.length;
 if($('libraryDialog').open)$('libraryDialog').close();
 const workspace=note.body.activeWorkspace||'study';setWorkspace(workspace,{open:false,save:false});setPractice(note.body.practice||'translation',{save:false});setContext(note.body.context||null,{save:false});
 setPanel(mobile()?!!note.body.mobilePanelOpen:note.body.panelOpen!==false,{save:false,motion:false});$('toolPanel').classList.remove('expanded');$('expandPanel').textContent='展开';
 const width=Math.max(320,Math.min(600,Number(note.body.panelWidth)||400));document.documentElement.style.setProperty('--assistant-width',width+'px');$('panelResizer').setAttribute('aria-valuenow',width);
 renderResults();studyUI.opened();$('saveStatus').textContent=note.updated?'记录已恢复':'本地保存';$('aiError').hidden=true;localWrite('paperStudio.lastPaper',id);await refreshLibrary();
 try{await reader.load('/api/papers/'+id+'/pdf',note.body.readerPosition||{page:note.body.currentPage||1,fraction:0,fit:true},paper.text_version);}
 catch(e){if(serial===openSerial){$('readerStatus').textContent='PDF 打开失败，请重新打开论文或检查文件。';toast('无法打开原文：'+e.message);}}
 finally{if(serial===openSerial)state.restoring=false;}
}
function renderOutline(items){const list=$('outlineList');list.replaceChildren();if(!items.length){list.append(el('p','outline-description','这份 PDF 没有嵌入目录。可使用以下页码跳转。'));items=Array.from({length:state.paper?.pages.length||0},(_,i)=>({title:'PDF 第 '+(i+1)+' 页',page:i+1,depth:0}));}
 for(const item of items){const b=el('button','',item.title);b.style.paddingLeft=12+Math.min(item.depth,4)*12+'px';b.onclick=()=>{jumpPage(item.page);$('outlineDialog').close();};list.append(b);}}
function answerText(){return['研究问题：'+$('answerProblem').value,'方法与假设：'+$('answerMethod').value,'关键证据：'+$('answerEvidence').value,'局限与待解问题：'+$('answerLimit').value].join('\n\n');}
const answerFields=Object.keys(feedbackLabels);
const feedbackRun=()=>state.runs.find(run=>run.task==='feedback');
const runDate=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
function dateLabel(run){return Number.isFinite(run.created)?runDate.format(run.created*1000):'日期未知';}
function currentFeedback(){
 const run=feedbackRun();
 return (run?.feedback||[]).map(row=>({
  ...row,
  stale:feedbackIsStale(run,row.field,$(row.field).value,state.notes.studyEvidence?.[row.field])
 }));
}
function pendingFeedback(rows){
 const fresh=rows.filter(row=>!row.stale);
 const conflicts=fresh.filter(row=>row.status==='contradicted');
 const gaps=fresh.filter(row=>row.status==='insufficient');
 return {conflicts,gaps,next:conflicts[0]||gaps[0]};
}
function currentAnswer(){
 return pendingFeedback(currentFeedback()).next?.field||answerFields.find(field=>!$(field).value.trim())||answerFields[0];
}
function focusAnswer(field){
 setPractice('feedback');setWorkspace('practice');
 $('answer-card-'+field).open=true;
 $(field).focus({preventScroll:true});
 $(field).scrollIntoView({block:'nearest'});
}
const feedbackActions={
 locate:locateEvidence,
 revise:focusAnswer,
 supplement:field=>{focusAnswer(field);toast('请在原文中选择依据，再加入对应项。');}
};
function updateFeedbackState(){
 const rows=currentFeedback();
 for(const field of answerFields){
  const row=rows.find(item=>item.field===field);
  const badge=$('answer-status-'+field);
  badge.textContent=row?.stale?'待重新核对':feedbackStatuses[row?.status]||($(field).value.trim()?'已作答':'');
  badge.dataset.status=row?.stale?'stale':row?.status||'';
  const marker=$('feedback-'+field).querySelector('.feedback-stale');
  if(marker)marker.hidden=!row?.stale;
 }
 const {conflicts,gaps,next}=pendingFeedback(rows);
 const button=$('feedbackPriority');
 button.hidden=!next;
 button.textContent=[conflicts.length&&`${conflicts.length} 项与原文不符`,gaps.length&&`${gaps.length} 项需补证`].filter(Boolean).join(' · ');
 button.onclick=next?()=>next.status==='contradicted'?focusAnswer(next.field):feedbackActions.supplement(next.field):null;
}
function runAttempt(run){
 const attempt=el('details','original-attempt');
 attempt.append(el('summary','','查看当时的作答'),el('p','',run.attempt));
 return attempt;
}
function saveRunButton(run){
 const save=el('button','result-save','保存到我的笔记');
 save.onclick=()=>{
  const citations=(run.citations||[]).map(c=>`- PDF 第 ${c.page} 页：${c.quote}`).join('\n');
  appendNote(`### ${taskNames[run.task]||run.task}（AI 辅助，待核查）\n\n${run.text}\n\n${citations}`);
  toast('AI 内容已明确标识并加入笔记。');
 };
 return save;
}
function renderRun(r){
  const box=el('article','result-card');
  const title=el('div','result-title');
  title.append(el('b','',(taskNames[r.task]||r.task)+' · AI'),el('time','',dateLabel(r)));
  box.append(title);
  if(r.question)box.append(el('div','user-question',r.question));
  if(r.attempt)box.append(runAttempt(r));
  if(r.feedback)renderFeedback(r,box,feedbackActions);else box.append(el('div','ai-text',r.text));const cites=el('div','citation-list');
  for(const c of r.feedback?[]:r.citations||[]){const b=el('button','citation',`PDF 第 ${c.page} 页 · 查看原文 ↗`);b.append(el('em','',c.quote));b.onclick=()=>locateEvidence(c);cites.append(b);}
  box.append(cites,el('p','result-notice',`片段覆盖：PDF 第 ${(r.coverage_pages||[]).join('、')} 页。引用核对仅证明摘录存在，专业反馈尚未经人工验证。`));
  box.append(saveRunButton(r));
  return box;
}
function renderHistory(host,runs,showLatest){
 host.replaceChildren();
 const history=showLatest?runs.slice(1):runs;
 if(showLatest&&runs.length)host.append(renderRun(runs[0]));
 if(!history.length)return;
 const list=el('details','run-history');
 list.append(el('summary','',`历史结果（${history.length}）`));
 for(const run of history){
  const entry=el('details','run-history-entry');
  entry.append(el('summary','',`${taskNames[run.task]||run.task} · ${dateLabel(run)}`));
  entry.addEventListener('toggle',()=>{if(entry.open&&entry.childElementCount===1)entry.append(renderRun(run));});
  list.append(entry);
 }
 host.append(list);
}
function renderResults(){
 const groups={assistant:[],practice:[],notes:[],feedback:[]};
 for(const run of state.runs){
  const group=run.task==='feedback'?'feedback':run.task==='translation'?'practice':run.task==='summary'?'notes':'assistant';
  groups[group].push(run);
 }
 for(const group of ['assistant','practice','notes'])renderHistory($(group+'Results'),groups[group],true);
 const latest=groups.feedback[0];
 const hasRows=!!latest?.feedback?.length;
 for(const field of answerFields){
  const holder=$('feedback-'+field);
  holder.replaceChildren();
  if(!hasRows||!latest.feedback.some(row=>row.field===field))continue;
  const marker=el('p','feedback-stale','修改前的反馈');
  marker.hidden=true;
  holder.append(marker);
  renderFeedback(latest,holder,feedbackActions,field);
 }
 const info=$('feedbackRunInfo');
 info.replaceChildren();
 if(hasRows){
  info.append(el('p','result-notice',`AI 反馈 · ${dateLabel(latest)}。请对照原文核查。`));
  if(latest.attempt)info.append(runAttempt(latest));
  info.append(saveRunButton(latest));
 }
 renderHistory($('feedbackHistory'),hasRows?groups.feedback.slice(1):groups.feedback,!hasRows);
 $('assistantWelcome').hidden=groups.assistant.length>0;
 updateFeedbackState();
}
async function runAI(task){
 if(!state.paper||state.busy)return;
 let attempt='',source='',page=reader.position().page,question=$('question').value.trim();
 if(task==='translation'){source=$('translationSource').value;attempt=$('translationRevision').value.trim()||$('translationAttempt').value;page=state.notes.translationPage||state.context?.page||page;if(!source.trim()||!attempt.trim()){toast('请先选择练习原文，并填写自己的译文。');return;}setWorkspace('practice');setPractice('translation');}
 else if(task==='feedback'){if(!['answerProblem','answerMethod','answerEvidence','answerLimit'].some(f=>$(f).value.trim())){toast('请先写下自己的解释，再获取反馈。');return;}attempt=answerText();setWorkspace('practice');setPractice('feedback');}
 else if(task==='summary'){attempt=answerText()+'\n个人笔记：'+$('personalNotes').value;setWorkspace('notes');}
 else{setWorkspace('assistant');if(task!=='preview'&&state.context){source=state.context.text;page=state.context.page;}if(task==='ask'&&!question){toast('请先填写你的问题。');$('question').focus();return;}}
 if(['explain','translate'].includes(task)&&!source){toast('请先在 PDF 原文上选择一个句段。');return;}
 if(!state.configured){toast('请在模型设置中连接服务，选区和作答已保留。');await openSettings();return;}
 const pid=state.paper.id;state.busy=true;$('aiBusy').hidden=false;$('aiError').hidden=true;document.querySelectorAll('[data-ai],#questionForm button').forEach(b=>b.disabled=true);
 try{
  await flush();
  if(state.paper?.id!==pid)return;
  const result=await api('/api/learn',{paper_id:pid,task,page,question:task==='ask'?question:'',source,attempt,...(task==='feedback'?{study_snapshot:studySnapshot(state.notes)}:{})});
  if(state.paper?.id===pid){
   state.runs.unshift(result);
   renderResults();
   if(state.view==='reader'){
    if(task==='feedback'&&state.workspace==='practice'&&state.practice==='feedback'){
     const next=currentAnswer();
     $('answer-card-'+next).open=true;
     $('answer-card-'+next).scrollIntoView({block:'start'});
    }else if(task!=='feedback'){
     const holder=$(task==='summary'?'notesResults':task==='translation'?'practiceResults':'assistantResults');
     holder.scrollIntoView({block:'nearest'});
    }
    toast('反馈已保存，请对照原文核查。');
   }
  }
 }
 catch(e){if(state.paper?.id===pid){$('aiError').textContent=e.message;$('aiError').hidden=false;}}
 finally{state.busy=false;$('aiBusy').hidden=true;document.querySelectorAll('[data-ai],#questionForm button').forEach(b=>b.disabled=false);}
}
for(const b of document.querySelectorAll('[data-ai]'))b.onclick=()=>runAI(b.dataset.ai).catch(e=>toast(e.message));
$('questionForm').onsubmit=e=>{e.preventDefault();runAI('ask').catch(err=>toast(err.message));};
for(const b of document.querySelectorAll('[data-workspace]'))b.onclick=()=>setWorkspace(b.dataset.workspace);
for(const b of document.querySelectorAll('[data-practice]'))b.onclick=()=>setPractice(b.dataset.practice);
$('panelToggle').onclick=()=>setPanel(!state.panelOpen);$('closePanel').onclick=()=>setPanel(false);$('focusBtn').onclick=()=>setPanel(!state.panelOpen);
$('expandPanel').onclick=()=>{const expanded=$('toolPanel').classList.toggle('expanded');$('expandPanel').textContent=expanded?'收回':'展开';};
$('clearContext').onclick=e=>{e.preventDefault();setContext(null);};$('contextLocate').onclick=()=>{if(state.context)locateEvidence({page:state.context.page,text:state.context.text,anchor:state.context.locator});};
$('zoomIn').onclick=()=>{finishPanelMotion();reader.zoom(.15).catch(e=>toast(e.message));};
$('zoomOut').onclick=()=>{finishPanelMotion();reader.zoom(-.15).catch(e=>toast(e.message));};
$('fitBtn').onclick=()=>{finishPanelMotion();$('columnMode').value='';reader.fitWidth().catch(e=>toast(e.message));};
$('columnMode').onchange = () => {
 finishPanelMotion();
 const side = $('columnMode').value;
 let operation;
 if (side === 'zoom-in' || side === 'zoom-out') operation = reader.zoom(side === 'zoom-in' ? .15 : -.15);
 else operation = side ? reader.fitColumn(side) : reader.fitWidth();
 operation.catch(error => toast(error.message));
};
$('compactPanel').onclick = () => setCompact(!$('toolPanel').classList.contains('compact'));
function jumpPage(page) { finishPanelMotion(); reader.jump(page); }
$('pageInput').onchange=()=>jumpPage($('pageInput').value);$('pageInput').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();jumpPage($('pageInput').value);$('readerScroll').focus();}};$('outlineBtn').onclick=()=>$('outlineDialog').showModal();$('libraryBtn').onclick=()=>$('libraryDialog').showModal();
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
let dragging=null;$('panelResizer').onpointerdown=e=>{finishPanelMotion();dragging={x:e.clientX,width:parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'))||400};$('panelResizer').setPointerCapture(e.pointerId);e.preventDefault();};
function setWidth(width){width=Math.round(Math.max(320,Math.min(600,innerWidth*.55,width)));document.documentElement.style.setProperty('--assistant-width',width+'px');$('panelResizer').setAttribute('aria-valuenow',width);state.notes.panelWidth=width;queueSave();}
$('panelResizer').onpointermove=e=>{if(dragging)setWidth(dragging.width+dragging.x-e.clientX);};$('panelResizer').onpointerup=()=>dragging=null;$('panelResizer').onpointercancel=()=>dragging=null;
$('panelResizer').onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const width=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'))||400;setWidth(width+(e.key==='ArrowLeft'?20:-20));}};
matchMedia('(max-width:840px)').addEventListener('change',e=>{if(state.paper)setPanel(e.matches?false:state.notes.panelOpen!==false,{save:false,motion:false});});
reducedMotion.addEventListener('change',finishPanelMotion);
async function loadConfig(){const config=await api('/api/config');state.configured=config.configured;$('connectionHint').hidden=config.configured;return config;}
async function openSettings(){const cfg=await loadConfig();$('endpoint').value=cfg.endpoint;$('modelName').value=cfg.model;$('apiKey').value='';$('settingsError').hidden=true;$('settingsDialog').showModal();}
$('settingsBtn').onclick=()=>openSettings().catch(e=>toast(e.message));$('connectBtn').onclick=$('settingsBtn').onclick;
$('settingsForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/config',{endpoint:$('endpoint').value,model:$('modelName').value,key:$('apiKey').value});$('apiKey').value='';await loadConfig();$('settingsDialog').close();toast('连接已保存到运行内存，尚未发起模型调用。');}catch(err){$('settingsError').textContent=err.message;$('settingsError').hidden=false;}};
$('clearConfig').onclick=async()=>{await api('/api/config/clear',{});$('apiKey').value='';await loadConfig();$('settingsDialog').close();toast('模型连接已清除。');};
$('paperTitle').onclick=()=>{if(!state.paper)return;const m=state.paper.metadata;$('metaTitle').value=state.paper.title;$('metaDoi').value=m.doi||'';$('metaDate').value=m.published||'';$('metaSource').value=m.source||'';$('metaReview').value=m.review_status||'待核实';$('metadataError').hidden=true;$('metadataDialog').showModal();};
$('metadataForm').onsubmit=async e=>{e.preventDefault();const m={doi:$('metaDoi').value,published:$('metaDate').value,source:$('metaSource').value,review_status:$('metaReview').value};try{await api('/api/metadata',{paper_id:state.paper.id,title:$('metaTitle').value,...m});state.paper.metadata={...state.paper.metadata,...m};studyUI.opened();state.paper.title=$('metaTitle').value;$('paperTitle').textContent=state.paper.title;$('paperTitle').title=state.paper.title;await refreshLibrary();$('metadataDialog').close();toast('论文详情已保存。');}catch(err){$('metadataError').textContent=err.message;$('metadataError').hidden=false;}};
$('uploadBtn').onclick=()=>$('fileInput').click();$('emptyUpload').onclick=$('uploadBtn').onclick;
$('fileInput').onchange=async()=>{const file=$('fileInput').files[0];if(!file)return;if(file.size>30*1024*1024){toast('请选择不超过 30 MB 的 PDF。');return;}$('uploadBtn').disabled=true;$('emptyUpload').disabled=true;try{const p=await api('/api/upload',await file.arrayBuffer(),{'Content-Type':'application/pdf','X-Filename':encodeURIComponent(file.name)});await openPaper(p.id);}catch(e){toast(e.message);}finally{$('uploadBtn').disabled=false;$('emptyUpload').disabled=false;$('fileInput').value='';}};
$('sampleBtn').onclick=async()=>{$('sampleBtn').disabled=true;try{const p=await api('/api/sample',{});await openPaper(p.id);}catch(e){toast(e.message);}finally{$('sampleBtn').disabled=false;}};
$('exportBtn').onclick=async()=>{try{await flush();const pid=state.paper.id;const result=await api('/api/study/export?paper_id='+pid);const url=URL.createObjectURL(new Blob([result.markdown],{type:'text/markdown;charset=utf-8'}));const a=el('a');a.href=url;a.download=state.paper.title.replace(/[<>:\"/\\|?*]/g,'_').slice(0,70)+'-学习笔记.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('笔记已导出。');}catch(e){toast(e.message);}};
function lastPaper() {
 const id = localRead('paperStudio.lastPaper');
 return state.papers.find(paper => paper.id === id);
}
function renderHome() {
 const recent = lastPaper();
 $('homeResume').hidden = !recent;
 $('emptyUpload').className = recent ? 'secondary' : 'primary';
 $('homePaperLabel').textContent = recent ? '上次打开' : '英文原文';
 $('homePaperTitle').textContent = recent ? recent.title : '从原文找依据';
 $('homeRecent').hidden = !state.papers.length;
 $('homeRecentList').replaceChildren();
 for (const paper of state.papers.slice(0, 3)) {
  const row = el('li');
  const button = el('button', 'home-paper-link');
  const imported = new Date(paper.created * 1000).toLocaleDateString('zh-CN');
  button.append(el('span', '', paper.title), el('time', '', imported), el('span', 'home-paper-arrow', '↗'));
  button.onclick = () => openPaper(paper.id).catch(error => toast(error.message));
  row.append(button);
  $('homeRecentList').append(row);
 }
}
function setView(view) {
 state.view = view;
 const reading = view === 'reader';
 $('homeView').hidden = view !== 'home';
 $('workspace').hidden = !reading;
 $('paperTitle').hidden = !reading;
 $('saveStatus').hidden = !reading;
 $('exportBtn').hidden = !reading;
 const current = {home:'homeBtn', reader:'readBtn', discovery:'discoverBtn'}[view];
 for (const id of ['homeBtn', 'readBtn', 'discoverBtn']) {
  if (id === current) $(id).setAttribute('aria-current', 'page');
  else $(id).removeAttribute('aria-current');
 }
 if (!reading) showSelection(null);
 if (view === 'home') renderHome();
}
function parkReader() {
 finishPanelMotion();
 if (state.view === 'reader') state.parkedPosition = reader.position();
}
function restoreReader() {
 setView('reader');
 const position = state.parkedPosition;
 if (position) {
  reader.jump(position.page, position.fraction);
  reader.scroll.scrollLeft = position.scrollLeft || 0;
 }
 state.parkedPosition = null;
}
async function showHome() {
 if (!state.restoring) ++openSerial;
 await flush();
 parkReader();
 await discoveryUI.hide({restore:false});
 setView('home');
 $('homeTitle').focus({preventScroll:true});
}
async function resumeReading() {
 if (state.view === 'reader') return;
 const paper = lastPaper() || state.papers[0];
 if (!paper) { await showHome(); return; }
 if (state.paper?.id === paper.id && reader.doc) {
  await discoveryUI.hide({restore:false});
  restoreReader();
 } else await openPaper(paper.id);
}
const discoveryUI = initDiscovery({
 api, toast, getPaper:()=>state.paper, openSettings, refreshLibrary, openPaper,
 enter: async () => {
  if (!state.restoring) ++openSerial;
  await flush();
  state.discoveryReturn = state.view;
  parkReader();
  setView('discovery');
 },
 leave: async restore => {
  if (!restore) return;
  if (state.discoveryReturn === 'reader' && state.paper) restoreReader();
  else setView('home');
 }
});
$('homeBtn').onclick = () => showHome().catch(error => toast(error.message));
$('readBtn').onclick = () => resumeReading().catch(error => toast(error.message));
$('homeResume').onclick = $('readBtn').onclick;
$('homeDiscover').onclick = $('discoverBtn').onclick;
$('homeLibrary').onclick = $('libraryBtn').onclick;
const studyUI=initLearningFlow({api,toast,runAI,currentAnswer,feedbackChanged:updateFeedbackState,getPaper:()=>state.paper,getNotes:()=>state.notes,getContext:()=>state.context,queueSave,flush,setWorkspace,setPractice,position:()=>reader.position(),locate:locateEvidence,openPaper,
 searchNext:query=>discoveryUI.searchFromLearning(query)});
for(const f of fields)$(f).addEventListener('input',queueSave);
for(const f of answerFields)$(f).addEventListener('input',updateFeedbackState);
async function init() {
 setView('home');
 const [, , sample] = await Promise.all([refreshLibrary(), loadConfig(), api('/api/sample-status')]);
 $('sampleBtn').hidden = !sample.available;
 discoveryUI.start().catch(error => toast('主题更新检查失败：' + error.message));
}
init().catch(error => toast('打开失败：' + error.message));
