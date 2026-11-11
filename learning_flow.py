"""Local learning artifacts and explicit self-reported completion, never mastery scores."""
import hashlib,json,re,time
from datetime import date
import discovery,discovery_venues
import evidence_feedback

ANSWERS={'answerProblem':'研究问题','answerMethod':'方法与假设','answerEvidence':'关键证据','answerLimit':'局限与待解问题'}

def export_markdown(paper,notes,runs,exercises):
    m=paper.get('metadata') or {}
    lines=['# '+paper['title'],'','DOI：'+(m.get('doi') or '待核实'),'发表日期：'+(m.get('published') or '待核实'),'来源：'+(m.get('source') or '待核实'),
        '','## 阅读目标','',notes.get('studyGoal',''),'','阅读问题：'+notes.get('studyQuestion',''),'','## 我的四项解释']
    for field,label in ANSWERS.items():
        lines+=['','### '+label,'',notes.get(field,'')]
        for item in (notes.get('studyEvidence') or {}).get(field,[]):lines+=['',f'> {item["quote"]}',f'','原文依据：PDF 第 '+str(item['page'])+' 页']
    lines+=['','## 英译中练习草稿','',notes.get('translationSource',''),'','我的译文：'+notes.get('translationAttempt',''),'','修改：'+notes.get('translationRevision',''),'','反思：'+notes.get('translationReflection',''),'','## 已保存的英译中练习']
    for ex in reversed(exercises):lines+=['',f'### PDF 第 {ex["page"]} 页','',ex['source'],'','我的译文：'+ex['attempt'],'','修改：'+ex['revision'],'','反思：'+ex['reflection']]
    lines+=['','## 我的阅读笔记','',notes.get('personalNotes',''),'','## AI 辅助内容','', '以下内容与学生作答分开保存；引用匹配只证明摘录存在。']
    tasks={'preview':'论文导读','ask':'追问','explain':'选段解释','translate':'选段翻译','translation':'翻译练习反馈','feedback':'自主解释反馈','critique':'辅助批判','summary':'结构化草稿'}
    for run in reversed(runs):
        lines+=['','### '+tasks.get(run['task'],run['task'])+' · AI']
        if run.get('question'):lines+=['','当时的问题：'+run['question']]
        if run.get('attempt'):lines+=['','当时的作答：','',run['attempt']]
        if run.get('source'):lines+=['','当时的练习原文：','',run['source']]
        if run.get('study_snapshot'):
            lines+=['','当时绑定的原文依据：']
            for field,items in run['study_snapshot']['studyEvidence'].items():
                for item in items:lines+=['',f'- {ANSWERS[field]} · PDF 第 {item["page"]} 页：{item["quote"]}']
        lines+=['','AI 内容：','',run['text']]
        for c in run.get('citations',[]):lines+=['',f'- PDF 第 {c["page"]} 页：{c["quote"]}']
    return '\n'.join(lines)+'\n'

def signature(notes):
    fields=(*ANSWERS,'studyGoal','studyQuestion','personalNotes','studyEvidence')
    return hashlib.sha256(json.dumps({k:notes.get(k) for k in fields},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def progress(notes,exercises):
    evidence=notes.get('studyEvidence') or {}
    missing=[name for key,name in ANSWERS.items() if not str(notes.get(key,'')).strip() or not evidence.get(key)]
    steps=[{'id':'preview','label':'明确阅读问题','done':bool(str(notes.get('studyGoal','')).strip() and str(notes.get('studyQuestion','')).strip())},
        {'id':'feedback','label':'四项解释与原文依据','done':not missing},
        {'id':'translation','label':'保存英译中练习','done':bool(exercises)},
        {'id':'notes','label':'整理阅读笔记','done':bool(str(notes.get('personalNotes','')).strip())}]
    complete=notes.get('studyCompletion') or {}
    return {'steps':steps,'ready':all(s['done'] for s in steps),'completed':bool(complete.get('at') and complete.get('signature')==signature(notes) and all(s['done'] for s in steps)),
        'completed_at':complete.get('at'),'missing_explanations':missing,'exercise_count':len(exercises)}

class LearningFlow:
    def __init__(self,db,resolver):self.db=db;self.resolver=resolver
    def ensure(self):
        with self.db() as c:c.execute('CREATE TABLE IF NOT EXISTS learning_exercises(id TEXT PRIMARY KEY,paper_id TEXT,body TEXT,created REAL)')
    def notes(self,pid):
        with self.db() as c:row=c.execute('SELECT body FROM notes WHERE paper_id=?',(pid,)).fetchone()
        return json.loads(row['body']) if row else {}
    def exercises(self,pid):
        self.ensure()
        with self.db() as c:rows=c.execute('SELECT body FROM learning_exercises WHERE paper_id=? ORDER BY created DESC',(pid,)).fetchall()
        return [json.loads(r['body']) for r in rows]
    def state(self,pid):
        n=self.notes(pid);exercises=self.exercises(pid)
        return dict(progress(n,exercises),exercises=exercises)
    def evidence(self,paper,page,source,locator=None,include_anchor=False):
        try:page=int(page)
        except (ValueError,TypeError):raise ValueError('请选择原文所在页。') from None
        found=self.resolver(paper,page,str(source))
        result={'page':found['page'],'quote':found['selected']}
        if include_anchor:result['anchor']=evidence_feedback.anchor(paper,found['page'],found['selected'],locator)
        return result
    def validate_notes(self,paper,note,old):
        if 'studyEvidence' in note:
            evidence=note['studyEvidence']
            if not isinstance(evidence,dict) or any(k not in ANSWERS for k in evidence):raise ValueError('原文依据格式无效。')
            canonical={}
            for key,items in evidence.items():
                if not isinstance(items,list) or len(items)>6:raise ValueError('每项最多保留6段原文依据。')
                if any(not isinstance(item,dict) or not {'page','quote'}<=set(item) or set(item)-{'page','quote','anchor'} or ('anchor' in item and not isinstance(item['anchor'],dict)) for item in items):raise ValueError('原文依据格式无效。')
                canonical[key]=[self.evidence(paper,item['page'],item['quote'],item.get('anchor'),'anchor' in item) for item in items]
            note['studyEvidence']=canonical
        for field in ('studyGoal','studyQuestion'):
            if field in note and (not isinstance(note[field],str) or len(note[field])>1000):raise ValueError('阅读目标或问题过长。')
        # Only the explicit completion endpoint can create a completion record.
        note.pop('studyCompletion',None)
        if old.get('studyCompletion'):note['studyCompletion']=old['studyCompletion']
        return note
    def save_exercise(self,paper,body):
        self.ensure();evidence=self.evidence(paper,body.get('page'),body.get('source',''))
        fields={key:str(body.get(key,'')).strip() for key in ('attempt','revision','reflection')}
        if not fields['attempt'] or any(len(v)>10000 for v in fields.values()):raise ValueError('请填写自己的译文，每项不超过10000字符。')
        content=dict(source=evidence['quote'],page=evidence['page'],**fields)
        digest=hashlib.sha256(json.dumps([paper['id'],content],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        record=dict(content,id=digest,created=time.time())
        with self.db() as c:
            c.execute('INSERT OR IGNORE INTO learning_exercises VALUES(?,?,?,?)',(digest,paper['id'],json.dumps(record,ensure_ascii=False),record['created']))
            record=json.loads(c.execute('SELECT body FROM learning_exercises WHERE id=?',(digest,)).fetchone()['body'])
        return record
    def complete(self,pid):
        exercises=self.exercises(pid)
        with self.db() as c:
            row=c.execute('SELECT body FROM notes WHERE paper_id=?',(pid,)).fetchone();notes=json.loads(row['body']) if row else {}
            state=progress(notes,exercises)
            if not state['ready']:raise ValueError('请先补齐阅读问题、四项解释及原文依据、英译中练习和阅读笔记。')
            if not state['completed']:
                now=time.time();notes['studyCompletion']={'at':now,'signature':signature(notes)};raw=json.dumps(notes,ensure_ascii=False)
                c.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?)',(pid,raw,now));c.execute('INSERT INTO revisions(paper_id,body,created) VALUES(?,?,?)',(pid,raw,now))
        return dict(progress(notes,exercises),exercises=exercises)
    def next_papers(self,paper,terms):
        """Use existing metadata reserves only; no hidden network/model calls."""
        query=' '.join(terms[:3]);self.ensure()
        with self.db() as c:
            rows=c.execute('SELECT body FROM discovery_candidates ORDER BY first_seen DESC LIMIT 500').fetchall()
            imports={r['id']:r['paper_id'] for r in c.execute('SELECT * FROM discovery_imports')}
            learned=set()
            for row in c.execute('SELECT paper_id,body FROM notes'):
                n=json.loads(row['body'])
                if (n.get('studyCompletion') or {}).get('signature')==signature(n):learned.add(row['paper_id'])
            known_dois={discovery.doi(json.loads(r['metadata']).get('doi')) for r in c.execute('SELECT id,metadata FROM papers') if r['id'] in learned or r['id']==paper['id']}
        candidates=[];seen=set();today=discovery.today()
        for row in rows:
            r=discovery_venues.annotate(json.loads(row['body']));doi=discovery.doi(r.get('doi'))
            try:age=(today-date.fromisoformat(r.get('published',''))).days
            except ValueError:continue
            if not doi or doi in known_dois or doi in seen or imports.get(r['key'])==paper['id'] or imports.get(r['key']) in learned or not 0<=age<=365 or not r.get('venue') or r.get('publication_kind')!='正式出版候选':continue
            text=(r['title']+' '+r.get('abstract','')).lower()
            matches=[t for t in terms[:3] if re.search(r'\b'+re.escape(t)+r'\b',text)]
            if not matches:continue
            seen.add(doi);candidates.append(dict(r,reason='与当前论文的 '+ '、'.join(matches)+' 相关',local_paper_id=imports.get(r['key'])))
        candidates.sort(key=lambda r:(sum(t in (r['title']+' '+r.get('abstract','')).lower() for t in terms[:3]),r['published']),reverse=True)
        return {'query':query,'papers':candidates[:3],'basis':'当前论文的标题与摘要；已完成论文按DOI排除','cached':True}
