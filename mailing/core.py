"""Validated paper excerpts, personalized selection and script-free email rendering."""
import hashlib,html,re
from datetime import datetime,timedelta,timezone,date
from urllib.parse import urlsplit
import discovery_venues

SHANGHAI=timezone(timedelta(hours=8))
LICENSES={'https://creativecommons.org/licenses/by/4.0/':'CC BY 4.0','https://creativecommons.org/publicdomain/zero/1.0/':'CC0 1.0'}
def day(now=None):return (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI).date()
def https_url(value):
    p=urlsplit(str(value))
    if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('链接必须是无凭据的HTTPS地址')
    return str(value)
def email_address(value):
    value=str(value).strip()
    if len(value)>254 or not re.fullmatch(r'[^\s<>@,;\r\n]+@[^\s<>@,;\r\n]+\.[^\s<>@,;\r\n]+',value):raise ValueError('邮箱地址格式无效')
    return value
def validate_paper(p,today=None):
    required=('doi','title','title_zh','published','source','authors','source_url','section','source_text','excerpt','excerpt_zh','license_url','license_evidence_url','terms','question')
    if any(not p.get(k) for k in required):raise ValueError('论文节选缺少原文、出处、译文或许可依据')
    if not re.fullmatch(r'10\.\d{4,9}/\S+',p['doi']):raise ValueError('DOI格式无效')
    published=date.fromisoformat(p['published']);today=today or day()
    if not 0<=(today-published).days<=365:raise ValueError('仅选近一年已发表论文')
    if not discovery_venues.match_venue(p):raise ValueError('尚未匹配精选期刊来源')
    if p.get('publication_kind')!='正式出版候选':raise ValueError('预印本不进入正式晨读')
    if p['license_url'] not in LICENSES or p.get('rights_verified') is not True:raise ValueError('具体原文版本的摘录与翻译分发许可尚未核对')
    for key in ('source_url','license_evidence_url'):https_url(p[key])
    normalize=lambda text:re.sub(r'\s+',' ',text).strip()
    if normalize(p['excerpt']) not in normalize(p['source_text']):raise ValueError('节选未通过原文逐字匹配')
    words=re.findall(r"[A-Za-z]+(?:[-’'][A-Za-z]+)*",p['excerpt'])
    if not 100<=len(words)<=150:raise ValueError('节选应为100—150个英文单词')
    if not re.search(r'[\u4e00-\u9fff]',p['title_zh']+p['excerpt_zh']):raise ValueError('缺少中文辅助内容')
    if len(p['terms'])!=3 or any(not isinstance(x,dict) or not x.get('en') or not x.get('zh') for x in p['terms']):raise ValueError('应提供3个中英术语')
    return p
def choose_paper(pool,topics,sent_dois,today=None):
    terms=set(re.findall(r'[a-z]{3,}',' '.join(topics).lower()));eligible=[]
    for p in pool:
        try:validate_paper(p,today)
        except (ValueError,TypeError,KeyError):continue
        if p['doi'].lower() in {x.lower() for x in sent_dois}:continue
        text=(p['title']+' '+p.get('abstract','')+' '+p['excerpt']).lower()
        matches=[t for t in sorted(terms) if re.search(r'\b'+re.escape(t)+r'\w*\b',text)]
        if terms and not matches:continue
        eligible.append((len(matches)/max(1,len(terms)),p['published'],p,matches))
    if not eligible:return None
    score,_,p,matches=max(eligible,key=lambda x:(x[0],x[1],x[2]['doi']))
    return dict(p,matched_terms=matches)
def render(p,reader_name,unsubscribe_url,preview=False):
    https_url(unsubscribe_url)
    if not preview:validate_paper(p)
    e=lambda value:html.escape(str(value),quote=True)
    source=https_url(p['source_url']);license_url=https_url(p['license_url'])
    title=('【排版测试】' if preview else '【研读晨读】')+p['title_zh']
    notice='<p style="font-size:12px;color:#7a8e98">排版示例 · 非真实论文</p>' if preview else ''
    doi='' if preview else '<br>DOI：'+e(p['doi'])
    rights='原创排版示例' if preview else '原文许可：<a href="'+e(license_url)+'">'+e(LICENSES[p['license_url']])+'</a> · 节选含中文翻译'
    term_html=''.join('<tr><td style="padding:8px;border-bottom:1px solid #e1e8ea">'+e(x['en'])+'</td><td style="padding:8px;border-bottom:1px solid #e1e8ea">'+e(x['zh'])+'</td></tr>' for x in p['terms'])
    body=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f7f8;color:#304d59;font-family:Arial,'Microsoft YaHei',sans-serif"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 12px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:white;border:1px solid #dce6eb;border-radius:10px"><tr><td style="padding:28px">
<p style="font-size:12px;letter-spacing:2px;color:#28777b">研读晨读</p>{notice}
<h1 style="font-size:23px;line-height:1.6">{e(p['title_zh'])}</h1><p style="font-size:15px;line-height:1.7">{e(p['title'])}</p><p style="font-size:12px;line-height:1.8;color:#70858f">{e(p['authors'])}<br>{e(p['source'])} · {e(p['published'])}{doi}</p>
<h2 style="font-size:16px;margin-top:30px">英文节选</h2><p style="font-size:12px;color:#70858f">原文位置：{e(p['section'])}</p><blockquote style="margin:12px 0;padding:16px 18px;border-left:3px solid #2c7c80;background:#f1f7f7;font:16px/1.9 Georgia,serif">{e(p['excerpt'])}</blockquote>
<h2 style="font-size:16px;margin-top:28px">中文译文{'（示例）' if preview else '（机器翻译）'}</h2><p style="font-size:15px;line-height:1.95">{e(p['excerpt_zh'])}</p>
<h2 style="font-size:16px;margin-top:28px">术语</h2><table width="100%" style="font-size:14px;border-collapse:collapse">{term_html}</table>
<h2 style="font-size:16px;margin-top:28px">想一想</h2><p style="font-size:15px;line-height:1.9">{e(p['question'])}</p><p style="margin-top:25px"><a style="color:#237980" href="{e(source)}">查看原文与发表出处 ↗</a></p>
<p style="font-size:11px;line-height:1.8;color:#7e929c">{rights}</p><hr style="border:0;border-top:1px solid #e0e8eb"><p style="font-size:11px;line-height:1.9"><a style="color:#4a7c85" href="{e(unsubscribe_url)}">退订晨读</a></p></td></tr></table></td></tr></table></body></html>'''
    preview_label='排版示例 · 非真实论文\n\n' if preview else ''
    doi_text='' if preview else ' | DOI '+p['doi']
    rights_text='原创排版示例' if preview else '许可：'+license_url
    plain=f"研读晨读\n\n{preview_label}{p['title_zh']}\n{p['title']}\n{p['authors']}\n{p['source']} | {p['published']}{doi_text}\n\n英文节选（{p['section']}）：\n{p['excerpt']}\n\n中文译文（{'示例' if preview else '机器翻译'}）：\n{p['excerpt_zh']}\n\n术语：\n"+'\n'.join(x['en']+'：'+x['zh'] for x in p['terms'])+f"\n\n想一想：{p['question']}\n原文：{source}\n{rights_text}\n退订：{unsubscribe_url}\n"
    return {'subject':title[:200],'html':body,'text':plain}
def delivery_key(email,send_day):return hashlib.sha256((email_address(email).lower()+'|'+str(send_day)).encode()).hexdigest()

def dispatch(store,sender,subscriber,paper,unsubscribe_url,now=None):
    now=now or datetime.now(SHANGHAI);local=now.astimezone(SHANGHAI)
    if local.hour<8 or local.hour>=10:return {'status':'outside-window'}
    address=email_address(subscriber['email'])
    if subscriber.get('confirmed') is not True or not subscriber.get('enabled',False):return {'status':'not-subscribed'}
    u=urlsplit(https_url(unsubscribe_url))
    if u.hostname in ('example.org','example.com','localhost') or u.hostname.endswith('.invalid'):raise ValueError('正式发送需要已部署的真实HTTPS退订入口')
    validate_paper(paper,local.date())
    if paper['doi'].lower() in {x.lower() for x in store.sent_dois(address)}:return {'status':'already-read'}
    payload=render(paper,subscriber.get('name') or '同学',unsubscribe_url)
    key=delivery_key(address,local.date())
    if not store.claim(key,{'day':local.date().isoformat(),'doi':paper['doi'],'recipient':address}):return {'status':'already-claimed'}
    # Once submitted, timeout can mean accepted: never automatically submit this claim again.
    try:
        result=sender.send(address,payload)
        store.finish(key,'accepted',result)
        return {'status':'accepted','provider':result}
    except Exception:
        store.finish(key,'unknown',{})
        return {'status':'unknown','message':'结果未确认，先查邮件服务日志；不自动重发。'}
