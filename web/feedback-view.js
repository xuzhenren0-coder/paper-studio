export const feedbackLabels={answerProblem:'研究问题',answerMethod:'方法与假设',answerEvidence:'关键证据',answerLimit:'局限与待解问题'};
export const feedbackStatuses={supported:'有依据',contradicted:'与原文不符',insufficient:'材料不足'};
export function studySnapshot(notes){return {...Object.fromEntries(Object.keys(feedbackLabels).map(f=>[f,String(notes[f]||'')])),studyEvidence:notes.studyEvidence||{}};}
export function feedbackIsStale(run,field,answer,evidence){
 const previous=run.study_snapshot;
 if(!previous)return false;
 const key=items=>JSON.stringify((items||[]).map(item=>[
  item.page,item.quote,item.anchor?.document,item.anchor?.offset,item.anchor?.prefix,item.anchor?.suffix
 ]));
 return previous[field]!==answer||key(previous.studyEvidence?.[field])!==key(evidence);
}
export function renderFeedback(run,host,{locate,supplement,revise},onlyField){
 const make=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;};
 const byRef=new Map((run.citations||[]).map(c=>[c.ref,c]));
 for(const row of run.feedback){
  if(onlyField&&row.field!==onlyField)continue;
  const card=make('section','feedback-item'),heading=make('div','feedback-heading');
  heading.append(make('h3','',onlyField?'本项反馈':feedbackLabels[row.field]||row.label),make('span','feedback-status '+row.status,feedbackStatuses[row.status]||'材料不足'));card.append(heading);
  for(const claim of row.claims){
   const block=make('div','feedback-claim');block.append(make('p','',claim.text));
   if(claim.status!==row.status)block.prepend(make('small','feedback-status '+claim.status,feedbackStatuses[claim.status]));
   if(claim.citation_issue)block.append(make('small','feedback-missing','引用未通过核对，此判断材料不足。'));
   for(const ref of claim.evidence_ids){const c=byRef.get(ref);if(!c)continue;const button=make('button','citation',`PDF 第 ${c.page} 页 · 查看原文`);button.append(make('em','',c.quote));button.onclick=()=>locate(c);block.append(button);}
   card.append(block);
  }
  if(row.hint)card.append(make('p','feedback-hint',row.hint));
  if(row.analysis){const detail=make('details','feedback-analysis');detail.append(make('summary','','更多分析'),make('p','',row.analysis));card.append(detail);}
  if(row.status==='insufficient'){const add=make('button','text-button feedback-supplement','补选原文');add.onclick=()=>supplement(row.field);card.append(add);}
  const edit = make('button', 'text-button feedback-revise', '回到这项作答');
  edit.onclick = () => revise(row.field);
  card.append(edit);
  host.append(card);
 }
}
