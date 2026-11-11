"""Evidence-bound learning feedback. Source matching is not a reasoning verifier."""
import hashlib
import json
import re
import unicodedata

FIELDS = {'answerProblem':'研究问题','answerMethod':'方法与假设','answerEvidence':'关键证据','answerLimit':'局限与待解问题'}
STATUS = {'supported':'有依据','contradicted':'与原文不符','insufficient':'材料不足'}
CONTEXT_LIMIT = 32000


def text_key(text):
    value = ''.join(unicodedata.normalize('NFKC', c).casefold() for c in text)
    value = re.sub(r'\s+|\u00ad', '', value)
    return re.sub(r'(?<=[a-z])[-‐‑](?=[a-z])', '', value)


def document_key(paper):
    return hashlib.sha256(json.dumps([(p['page'],p['text']) for p in paper['pages']],ensure_ascii=False).encode()).hexdigest()


def occurrences(text, quote):
    return [m.start() for m in re.finditer('(?='+re.escape(quote)+')', text)] if quote else []


def anchor(paper, page, quote, hint=None, context=None):
    text = next((p['text'] for p in paper['pages'] if p['page']==page), '')
    key, q = text_key(text), text_key(quote)
    positions = occurrences(key,q)
    hint = hint if isinstance(hint,dict) else {}
    if hint.get('document') and hint['document'] != document_key(paper):
        raise ValueError('证据所属文档已变化，请重新选择原文。')
    prefix, suffix = str(hint.get('prefix',''))[-80:],str(hint.get('suffix',''))[:80]
    if len(positions)>1 and (prefix or suffix):
        positions = [i for i in positions if (not prefix or key[:i].endswith(prefix)) and (not suffix or key[i+len(q):].startswith(suffix))]
    if len(positions)>1 and context:
        ck = text_key(context)
        starts = occurrences(key,ck)
        local = occurrences(ck,q)
        if len(starts)==len(local)==1:
            positions = [starts[0]+local[0]]
    unique = len(positions)==1
    i = positions[0] if unique else None
    return {'version':1,'document':document_key(paper),'page':page,'offset':i,
            'prefix':key[max(0,i-80):i] if unique else '',
            'suffix':key[i+len(q):i+len(q)+80] if unique else '', 'ambiguous':not unique}


def snapshot(notes):
    return {**{f:str(notes.get(f,'')) for f in FIELDS},'studyEvidence':notes.get('studyEvidence') or {}}


def prepare(paper, notes, resolver, extra_chunks):
    snap = snapshot(notes)
    if not any(snap[f].strip() for f in FIELDS):
        raise ValueError('请先填写自己的解释，再请求反馈。')
    if any(len(snap[f])>10000 for f in FIELDS) or sum(len(snap[f]) for f in FIELDS)>16000:
        raise ValueError('四项作答超过本次上下文容量，请缩短后重试；尚未调用模型。')
    chunks, bindings = [], {f:[] for f in FIELDS}
    evidence = snap['studyEvidence']
    if not isinstance(evidence,dict) or any(k not in FIELDS for k in evidence):
        raise ValueError('原文依据格式无效，请重新选择。')
    for field,items in evidence.items():
        if not isinstance(items,list) or len(items)>6:
            raise ValueError('每项最多保留6段原文依据。')
        for n,item in enumerate(items):
            if not isinstance(item,dict) or not isinstance(item.get('quote'),str):
                raise ValueError('原文依据格式无效。')
            try: page=int(item['page'])
            except (KeyError,TypeError,ValueError): raise ValueError('原文依据页码无效。') from None
            found=resolver(paper,page,item['quote'])
            if found['page']!=page: raise ValueError('原文依据页码已失效，请重新选择。')
            if isinstance(item.get('anchor'),dict): anchor(paper,page,found['selected'],item['anchor'])
            cid=f'e-{field}-{n+1}'
            chunks.append(dict(found,id=cid,field=field))
            bindings[field].append({'id':cid,'page':page,'quote':found['selected']})
    used=sum(len(c['text']) for c in chunks)
    if used>CONTEXT_LIMIT: raise ValueError('绑定的原文依据超过本次上下文容量，请减少或缩短依据后重试；尚未调用模型。')
    for ch in extra_chunks:
        if used+len(ch['text'])>CONTEXT_LIMIT: continue
        chunks.append(ch);used+=len(ch['text'])
    return snap,chunks,bindings


def validate_feedback(obj, citations, snap):
    rows=obj.get('feedback')
    if not isinstance(rows,list) or len(rows)>4: raise ValueError('模型未返回四项结构化反馈，本次结果未保存。')
    by_ref={c['ref']:c for c in citations}
    seen=set(); result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('field') not in FIELDS or row['field'] in seen:
            raise ValueError('模型反馈项目格式无效，本次结果未保存。')
        field=row['field'];seen.add(field)
        claims=row.get('claims')
        if not isinstance(claims,list) or len(claims)>8: raise ValueError('模型判断格式无效，本次结果未保存。')
        checked=[]
        for claim in claims:
            if not isinstance(claim,dict) or not isinstance(claim.get('text'),str) or claim.get('status') not in STATUS:
                raise ValueError('模型判断格式无效，本次结果未保存。')
            refs=claim.get('evidence_ids',[])
            if not isinstance(refs,list) or any(not isinstance(r,str) for r in refs): raise ValueError('模型引用标识格式无效。')
            valid=list(dict.fromkeys(r for r in refs if r in by_ref))
            unsupported=not valid or any(r not in by_ref for r in refs)
            status='insufficient' if unsupported or not snap[field].strip() else claim['status']
            checked.append({'text':claim['text'][:1600],'status':status,'evidence_ids':valid,
                            'citation_issue':bool(unsupported and claim['status']!='insufficient')})
        if not checked: checked=[{'text':'本次未返回可核对的判断。','status':'insufficient','evidence_ids':[]}]
        statuses={c['status'] for c in checked}
        status='insufficient' if 'insufficient' in statuses else 'contradicted' if 'contradicted' in statuses else 'supported'
        result.append({'field':field,'label':FIELDS[field],'status':status,'claims':checked,
                       'hint':str(row.get('hint',''))[:1600],'analysis':str(row.get('analysis',''))[:4000]})
    for field in FIELDS:
        if field not in seen: result.append({'field':field,'label':FIELDS[field],'status':'insufficient',
            'claims':[{'text':'本次未返回该项反馈。','status':'insufficient','evidence_ids':[]}], 'hint':'补充作答及相关原文后再核对。','analysis':''})
    result.sort(key=lambda r:list(FIELDS).index(r['field']))
    return result


def feedback_text(rows):
    return '\n\n'.join(r['label']+' · '+STATUS[r['status']]+'\n'+ '\n'.join(
        STATUS[c['status']]+'：'+c['text']+(' ['+', '.join(c['evidence_ids'])+']' if c['evidence_ids'] else '') for c in r['claims'])+
        ('\n修改提示：'+r['hint'] if r['hint'] else '')+ ('\n补充分析（待核对）：'+r['analysis'] if r['analysis'] else '') for r in rows)
