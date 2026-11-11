import {feedbackLabels as labels} from '/feedback-view.js';

export function initLearningFlow(h){
 const $=id=>document.getElementById(id),node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;};
 let snapshot=null,serial=0,exerciseBusy=false,nextSerial=0;
 const removedEvidence=new Map();
 const sameEvidence=(left,right)=>left.page===right.page&&left.quote===right.quote
  &&(left.anchor?.prefix||'')===(right.anchor?.prefix||'')
  &&(left.anchor?.suffix||'')===(right.anchor?.suffix||'');
 const section=document.querySelector('[data-view="study"]');
 section.innerHTML=`<div class="study-scroll"><div class="study-heading"><h2>本篇学习</h2><span id="studyProgress"></span></div><div id="studySource" class="study-source"></div><details id="studyGoals" open><summary id="studyGoalSummary">阅读目标与问题</summary><label for="studyGoal">阅读目标</label><input id="studyGoal" maxlength="1000" placeholder="例如：理解低附着路面的横向控制"><label for="studyQuestion">带着什么问题读？</label><textarea id="studyQuestion" rows="2" maxlength="1000" placeholder="这篇论文能帮我回答什么？"></textarea></details><div class="study-tools"><button id="studyPreview" class="text-button">中文预读</button><button id="studyCritique" class="text-button">批判阅读</button></div><ol id="studySteps" class="study-steps"></ol><div class="study-actions"><button id="studyContinue" class="primary">继续学习</button><button id="studyComplete" class="secondary" disabled>完成本轮学习</button></div><button id="nextPaperBtn" class="secondary full">推荐下一篇</button><div id="nextPaperResults" class="next-paper-results"></div></div>`;
 const translation=document.querySelector('[data-practice-view="translation"]');
 const extra=node('div','exercise-review');extra.innerHTML=`<label for="translationRevision">修改后的译文</label><textarea id="translationRevision" rows="3" placeholder="对照原文和反馈修改"></textarea><label for="translationReflection">这次学到什么？</label><textarea id="translationReflection" rows="2" placeholder="术语、逻辑关系或容易误解的地方"></textarea><button id="saveExercise" class="secondary">保存这次练习</button><details id="exerciseHistory"><summary>练习记录 <span id="exerciseCount">0</span></summary><div id="exerciseHistoryList"></div></details>`;translation.append(extra);
 const dialog=node('dialog','evidence-dialog');dialog.innerHTML='<div class="dialog-heading"><h2>这段原文支持哪一项？</h2><button type="button" class="close-icon" aria-label="关闭原文依据">×</button></div><div id="evidenceTargets"></div>';document.body.append(dialog);dialog.querySelector('.close-icon').onclick=()=>dialog.close();
 for(const [field,label]of Object.entries(labels)){
  const target=node('button','secondary full',label);
  target.onclick=async()=>{
   try{
    const c=h.getContext();
    if(!c)return;
    const pid=h.getPaper().id;
    const evidence=await h.api('/api/study/evidence',{paper_id:pid,page:c.page,source:c.text,locator:c.locator});
    if(h.getPaper()?.id!==pid)return;
    const n=h.getNotes();n.studyEvidence??={};
    const entries=n.studyEvidence[field]??=[];
    if(!entries.some(item=>sameEvidence(item,evidence))){
     if(entries.length>=6)throw Error('每项最多保留6段依据。');
     entries.push(evidence);
    }
    dialog.close();
    h.setPractice('feedback');h.setWorkspace('practice');
    openAnswer(field);
    evidenceChanged(field);
    $('answer-card-'+field).scrollIntoView({block:'nearest'});
    h.toast('已加入原文依据');
   }catch(e){h.toast(e.message);}
  };
  $('evidenceTargets').append(target);
  const answer=$(field),labelNode=answer.previousElementSibling;
  const card=node('details','answer-card');
  card.id='answer-card-'+field;
  const heading=node('summary','answer-heading');
  const status=node('span','answer-status');
  status.id='answer-status-'+field;
  heading.append(node('span','answer-title',label),status);
  const body=node('div','answer-body');
  labelNode.textContent='我的作答';
  labelNode.before(card);
  const evidence=node('div','study-evidence');
  evidence.id='evidence-'+field;
  const feedback=node('div','answer-feedback');
  feedback.id='feedback-'+field;
  body.append(labelNode,answer,evidence,feedback);
  card.append(heading,body);
 }
 function openAnswer(field){$('answer-card-'+field).open=true;}
 function evidenceChanged(field){
  renderEvidence(field);
  h.feedbackChanged();
  h.queueSave();
 }
 function renderEvidence(onlyField) {
  for (const field of onlyField?[onlyField]:Object.keys(labels)) {
   const box = $('evidence-' + field);
   box.replaceChildren();
   const entries=h.getNotes().studyEvidence?.[field]||[];
   if(entries.length)box.append(node('div','evidence-label','原文依据'));
   for (const [index, evidence] of entries.entries()) {
    const row = node('div', 'evidence-row');
    const content = node('div', 'evidence-content');
    const locate = node('button', 'evidence-quote', `第 ${evidence.page} 页 · 查看原句`);
    locate.onclick = () => h.locate(evidence);
    const excerpt = node('details', 'evidence-excerpt');
    excerpt.append(node('summary', '', '展开摘录'), node('blockquote', '', evidence.quote));
    const remove = node('button', 'text-button', '移除');
    remove.onclick = () => {
     h.getNotes().studyEvidence[field].splice(index, 1);
     removedEvidence.set(field,{index,evidence});
     evidenceChanged(field);
     $('undo-'+field).focus({preventScroll:true});
    };
    content.append(locate, excerpt);
    row.append(content, remove);
    box.append(row);
   }
   const removed=removedEvidence.get(field);
   if(removed){
    const notice=node('div','evidence-undo');
    const undo=node('button','text-button','撤销');
    undo.id='undo-'+field;
    undo.onclick=()=>{
     const entries=h.getNotes().studyEvidence[field];
     if(!entries.some(item=>sameEvidence(item,removed.evidence))){
      if(entries.length>=6){h.toast('已达 6 段依据上限。移除一段后可恢复。');return;}
      entries.splice(removed.index,0,removed.evidence);
     }
     removedEvidence.delete(field);
     evidenceChanged(field);
     box.querySelector('.evidence-quote')?.focus({preventScroll:true});
    };
    notice.append(node('span','','已移除一段依据'),undo);
    box.append(notice);
   }
  }
 }
 function navigate(step){if(step==='preview'){$('studyGoal').value.trim()?$('studyQuestion').focus():$('studyGoal').focus();}else if(step==='feedback'){h.setWorkspace('practice');h.setPractice('feedback');const field=h.currentAnswer();openAnswer(field);$(field).focus();}else if(step==='translation'){h.setWorkspace('practice');h.setPractice('translation');$('translationSource').focus();}else{h.setWorkspace('notes');$('personalNotes').focus();}}
 function render(){if(!snapshot)return;const done=snapshot.steps.filter(s=>s.done).length;$('studyGoalSummary').textContent='阅读目标'+($('studyGoal').value.trim()?' · '+$('studyGoal').value.trim():'与问题');$('studyProgress').textContent=snapshot.completed?'本轮已完成':`${done} / ${snapshot.steps.length}`;$('studySteps').replaceChildren();for(const step of snapshot.steps){const item=node('li',step.done?'done':''),button=node('button','',`${step.done?'✓':'○'} ${step.label}`);button.onclick=()=>navigate(step.id);item.append(button);$('studySteps').append(item);}
  $('studyComplete').disabled=!snapshot.ready||snapshot.completed;$('studyComplete').textContent=snapshot.completed?'已完成本轮学习':'完成本轮学习';$('studyContinue').textContent=snapshot.steps.find(s=>!s.done)?.label||'查看阅读笔记';$('exerciseCount').textContent=snapshot.exercises.length;renderHistory();
 }
 async function refresh(){const pid=h.getPaper()?.id;if(!pid)return;const ticket=++serial;try{const data=await h.api('/api/study?paper_id='+pid);if(h.getPaper()?.id!==pid||ticket!==serial)return;snapshot=data;render();}catch(e){h.toast(e.message);}}
 function opened(){snapshot=null;++nextSerial;removedEvidence.clear();$('nextPaperResults').replaceChildren();const p=h.getPaper(),m=p.metadata||{};$('studySource').textContent=[m.venue_name||m.source,m.published,m.doi,m.pdf_identity].filter(Boolean).join(' · ')||'出处待核实';renderEvidence();const current=h.currentAnswer();for(const field of Object.keys(labels))$('answer-card-'+field).open=field===current;$('studyGoals').open=!h.getNotes().studyGoal||!h.getNotes().studyQuestion;refresh();}
 async function saveExercise(){if(exerciseBusy)throw Error('正在保存练习，请稍候。');const p=h.getPaper();if(!p)return;const body={paper_id:p.id,page:h.getNotes().translationPage||h.getContext()?.page||h.position().page,source:$('translationSource').value,attempt:$('translationAttempt').value,revision:$('translationRevision').value,reflection:$('translationReflection').value};exerciseBusy=true;$('saveExercise').disabled=true;try{await h.flush();const item=await h.api('/api/study/exercises',body);if(h.getPaper()?.id===p.id)await refresh();return item;}finally{exerciseBusy=false;$('saveExercise').disabled=false;}}
 async function archiveDraft(){if($('translationSource').value.trim()&&$('translationAttempt').value.trim())await saveExercise();}
 async function beginTranslation(context){const pid=h.getPaper()?.id;if($('translationSource').value.trim()!==context.text.trim()){await archiveDraft();if(h.getPaper()?.id!==pid)throw Error('论文已切换，原练习已保存。');for(const id of ['translationAttempt','translationRevision','translationReflection'])$(id).value='';}$('translationSource').value=context.text;h.getNotes().translationPage=context.page;h.queueSave();}
 function renderHistory(){const box=$('exerciseHistoryList');box.replaceChildren();for(const item of snapshot.exercises){const card=node('article','exercise-entry');card.append(node('small','',`PDF 第 ${item.page} 页 · ${new Date(item.created*1000).toLocaleDateString('zh-CN')}`),node('blockquote','',item.source),node('p','',item.attempt));if(item.revision)card.append(node('p','exercise-revision','修改：'+item.revision));if(item.reflection)card.append(node('p','',item.reflection));const restore=node('button','text-button','继续修改');restore.onclick=async()=>{try{await archiveDraft();$('translationSource').value=item.source;$('translationAttempt').value=item.attempt;$('translationRevision').value=item.revision;$('translationReflection').value=item.reflection;h.getNotes().translationPage=item.page;h.queueSave();h.locate(item.page);}catch(e){h.toast(e.message);}};card.append(restore);box.append(card);}}
 $('studyPreview').onclick=()=>h.runAI('preview');$('studyCritique').onclick=()=>h.runAI('critique');
 $('studyContinue').onclick=()=>navigate(snapshot?.steps.find(s=>!s.done)?.id||'notes');
 $('studyComplete').onclick=async()=>{try{await archiveDraft();await h.flush();const pid=h.getPaper().id;const result=await h.api('/api/study/complete',{paper_id:pid});if(h.getPaper()?.id!==pid)return;snapshot=result;render();$('studyGoals').open=false;h.toast('已记录本轮学习完成');await loadNext();}catch(e){h.toast(e.message);}};
 $('saveExercise').onclick=()=>saveExercise().then(()=>h.toast('练习已保存')).catch(e=>h.toast(e.message));
 async function loadNext(){const p=h.getPaper();if(!p)return;const ticket=++nextSerial,box=$('nextPaperResults');box.textContent='正在整理候选…';try{await h.flush();const result=await h.api('/api/study/next?paper_id='+p.id);if(ticket!==nextSerial||h.getPaper()?.id!==p.id)return;box.replaceChildren();for(const paper of result.papers){const card=node('article','next-paper');card.append(node('h3','',paper.title_zh||paper.title));if(paper.title_zh)card.append(node('p','',paper.title));card.append(node('small','',`${paper.source} · ${paper.published}`),node('p','',paper.reason));const source=node('a','','查看出处 ↗');source.href=paper.official_url;source.target='_blank';source.rel='noopener noreferrer';card.append(source);if(paper.local_paper_id||paper.pdf_url){const read=node('button','secondary',paper.local_paper_id?'打开论文':'导入并阅读');read.onclick=async()=>{read.disabled=true;try{await archiveDraft();if(h.getPaper()?.id!==p.id)return;const imported=paper.local_paper_id?{paper_id:paper.local_paper_id}:await h.api('/api/discovery/import',{key:paper.key});if(h.getPaper()?.id===p.id)await h.openPaper(imported.paper_id);}catch(e){h.toast(e.message);}finally{read.disabled=false;}};card.append(read);}box.append(card);}
   if(!result.papers.length)box.append(node('p','description','现有储备没有匹配的未完成论文。'));const search=node('button','primary full','继续检索相关论文');search.onclick=()=>h.searchNext(result.query);box.append(search);
  }catch(e){if(ticket===nextSerial){box.textContent=e.message;}}}
 $('contextEvidence').onclick=()=>{if(h.getContext())dialog.showModal();};
 $('nextPaperBtn').onclick=loadNext;
 return {opened,refresh,beginTranslation,saveExercise,showEvidence:()=>{if(!h.getContext())return h.toast('请先选中一段原文。');dialog.showModal();},exportText:()=>snapshot?.exercises.map(x=>`\n### PDF 第 ${x.page} 页\n\n${x.source}\n\n我的译文：${x.attempt}\n\n修改：${x.revision||'尚未修改'}\n\n反思：${x.reflection||''}\n`).join('')||''};
}
