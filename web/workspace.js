import {PaperReader} from '/reader.js';
import {initDiscovery} from '/discovery-ui.js';
const $=id=>document.getElementById(id);
const state={paper:null,papers:[],notes:{},runs:[],workspace:'assistant',practice:'translation',panelOpen:true,context:null,selection:null,configured:false,busy:false,restoring:false};
const fields=['question','translationSource','translationAttempt','answerProblem','answerMethod','answerEvidence','answerLimit','personalNotes'];
const taskNames={preview:'论文导读',ask:'追问',explain:'选段解释',translate:'选段翻译',translation:'翻译练习反馈',feedback:'自主解释反馈',critique:'辅助批判',summary:'结构化草稿'};
const mobile=()=>matchMedia('(max-width:840px)').matches;
let saveTimer,saveQueue=Promise.resolve(),saving=false,dirty=false,openSerial=0,toastTimer;
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5000);}
function localRead(key){try{return localStorage.getItem(key)}catch{return null}}
function localWrite(key,value){try{localStorage.setItem(key,value)}catch{}}
async function api(path,body,headers={}){const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Request':'1',...headers},body:body instanceof ArrayBuffer?body:JSON.stringify(body)};const r=await fetch(path,options);const data=await r.json();if(!r.ok)throw Error(data.error||'操作失败');return data;}
const reader=new PaperReader($('readerScroll'),$('pdfPages'),{
 onPosition:position=>{if(!state.paper||state.discoveryActive)return;$('pageInput').value=position.page;$('zoomLabel').textContent=Math.round(position.scale*100)+'%';if(!state.restoring){state.notes.readerPosition=position;queueSave();}},
 onSelection:selection=>showSelection(selection),
 onStatus:message=>{$('readerStatus').textContent=message;$('readerStatus').classList.toggle('ready',message==='可直接选择原文文字');},
 onOutline:items=>renderOutline(items)
});
function capture(){const n={...state.notes};for(const f of fields)n[f]=$(f).value;n.activeWorkspace=state.workspace;n.practice=state.practice;n.context=state.context;n.readerPosition=state.discoveryActive?state.discoveryPosition:reader.position();n.currentPage=n.readerPosition.page;
 if(mobile())n.mobilePanelOpen=state.panelOpen;else n.panelOpen=state.panelOpen;
 state.notes=n;return structuredClone(n);}
function queueSave(){if(!state.paper||state.restoring)return;dirty=true;$('saveStatus').textContent='正在保存…';clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveNow().catch(()=>{}),650);}
function saveNow(){if(!state.paper)return Promise.resolve();clearTimeout(saveTimer);saveTimer=null;const pid=state.paper.id,body=capture();dirty=false;
 saveQueue=saveQueue.catch(()=>{}).then(async()=>{saving=true;try{await api('/api/notes',{paper_id:pid,body});if(state.paper?.id===pid&&!dirty)$('saveStatus').textContent='已保存到本机';}finally{saving=false;}}).catch(e=>{if(state.paper?.id===pid){dirty=true;$('saveStatus').textContent='保存失败';}toast('保存失败：'+e.message);throw e;});return saveQueue;}
async function flush(){if(dirty||saveTimer)await saveNow();else await saveQueue;}
window.addEventListener('beforeunload',e=>{if(dirty||saving||state.busy){e.preventDefault();e.returnValue='';}});
for(const f of fields)$(f).addEventListener('input',queueSave);
function setPanel(open,{save=true}={}){state.panelOpen=open;$('workArea').classList.toggle('panel-open',open);$('panelToggle').classList.toggle('active',open);$('panelToggle').setAttribute('aria-expanded',String(open));$('focusBtn').textContent=open?'专注阅读':'退出专注';if(save)queueSave();}
function setWorkspace(name,{open=true,save=true}={}){if(!['assistant','practice','notes'].includes(name))name='assistant';state.workspace=name;document.querySelectorAll('[data-workspace]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.workspace===name)));document.querySelectorAll('[data-view]').forEach(v=>v.hidden=v.dataset.view!==name);if(open)setPanel(true,{save:false});$('aiError').hidden=true;if(save)queueSave();}
function setPractice(name,{save=true}={}){state.practice=name==='feedback'?'feedback':'translation';document.querySelectorAll('[data-practice]').forEach(b=>b.classList.toggle('selected',b.dataset.practice===state.practice));document.querySelectorAll('[data-practice-view]').forEach(v=>v.hidden=v.dataset.practiceView!==state.practice);if(save)queueSave();}
function setContext(context,{save=true}={}){state.context=context;$('contextBlock').hidden=!context;if(context){$('contextLabel').textContent=`PDF 第 ${context.page} 页 · 所选原文`;$('contextText').textContent=context.text;$('contextBlock').open=true;}$('questionScope').textContent=context?'针对选中的原文提问':'结合当前页与相关片段';if(save)queueSave();}
function showSelection(selection){state.selection=selection;const menu=$('selectionMenu');if(!selection){menu.hidden=true;$('selectionExtras').hidden=true;return;}menu.hidden=false;$('selectionExtras').hidden=true;$('selectionMore').setAttribute('aria-expanded','false');const width=menu.offsetWidth||260;const x=Math.max(8,Math.min(innerWidth-width-8,(selection.rect.left+selection.rect.right-width)/2));const above=selection.rect.top-menu.offsetHeight-9;const y=above>100?above:Math.min(innerHeight-menu.offsetHeight-12,selection.rect.bottom+9);menu.style.left=x+'px';menu.style.top=Math.max(60,y)+'px';}
async function selectionAction(action){const s=state.selection;if(!s)return;if(s.text.length>6000){toast('选区过长，请每次选择不超过 6000 字符的句段。');return;}
 if(s.page!==s.endPage&&action!=='note'){toast('跨页选文可能混入页眉和图注，请在同一页选择句段后操作。');return;}
 const context={text:s.text,page:s.page};setContext(context);showSelection(null);
 if(action==='note'){appendNote(`> ${s.text.replace(/\n/g,'\n> ')}\n\n来源：PDF 第 ${s.page}${s.endPage!==s.page?'—'+s.endPage:''} 页`);setWorkspace('notes');toast('原文摘录已加入笔记。');return;}
 if(action==='practice'){$('translationSource').value=s.text;setPractice('translation');setWorkspace('practice');queueSave();$('translationAttempt').focus();return;}
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
 for(const p of state.papers){const b=el('button','paper-item'+(p.id===state.paper?.id?' active':''));b.append(el('b','',p.title),el('small','',new Date(p.created*1000).toLocaleDateString('zh-CN')+' · 本地论文'));b.onclick=()=>openPaper(p.id).catch(e=>toast(e.message));list.append(b);}}
async function openPaper(id){
 const serial=++openSerial;await flush();const [paper,note,runs]=await Promise.all([api('/api/papers/'+id),api('/api/papers/'+id+'/notes'),api('/api/papers/'+id+'/runs')]);if(serial!==openSerial)return;
 state.restoring=true;state.paper=paper;state.notes=note.body;state.runs=runs;fields.forEach(f=>$(f).value=note.body[f]||'');
 $('emptyView').hidden=true;$('workspace').hidden=false;$('exportBtn').hidden=false;$('paperTitle').textContent=paper.title;$('paperTitle').title=paper.title+' · 点击查看来源';$('pageTotal').textContent='/ '+paper.pages.length;$('pageInput').max=paper.pages.length;
 if($('libraryDialog').open)$('libraryDialog').close();
 const workspace=note.body.activeWorkspace||'assistant';setWorkspace(workspace,{open:false,save:false});setPractice(note.body.practice||'translation',{save:false});setContext(note.body.context||null,{save:false});
 setPanel(mobile()?!!note.body.mobilePanelOpen:note.body.panelOpen!==false,{save:false});$('toolPanel').classList.remove('expanded');$('expandPanel').textContent='展开';
 const width=Math.max(320,Math.min(600,Number(note.body.panelWidth)||400));document.documentElement.style.setProperty('--assistant-width',width+'px');$('panelResizer').setAttribute('aria-valuenow',width);
 renderResults();$('saveStatus').textContent=note.updated?'记录已恢复':'本地保存';$('aiError').hidden=true;localWrite('paperStudio.lastPaper',id);await refreshLibrary();
 try{await reader.load('/api/papers/'+id+'/pdf',note.body.readerPosition||{page:note.body.currentPage||1,fraction:0,fit:true});}
 catch(e){if(serial===openSerial){$('readerStatus').textContent='PDF 打开失败，请重新打开论文或检查文件。';toast('无法打开原文：'+e.message);}}
 finally{if(serial===openSerial)state.restoring=false;}
}
function renderOutline(items){const list=$('outlineList');list.replaceChildren();if(!items.length){list.append(el('p','outline-description','这份 PDF 没有嵌入目录。可使用以下页码跳转。'));items=Array.from({length:state.paper?.pages.length||0},(_,i)=>({title:'PDF 第 '+(i+1)+' 页',page:i+1,depth:0}));}
 for(const item of items){const b=el('button','',item.title);b.style.paddingLeft=12+Math.min(item.depth,4)*12+'px';b.onclick=()=>{reader.jump(item.page);$('outlineDialog').close();};list.append(b);}}
function answerText(){return['研究问题：'+$('answerProblem').value,'方法与假设：'+$('answerMethod').value,'关键证据：'+$('answerEvidence').value,'局限与待解问题：'+$('answerLimit').value].join('\n\n');}
function renderResults(){for(const id of ['assistantResults','practiceResults','notesResults'])$(id).replaceChildren();
 const groups={assistant:[],practice:[],notes:[]};for(const run of state.runs){const group=['translation','feedback'].includes(run.task)?'practice':run.task==='summary'?'notes':'assistant';groups[group].push(run);}
 for(const [group,runs]of Object.entries(groups))for(const r of runs){
  const box=el('article','result-card');const title=el('div','result-title');title.append(el('b','',(taskNames[r.task]||r.task)+' · AI'),el('time','',new Date(r.created*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})));box.append(title);
  if(r.question)box.append(el('div','user-question',r.question));box.append(el('div','ai-text',r.text));const cites=el('div','citation-list');
  for(const c of r.citations||[]){const b=el('button','citation',`PDF 第 ${c.page} 页 · 查看原文 ↗`);b.append(el('em','',c.quote));b.onclick=()=>{reader.jump(c.page);if(mobile())setPanel(false);};cites.append(b);}
  box.append(cites,el('p','result-notice',`片段覆盖：PDF 第 ${(r.coverage_pages||[]).join('、')} 页。引用核对仅证明摘录存在，专业反馈尚未经人工验证。`));
  const save=el('button','result-save','保存到我的笔记');save.onclick=()=>{appendNote(`### ${taskNames[r.task]||r.task}（AI 辅助，待核查）\n\n${r.text}\n\n`+(r.citations||[]).map(c=>`- PDF 第 ${c.page} 页：${c.quote}`).join('\n'));toast('AI 内容已明确标识并加入笔记。');};box.append(save);$(group+'Results').append(box);
 }
 $('assistantWelcome').hidden=groups.assistant.length>0;
}
async function runAI(task){
 if(!state.paper||state.busy)return;
 let attempt='',source='',page=reader.position().page,question=$('question').value.trim();
 if(task==='translation'){source=$('translationSource').value;attempt=$('translationAttempt').value;page=state.context?.page||page;if(!source.trim()||!attempt.trim()){toast('请先选择练习原文，并填写自己的译文。');return;}setWorkspace('practice');setPractice('translation');}
 else if(task==='feedback'){if(!['answerProblem','answerMethod','answerEvidence','answerLimit'].some(f=>$(f).value.trim())){toast('请先写下自己的解释，再获取反馈。');return;}attempt=answerText();setWorkspace('practice');setPractice('feedback');}
 else if(task==='summary'){attempt=answerText()+'\n个人笔记：'+$('personalNotes').value;setWorkspace('notes');}
 else{setWorkspace('assistant');if(task!=='preview'&&state.context){source=state.context.text;page=state.context.page;}if(task==='ask'&&!question){toast('请先填写你的问题。');$('question').focus();return;}}
 if(['explain','translate'].includes(task)&&!source){toast('请先在 PDF 原文上选择一个句段。');return;}
 if(!state.configured){toast('请在模型设置中连接服务，选区和作答已保留。');await openSettings();return;}
 await flush();const pid=state.paper.id;state.busy=true;$('aiBusy').hidden=false;$('aiError').hidden=true;document.querySelectorAll('[data-ai],#questionForm button').forEach(b=>b.disabled=true);
 try{const result=await api('/api/learn',{paper_id:pid,task,page,question:task==='ask'?question:'',source,attempt});if(state.paper?.id===pid){state.runs.unshift(result);renderResults();const holder=$(task==='summary'?'notesResults':['translation','feedback'].includes(task)?'practiceResults':'assistantResults');holder.scrollIntoView({block:'nearest'});toast('反馈已保存，请对照原文核查。');}}
 catch(e){if(state.paper?.id===pid){$('aiError').textContent=e.message;$('aiError').hidden=false;}}
 finally{state.busy=false;$('aiBusy').hidden=true;document.querySelectorAll('[data-ai],#questionForm button').forEach(b=>b.disabled=false);}
}
for(const b of document.querySelectorAll('[data-ai]'))b.onclick=()=>runAI(b.dataset.ai).catch(e=>toast(e.message));
$('questionForm').onsubmit=e=>{e.preventDefault();runAI('ask').catch(err=>toast(err.message));};
for(const b of document.querySelectorAll('[data-workspace]'))b.onclick=()=>setWorkspace(b.dataset.workspace);
for(const b of document.querySelectorAll('[data-practice]'))b.onclick=()=>setPractice(b.dataset.practice);
$('panelToggle').onclick=()=>setPanel(!state.panelOpen);$('closePanel').onclick=()=>setPanel(false);$('focusBtn').onclick=()=>setPanel(!state.panelOpen);
$('expandPanel').onclick=()=>{const expanded=$('toolPanel').classList.toggle('expanded');$('expandPanel').textContent=expanded?'收回':'展开';};
$('clearContext').onclick=e=>{e.preventDefault();setContext(null);};$('contextLocate').onclick=()=>{if(state.context)reader.jump(state.context.page);if(mobile())setPanel(false);};
$('zoomIn').onclick=()=>reader.zoom(.15).catch(e=>toast(e.message));$('zoomOut').onclick=()=>reader.zoom(-.15).catch(e=>toast(e.message));$('fitBtn').onclick=()=>reader.fitWidth().catch(e=>toast(e.message));
$('pageInput').onchange=()=>reader.jump($('pageInput').value);$('pageInput').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();reader.jump($('pageInput').value);$('readerScroll').focus();}};$('outlineBtn').onclick=()=>$('outlineDialog').showModal();$('libraryBtn').onclick=()=>$('libraryDialog').showModal();
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
let dragging=null;$('panelResizer').onpointerdown=e=>{dragging={x:e.clientX,width:parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'))||400};$('panelResizer').setPointerCapture(e.pointerId);e.preventDefault();};
function setWidth(width){width=Math.round(Math.max(320,Math.min(600,innerWidth*.55,width)));document.documentElement.style.setProperty('--assistant-width',width+'px');$('panelResizer').setAttribute('aria-valuenow',width);state.notes.panelWidth=width;queueSave();}
$('panelResizer').onpointermove=e=>{if(dragging)setWidth(dragging.width+dragging.x-e.clientX);};$('panelResizer').onpointerup=()=>dragging=null;$('panelResizer').onpointercancel=()=>dragging=null;
$('panelResizer').onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const width=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'))||400;setWidth(width+(e.key==='ArrowLeft'?20:-20));}};
matchMedia('(max-width:840px)').addEventListener('change',e=>{if(state.paper)setPanel(e.matches?false:state.notes.panelOpen!==false,{save:false});});
async function loadConfig(){const config=await api('/api/config');state.configured=config.configured;$('connectionHint').hidden=config.configured;return config;}
async function openSettings(){const cfg=await loadConfig();$('endpoint').value=cfg.endpoint;$('modelName').value=cfg.model;$('apiKey').value='';$('settingsError').hidden=true;$('settingsDialog').showModal();}
$('settingsBtn').onclick=()=>openSettings().catch(e=>toast(e.message));$('connectBtn').onclick=$('settingsBtn').onclick;
$('settingsForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/config',{endpoint:$('endpoint').value,model:$('modelName').value,key:$('apiKey').value});$('apiKey').value='';await loadConfig();$('settingsDialog').close();toast('连接已保存到运行内存，尚未发起模型调用。');}catch(err){$('settingsError').textContent=err.message;$('settingsError').hidden=false;}};
$('clearConfig').onclick=async()=>{await api('/api/config/clear',{});$('apiKey').value='';await loadConfig();$('settingsDialog').close();toast('模型连接已清除。');};
$('paperTitle').onclick=()=>{if(!state.paper)return;const m=state.paper.metadata;$('metaTitle').value=state.paper.title;$('metaDoi').value=m.doi||'';$('metaDate').value=m.published||'';$('metaSource').value=m.source||'';$('metaReview').value=m.review_status||'待核实';$('metadataError').hidden=true;$('metadataDialog').showModal();};
$('metadataForm').onsubmit=async e=>{e.preventDefault();const m={doi:$('metaDoi').value,published:$('metaDate').value,source:$('metaSource').value,review_status:$('metaReview').value};try{await api('/api/metadata',{paper_id:state.paper.id,title:$('metaTitle').value,...m});state.paper.metadata=m;state.paper.title=$('metaTitle').value;$('paperTitle').textContent=state.paper.title;$('paperTitle').title=state.paper.title;await refreshLibrary();$('metadataDialog').close();toast('论文详情已保存。');}catch(err){$('metadataError').textContent=err.message;$('metadataError').hidden=false;}};
$('uploadBtn').onclick=()=>$('fileInput').click();$('emptyUpload').onclick=$('uploadBtn').onclick;
$('fileInput').onchange=async()=>{const file=$('fileInput').files[0];if(!file)return;if(file.size>30*1024*1024){toast('请选择不超过 30 MB 的 PDF。');return;}$('uploadBtn').disabled=true;try{const p=await api('/api/upload',await file.arrayBuffer(),{'Content-Type':'application/pdf','X-Filename':encodeURIComponent(file.name)});await openPaper(p.id);}catch(e){toast(e.message);}finally{$('uploadBtn').disabled=false;$('fileInput').value='';}};
$('sampleBtn').onclick=async()=>{$('sampleBtn').disabled=true;try{const p=await api('/api/sample',{});await openPaper(p.id);}catch(e){toast(e.message);}finally{$('sampleBtn').disabled=false;}};
$('exportBtn').onclick=async()=>{try{await flush();const p=state.paper,n=capture();let text=`# ${p.title}\n\nDOI：${p.metadata.doi||'待核实'}\n发表日期：${p.metadata.published||'待核实'}\n来源：${p.metadata.source||'待核实'}\n\n## 我的四项解释\n\n${answerText()}\n\n## 英译中练习\n\n${n.translationSource||''}\n\n我的译文：${n.translationAttempt||''}\n\n## 我的笔记\n\n${n.personalNotes||''}\n\n## AI 辅助内容\n\n引用存在不代表推理正确，专业反馈尚未经人工核验。\n`;
 for(const r of [...state.runs].reverse()){text+=`\n### ${taskNames[r.task]||r.task}\n\n${r.text}\n`;for(const c of r.citations||[])text+=`\n- PDF 第 ${c.page} 页：${c.quote}\n`;}
 const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=el('a');a.href=url;a.download=p.title.replace(/[<>:"/\\|?*]/g,'_').slice(0,70)+'-学习笔记.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('笔记已导出。');}catch(e){toast(e.message);}};
const discoveryUI=initDiscovery({api,toast,getPaper:()=>state.paper,openSettings,refreshLibrary,openPaper:async id=>{await discoveryUI.hide();await openPaper(id);},enter:async()=>{await flush();state.discoveryPosition=reader.position();state.discoveryActive=true;showSelection(null);$('workspace').hidden=true;$('emptyView').hidden=true;$('exportBtn').hidden=true;},leave:async()=>{state.discoveryActive=false;if(state.paper){$('workspace').hidden=false;$('exportBtn').hidden=false;reader.jump(state.discoveryPosition?.page||1,state.discoveryPosition?.fraction||0);}else $('emptyView').hidden=false;}});
async function init(){await Promise.all([refreshLibrary(),loadConfig()]);const sample=await api('/api/sample-status');$('sampleBtn').hidden=!sample.available;const recent=localRead('paperStudio.lastPaper');const p=state.papers.find(p=>p.id===recent)||state.papers[0];if(p)await openPaper(p.id);else $('emptyView').hidden=false;discoveryUI.start().catch(e=>toast('主题更新检查失败：'+e.message));}
init().catch(e=>{$('emptyView').hidden=false;toast('打开失败：'+e.message);});
