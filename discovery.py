"""Public scholarly metadata search, saved-topic refresh, and guarded OA import."""
import concurrent.futures, hashlib, html, ipaddress, json, re, socket, threading, time
import urllib.request, urllib.parse, urllib.error, unicodedata, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import discovery_venues as venues

def today(): return datetime.now(timezone(timedelta(hours=8))).date()
def clean(value): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',str(value or '')))).strip()
def doi(value): return re.sub(r'^https?://(?:dx\.)?doi\.org/','',str(value or ''),flags=re.I).strip().casefold()
def fingerprint(title): return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKC',title).casefold())
def safe_link(url):
    try:
        p=urllib.parse.urlsplit(str(url or ''))
        return url if p.scheme=='https' and p.hostname and not p.username and not p.password else ''
    except ValueError: return ''
def json_get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'PaperStudio/0.3 local scholarly reading tool','Accept':'application/json'})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=22) as r:
                raw=r.read(12*1024*1024+1)
                if len(raw)>12*1024*1024: raise ValueError('数据源响应过大')
                return json.loads(raw)
        except urllib.error.HTTPError as err:
            if err.code not in (429,503) or attempt:raise
            retry=err.headers.get('Retry-After','2')
            # Do not retry ahead of a long requested cooldown, or hammer the endpoint.
            if not retry.isdigit() or int(retry)>10:raise
            time.sleep(max(1,int(retry)))

TERMS={'车辆动力学':'vehicle dynamics','横纵向协同控制':'longitudinal lateral coordinated control','纵横向协调控制':'longitudinal lateral coordinated control','横向控制':'lateral control','纵向控制':'longitudinal control','路径跟踪':'path tracking','轨迹跟踪':'trajectory tracking','模型预测控制':'model predictive control','滑模控制':'sliding mode control','模糊控制':'fuzzy control','强化学习':'reinforcement learning','深度学习':'deep learning','自动驾驶':'autonomous driving','智能网联汽车':'connected automated vehicles','网联汽车':'connected vehicles','低附着':'low friction','电动汽车':'electric vehicle','动力电池':'power battery','热管理':'thermal management','轻量化':'lightweight design','结构优化':'structural optimization','车辆':'vehicle','汽车':'vehicle','制动':'braking','轮胎':'tire','悬架':'suspension','转向':'steering','稳定性':'stability','控制':'control','仿真':'simulation','路面':'road','算法':'algorithm'}
STOP=set('a an the of for and to in on with by from using based study research system systems method methods approach analysis novel new integrated driven algorithm algorithms'.split())
def prepare_topic(topic,title=''):
    topic=str(topic or title).strip()[:400]; text=topic; found=[]
    for word,english in sorted(TERMS.items(),key=lambda x:-len(x[0])):
        if word in text: found.append(english);text=text.replace(word,' ')
    unknown=''.join(re.findall(r'[\u4e00-\u9fff]+',text))
    unknown=re.sub(r'基于|关于|研究|相关|最新|前沿|以及|与|的|在|中|和|及','',unknown)
    words=re.findall(r'[a-zA-Z][a-zA-Z0-9-]*',text)
    english=' '.join(found+[' '.join(w for w in words if w.lower() not in STOP)])
    if title and not found:
        low=title.lower()
        if 'vehicle' in low and 'control' in low:
            english='vehicle '+('longitudinal ' if 'longitudinal' in low else '')+('lateral ' if 'lateral' in low else '')+'control'+(' fuzzy' if 'fuzzy' in low else '')
    tokens=list(dict.fromkeys(english.split()))[:18]
    return {'topic':topic,'query':' '.join(tokens),'unmapped':unknown,'notice':'术语词典生成，请确认并修改检索词；不是完整语义翻译。' if found or unknown else '已整理标题或英文关键词，请确认检索范围。'}

def reconstruct(index):
    if not isinstance(index,dict): return ''
    positions={}
    for word,items in index.items():
        for n in items:
            if isinstance(n,int) and 0<=n<12000: positions[n]=word
    return clean(' '.join(positions[n] for n in sorted(positions)))[:18000]

def openalex(query,start,end,selected=False):
    params={'search':query,'filter':f'from_publication_date:{start},to_publication_date:{end},is_retracted:false','per-page':50}
    if selected:params['filter']+=',primary_location.source.issn:'+'|'.join(x for v in venues.VENUES for x in v['issns'])+',language:en'
    data=json_get('https://api.openalex.org/works?'+urllib.parse.urlencode(params));items=[]
    for w in data.get('results',[]):
        if w.get('type') not in ('article','review','preprint','proceedings-article','conference-paper'): continue
        primary=w.get('primary_location') or {};source=primary.get('source') or {};locations=w.get('locations') or []
        formal=next((x for x in locations if (x.get('source') or {}).get('type') in ('journal','conference') and x.get('is_published')),None)
        kind='正式出版候选' if formal or (source.get('type') in ('journal','conference') and primary.get('is_published')) else '预印本或存储库版本' if w.get('type')=='preprint' or source.get('type')=='repository' else '出版状态待核实'
        loc=w.get('best_oa_location') or {};pdf=safe_link(loc.get('pdf_url')) if loc.get('is_oa') else ''
        publication=formal or primary;origin=publication.get('source') or {}
        items.append({'key':w.get('id',''),'doi':doi(w.get('doi')),'title':clean(w.get('display_name')),'published':w.get('publication_date') or '', 'date_label':'数据库发表日期','source':clean(origin.get('display_name')),'issns':origin.get('issn') or [],'publisher':clean(origin.get('host_organization_name')),'language':w.get('language',''),'authors':', '.join((x.get('author') or {}).get('display_name','') for x in w.get('authorships',[])[:6]),'abstract':reconstruct(w.get('abstract_inverted_index')),'landing_url':safe_link(publication.get('landing_page_url')) or safe_link(w.get('doi')) or safe_link(w.get('id')),'pdf_url':pdf,'pdf_source':clean((loc.get('source') or {}).get('display_name')) or urllib.parse.urlsplit(pdf).hostname or '', 'license':loc.get('license') or '', 'publication_kind':kind,'providers':['OpenAlex'],'citations':w.get('cited_by_count',0),'provider_rank':len(items),'review_status':'待核实'})
    return items, data.get('meta',{}).get('count',0)

def crossref(query,start,end,selected=False):
    params={'query.bibliographic':query,'filter':f'from-pub-date:{start},until-pub-date:{end}','rows':40}
    if selected:
        # Query each selected journal, rather than hoping a global first batch contains it.
        params['rows']=8
        def fetch(v):return json_get('https://api.crossref.org/journals/'+v['issns'][0]+'/works?'+urllib.parse.urlencode(params))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            payloads=list(pool.map(fetch,venues.VENUES))
        data={'message':{'items':[r for d in payloads for r in d.get('message',{}).get('items',[])],'total-results':sum(d.get('message',{}).get('total-results',0) for d in payloads)}}
    else:data=json_get('https://api.crossref.org/works?'+urllib.parse.urlencode(params))
    items=[]
    for w in data.get('message',{}).get('items',[]):
        kind=w.get('type');
        if kind not in ('journal-article','proceedings-article','posted-content','review'): continue
        dates=[]
        for field in ('published-online','published-print','published','issued'):
            parts=(w.get(field) or {}).get('date-parts',[])
            if parts and len(parts[0])>=3:
                try: dates.append(datetime(*parts[0][:3]).date().isoformat())
                except (ValueError,TypeError): pass
        published=min(dates) if dates else ''
        # Require a real day-level publication date; never substitute deposit/index dates.
        if not published or not start<=published<=end: continue
        items.append({'key':'crossref:'+doi(w.get('DOI')),'doi':doi(w.get('DOI')),'title':clean((w.get('title') or [''])[0]),'published':published,'date_label':'元数据发表日期','source':clean((w.get('container-title') or [w.get('publisher','')])[0]),'issns':w.get('ISSN') or [],'publisher':clean(w.get('publisher')),'language':w.get('language',''),'authors':', '.join(clean(x.get('given','')+' '+x.get('family','')) for x in w.get('author',[])[:6]),'abstract':clean(w.get('abstract'))[:18000],'landing_url':safe_link((w.get('resource') or {}).get('primary',{}).get('URL')) or safe_link(w.get('URL')),'pdf_url':'','license':'','publication_kind':'预印本或存储库版本' if kind=='posted-content' else '正式出版候选','providers':['Crossref'],'citations':w.get('is-referenced-by-count',0),'provider_rank':len(items),'review_status':'待核实'})
    return items,data.get('message',{}).get('total-results',0)

ARXIV_LOCK=threading.Lock(); ARXIV_LAST=0
def arxiv(query,start,end):
    global ARXIV_LAST
    terms=re.findall(r'[A-Za-z0-9-]+',query)[:8]
    expression=' AND '.join('all:'+w for w in terms)+f' AND submittedDate:[{start.replace("-","")}0000 TO {end.replace("-","")}2359]'
    url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':expression,'max_results':25,'sortBy':'submittedDate','sortOrder':'descending'})
    with ARXIV_LOCK:
        delay=3-(time.monotonic()-ARXIV_LAST)
        if delay>0:time.sleep(delay)
        ARXIV_LAST=time.monotonic()
        req=urllib.request.Request(url,headers={'User-Agent':'PaperStudio/0.3'})
        with urllib.request.urlopen(req,timeout=22) as r:root=ET.fromstring(r.read(3000000))
    ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'};items=[]
    for e in root.findall('a:entry',ns):
        identifier=e.findtext('a:id','',ns);published=e.findtext('a:published','',ns)[:10];pdf=''
        for link in e.findall('a:link',ns):
            if link.get('title')=='pdf':pdf=link.get('href','').replace('http://','https://')
        if not start<=published<=end:continue
        items.append({'key':re.sub(r'v\d+$','',identifier),'doi':doi(e.findtext('x:doi','',ns)),'title':clean(e.findtext('a:title','',ns)),'published':published,'date_label':'arXiv 首版提交日期','source':'arXiv','authors':', '.join(a.findtext('a:name','',ns) for a in e.findall('a:author',ns)[:6]),'abstract':clean(e.findtext('a:summary','',ns)),'landing_url':safe_link(identifier.replace('http://','https://')),'pdf_url':safe_link(pdf),'license':'','publication_kind':'预印本或存储库版本','providers':['arXiv'],'citations':0,'provider_rank':len(items),'review_status':'预印本，未经 arXiv 同行评审'})
    return items,len(items)

def merge_rank(rows,query,exclude_doi='',preprints=False):
    merged=[];by_doi={};by_title={}
    for r in rows:
        if not r['title'] or (exclude_doi and r['doi']==exclude_doi):continue
        match=by_doi.get(r['doi']) if r['doi'] else None
        if match is None:match=by_title.get(fingerprint(r['title']))
        if match is not None:
            old=merged[match];old['providers']=sorted(set(old['providers']+r['providers']))
            for f in ('abstract','pdf_url','pdf_source','license','authors','doi','publisher','issns','language'):
                if not old.get(f) and r.get(f):old[f]=r[f]
            if r['publication_kind']=='正式出版候选' and old['publication_kind']!='正式出版候选':
                for f in ('publication_kind','source','published','date_label','landing_url','publisher','issns','language'):
                    if f in r:old[f]=r[f]
            if old['doi']:by_doi[old['doi']]=match
            continue
        n=len(merged);merged.append(dict(r));by_title[fingerprint(r['title'])]=n
        if r['doi']:by_doi[r['doi']]=n
    terms=set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}',query) if w.lower() not in STOP)
    output=[]
    for r in merged:
        if not preprints and r['publication_kind']=='预印本或存储库版本':continue
        title=r['title'].lower();abstract=r['abstract'].lower();hits=[w for w in sorted(terms) if re.search(r'\b'+re.escape(w)+r'\w*\b',title+' '+abstract)]
        title_hits=sum(bool(re.search(r'\b'+re.escape(w)+r'\w*\b',title)) for w in terms)
        if terms and not hits:continue
        r['matched_terms']=hits;r['reason']='匹配关键词：'+', '.join(hits) if hits else '数据源返回的相关候选'
        r['rank_score']=round((title_hits*2+len(hits))/max(1,len(terms)),3)
        r['key']=('doi:'+r['doi']) if r['doi'] else 'title:'+hashlib.sha256(fingerprint(r['title']).encode()).hexdigest()[:28]
        r['fulltext_status']='公开 PDF 链接可用（下载待验证）' if r['pdf_url'] else '仅来源页面，公开 PDF 未知'
        output.append(venues.annotate(r))
    output.sort(key=lambda r:(r['rank_score'],r['published'],r['publication_kind']=='正式出版候选'),reverse=True)
    return output

def validate_public_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('全文地址必须是公开 HTTPS 链接。')
    try:addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    except socket.gaierror:raise ValueError('全文站点无法解析。') from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('不允许访问本机或内网全文地址。')
    return url
class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_public_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def download_pdf(url):
    validate_public_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'PaperStudio/0.3','Accept':'application/pdf'})
    try:
        with urllib.request.build_opener(PublicRedirect).open(req,timeout=25) as r:
            if int(r.headers.get('Content-Length','0'))>30*1024*1024:raise ValueError('公开 PDF 超过 30 MB。')
            raw=r.read(30*1024*1024+1)
        if len(raw)>30*1024*1024:raise ValueError('公开 PDF 超过 30 MB。')
        if not raw.startswith(b'%PDF-'):raise ValueError('该链接未返回 PDF，可能需要登录或已改变。请打开来源页面自行获取后上传。')
        return raw
    except (urllib.error.URLError,TimeoutError):raise ValueError('公开 PDF 下载失败或超时。请打开来源页面获取后上传；已有阅读记录保留。') from None

class Discovery:
    def __init__(self,db,importer):
        self.db=db;self.importer=importer;self.lock=threading.RLock();self.refreshing=False;self.jobs={};self.import_lock=threading.Lock()
    def ensure(self):
        with self.db() as c:c.executescript('''CREATE TABLE IF NOT EXISTS discovery_topics(id TEXT PRIMARY KEY,name TEXT,options TEXT,enabled INTEGER DEFAULT 1,last_checked REAL DEFAULT 0,last_error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS discovery_cache(id TEXT PRIMARY KEY,body TEXT,updated REAL);
        CREATE TABLE IF NOT EXISTS discovery_candidates(id TEXT PRIMARY KEY,body TEXT,first_seen REAL);
        CREATE TABLE IF NOT EXISTS discovery_bookmarks(id TEXT PRIMARY KEY,created REAL);
        CREATE TABLE IF NOT EXISTS discovery_imports(id TEXT PRIMARY KEY,paper_id TEXT);
        CREATE TABLE IF NOT EXISTS discovery_ai(id TEXT PRIMARY KEY,body TEXT);''')
    def options(self,data):
        query=clean(data.get('query'))[:300]
        if len(query)<3 or not re.search(r'[A-Za-z]{2}',query):raise ValueError('请先生成并确认英文检索词，或直接填写英文关键词。')
        days=int(data.get('days',365))
        if days not in (90,365,1095):raise ValueError('不支持的时间范围。')
        quality=data.get('quality','curated')
        if quality not in ('curated','broad'):raise ValueError('不支持的来源范围。')
        return {'query':query,'days':days,'preprints':bool(data.get('preprints',False)),'exclude_doi':doi(data.get('exclude_doi')),'quality':quality}
    def cache_key(self,options):return hashlib.sha256(json.dumps(dict(options,schema='3',venues=venues.VERSION),sort_keys=True).encode()).hexdigest()
    def candidate(self,key):
        self.ensure()
        with self.db() as c:row=c.execute('SELECT body,first_seen FROM discovery_candidates WHERE id=?',(key,)).fetchone()
        if not row:raise ValueError('候选记录不存在，请重新搜索。')
        return dict(json.loads(row['body']),first_seen=row['first_seen'])
    def search(self,data):
        self.ensure();options=self.options(data);key=self.cache_key(options)
        with self.lock:
            with self.db() as c:cached=c.execute('SELECT * FROM discovery_cache WHERE id=?',(key,)).fetchone()
            if cached and not data.get('force') and time.time()-cached['updated']<21600:return dict(json.loads(cached['body']),cached=True)
            end=today().isoformat();start=(today()-timedelta(days=options['days'])).isoformat();rows=[];errors=[];coverage=[];success=0
            providers={'OpenAlex':openalex,'Crossref':crossref}
            if options['preprints']:providers['arXiv']=arxiv
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures={pool.submit(fn,options['query'],start,end,*([options['quality']=='curated'] if name!='arXiv' else [])):name for name,fn in providers.items()}
                for future in concurrent.futures.as_completed(futures):
                    name=futures[future]
                    try:
                        found,total=future.result();success+=1;rows.extend(found);coverage.append({'source':name,'returned':len(found),'reported_hits':total})
                    except Exception as e:
                        status=getattr(e,'code',None);errors.append(name+(' 请求受限（HTTP 429），请稍后刷新' if status==429 else ' HTTP '+str(status) if status else ' 暂时无法连接')+'；结果可能不完整。')
            if not success:raise ValueError('论文数据源均未成功响应，请稍后刷新。'+ ' '.join(errors))
            dated=[]
            for r in rows:
                try: valid=datetime.fromisoformat(r.get('published','')).date().isoformat()
                except (ValueError,TypeError): continue
                if start<=valid<=end:dated.append(r)
            ranked=merge_rank(dated,options['query'],options['exclude_doi'],options['preprints'])
            preprint_rows=[r for r in ranked if r['publication_kind']=='预印本或存储库版本']
            ranked=[r for r in ranked if r['publication_kind']!='预印本或存储库版本']
            if options['quality']=='curated':ranked=[r for r in ranked if r['venue'] and r['publication_kind']=='正式出版候选' and r.get('language','en') in ('','en',None)]
            now=time.time();old_ids={r['key'] for r in json.loads(cached['body'])['results']} if cached else set()
            with self.db() as c:
                for r in ranked+preprint_rows:
                    prior=c.execute('SELECT first_seen FROM discovery_candidates WHERE id=?',(r['key'],)).fetchone();r['first_seen']=prior['first_seen'] if prior else now
                    c.execute('INSERT INTO discovery_candidates VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(r['key'],json.dumps(r,ensure_ascii=False),r['first_seen']))
            result={'options':options,'start_date':start,'end_date':end,'results':ranked,'preprint_results':preprint_rows,'coverage':coverage,'warnings':errors,'fetched_at':now,'cached':False,'first_search':not bool(cached),'new_ids':[r['key'] for r in ranked if cached and r['key'] not in old_ids],'scope':('限定6种已核对范围与标识的期刊；不足不混入其他来源。' if options['quality']=='curated' else '扩大范围，未入选来源单独标记。')+'本次接口候选集非全网全集；来源入选不等于逐篇质量认证。','venue_version':venues.VERSION}
            with self.db() as c:c.execute('INSERT OR REPLACE INTO discovery_cache VALUES(?,?,?)',(key,json.dumps(result,ensure_ascii=False),now))
            return result
    def state(self):
        self.ensure()
        with self.db() as c:
            topics=[dict(r) for r in c.execute('SELECT * FROM discovery_topics ORDER BY rowid DESC')]
            bookmarks=[dict(json.loads(r['body']),bookmarked_at=r['created']) for r in c.execute('SELECT c.body,b.created FROM discovery_bookmarks b JOIN discovery_candidates c ON c.id=b.id ORDER BY b.created DESC')]
        for t in topics:t['options']=self.options(json.loads(t['options']));t['running']=bool(self.jobs.get(t['id']))
        return {'topics':topics,'bookmarks':[venues.annotate(r) for r in bookmarks],'refreshing':self.refreshing,'catalog':venues.catalog()}
    def save_topic(self,data):
        self.ensure();options=self.options(data);key=self.cache_key(options);name=clean(data.get('name') or options['query'])[:150]
        with self.db() as c:
            if c.execute('SELECT count(*) FROM discovery_topics').fetchone()[0]>=20 and not c.execute('SELECT 1 FROM discovery_topics WHERE id=?',(key,)).fetchone():raise ValueError('首版最多保存 20 个主题，可先暂停不需要的主题。')
            c.execute('INSERT INTO discovery_topics(id,name,options) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,enabled=1',(key,name,json.dumps(options)))
        return self.state()
    def topic_result(self,key):
        self.ensure()
        with self.db() as c:
            topic=c.execute('SELECT options FROM discovery_topics WHERE id=?',(key,)).fetchone()
            if topic:key=self.cache_key(self.options(json.loads(topic['options'])))
            row=c.execute('SELECT body FROM discovery_cache WHERE id=?',(key,)).fetchone()
        return json.loads(row['body']) if row else None
    def toggle_topic(self,key,enabled):
        self.ensure()
        with self.db() as c:c.execute('UPDATE discovery_topics SET enabled=? WHERE id=?',(int(bool(enabled)),key))
        return self.state()
    def refresh(self,force=False):
        self.ensure()
        with self.lock:
            if self.refreshing:return {'started':False}
            topics=[t for t in self.state()['topics'] if t['enabled'] and (force or time.time()-t['last_checked']>21600 or self.topic_result(t['id']) is None)]
            if not topics:return {'started':False}
            self.refreshing=True
        def work():
            try:
                for t in topics:
                    self.jobs[t['id']]=True
                    try:
                        self.search(dict(t['options'],force=bool(force)))
                        with self.db() as c:c.execute("UPDATE discovery_topics SET last_checked=?,last_error='' WHERE id=?",(time.time(),t['id']))
                    except Exception as e:
                        with self.db() as c:c.execute('UPDATE discovery_topics SET last_error=?,last_checked=? WHERE id=?',(str(e)[:500],time.time(),t['id']))
                    finally:self.jobs.pop(t['id'],None)
            finally:self.refreshing=False
        threading.Thread(target=work,daemon=True).start();return {'started':True,'count':len(topics)}
    def bookmark(self,key,enabled):
        self.candidate(key)
        with self.db() as c:
            if enabled:c.execute('INSERT OR IGNORE INTO discovery_bookmarks VALUES(?,?)',(key,time.time()))
            else:c.execute('DELETE FROM discovery_bookmarks WHERE id=?',(key,))
        return self.state()
    def import_candidate(self,key):
        self.ensure()
        with self.import_lock:
            r=self.candidate(key)
            with self.db() as c:
                found=c.execute('SELECT paper_id FROM discovery_imports WHERE id=?',(key,)).fetchone()
                if found and c.execute('SELECT 1 FROM papers WHERE id=?',(found['paper_id'],)).fetchone():return {'paper_id':found['paper_id'],'existing':True}
                for p in c.execute('SELECT id,metadata FROM papers'):
                    if r['doi'] and doi(json.loads(p['metadata']).get('doi'))==r['doi']:return {'paper_id':p['id'],'existing':True}
            if not r['pdf_url']:raise ValueError('没有可用的公开 PDF 链接，请从来源页面获取后上传。')
            raw=download_pdf(r['pdf_url']);paper=self.importer(raw,(fingerprint(r['title'])[:80] or 'paper')+'.pdf')
            metadata=paper['metadata'];metadata.update(doi=r['doi'],published=r['published'],source=r.get('official_url') or r['landing_url'],venue_name=r['source'],abstract=r['abstract'],publisher=r.get('publisher',''),review_status='预印本' if r['publication_kind']=='预印本或存储库版本' else '待核实',discovery_providers=r['providers'])
            with self.db() as c:
                c.execute('UPDATE papers SET title=?,metadata=? WHERE id=?',(r['title'],json.dumps(metadata,ensure_ascii=False),paper['id']))
                c.execute('INSERT OR REPLACE INTO discovery_imports VALUES(?,?)',(key,paper['id']))
            return {'paper_id':paper['id'],'existing':False}
