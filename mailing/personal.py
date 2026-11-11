"""Per-user drafts and bounded preparation, with unread, verified reserve fallback."""
import hashlib,secrets
from datetime import datetime,timedelta
from .core import SHANGHAI,day,choose_paper,dispatch
from .preferences import preferences,content_key,due,upcoming,validate_profile

class GenerationQuotaExceeded(ValueError):pass

class BudgetTranslator:
    def __init__(self,translator,store,sid,date,purpose='delivery'):
        if purpose not in ('delivery','verification'):raise ValueError('生成用途无效')
        self.translator=translator;self.store=store;self.sid=sid;self.date=date;self.purpose=purpose
    def __call__(self,paper):
        def reserve(prefix,limit):
            return any(self.store.create(prefix+str(i)+'.json',{'reserved':True}) for i in range(limit))
        # Count failed calls too. A lost write never grants another model call.
        prefix='personal/'+self.purpose+'-model-budget/'+self.date+'/'
        personal,global_limit=(4,8) if self.purpose=='delivery' else (2,4)
        if not reserve(prefix+self.sid+'/',personal):raise GenerationQuotaExceeded('今日个人生成额度已用完')
        if not reserve(prefix+'global/',global_limit):raise GenerationQuotaExceeded('今日生成额度已用完')
        return self.translator(paper)

class PersonalMorning:
    def __init__(self,service):self.service=service;self.store=service.store
    def draft_key(self,user,slot):return 'personal/drafts/'+user['sid']+'/'+slot.date().isoformat()+'/'+content_key(user)+'.json'
    def reserve_prefix(self,user):
        p=preferences(user);return 'personal/reserve/'+p['difficulty']+'-'+p['length']+'/'
    def candidates(self,user,now):
        result=[]
        for key in list(self.store.keys(self.reserve_prefix(user)))[:100]:
            paper=self.store.read(key)
            try:validate_profile(paper,user,day(now))
            except (ValueError,TypeError,KeyError):continue
            result.append(paper)
        return result
    def chosen(self,papers,user,now):
        return choose_paper(papers,user['topics'],self.store.sent_dois(user['email']),day(now))
    def prepare_user(self,user,slot,now,verification=False):
        key=self.draft_key(user,slot)
        old=self.store.read(key)
        if old and not verification:
            try:
                validate_profile(old['paper'],user,day(now))
                if self.chosen([old['paper']],user,now):return {'status':'ready','paper':old['paper']}
            except (ValueError,TypeError,KeyError):pass
        # No permanent empty-pool lock: allow two bounded attempts for a given profile/day.
        # v1 attempts could be spent by a shared verification quota. Preserve that
        # audit trail, but account new attempts by actual execution/budget date.
        attempt_prefix='personal/prepare-v2/'+user['sid']+'/'+slot.date().isoformat()+'/'+content_key(user)+'/'+day(now).isoformat()+'/'
        attempt=secrets.token_hex(12) if verification else next((str(i) for i in range(2) if self.store.create(attempt_prefix+str(i)+'.json',{'started_at':now.isoformat()})),None)
        fresh=[];report={}
        if attempt is not None:
            preparer=self.service.preparer.for_preferences(user)
            preparer.translator=BudgetTranslator(preparer.translator,self.store,user['sid'],day(now).isoformat(),'verification' if verification else 'delivery')
            try:
                fresh=preparer(user['topics'],day(now),exclude_dois=self.store.sent_dois(user['email']))
                report=getattr(preparer,'last_report',{})
            except Exception as error:
                fresh=[];report={'preparation_error':type(error).__name__}
            for paper in fresh:
                validate_profile(paper,user,day(now))
                self.store.create(self.reserve_prefix(user)+hashlib.sha256(paper['doi'].lower().encode()).hexdigest()+'.json',paper)
        paper=self.chosen(fresh,user,now) or self.chosen(self.candidates(user,now),user,now)
        if not verification and attempt is not None:
            self.store.create('personal/prepare-outcomes-v2/'+user['sid']+'/'+slot.date().isoformat()+'/'+content_key(user)+'/'+day(now).isoformat()+'/'+attempt+'.json',
                {'status':'ready' if paper else 'no-paper','finished_at':datetime.now(SHANGHAI).isoformat(),'checks':report,'doi':paper['doi'] if paper else None})
        if not paper:return {'status':'no-paper','checks':report}
        if not verification:self.store.create(key,{'paper':paper,'prepared_at':now.isoformat(),'content_key':content_key(user)})
        return {'status':'verified' if verification else 'ready','paper':paper,'checks':report}
    def check(self,now=None):
        now=now or datetime.now(SHANGHAI);self.store.safe();results=[]
        for user in self.service.subscriptions.subscribers.values():
            slot=upcoming(user,now)
            if not slot or not self.service.subscriptions.active(user):continue
            result=self.prepare_user(user,slot,now,verification=True)
            p=result.get('paper',{})
            import re
            results.append({'sid':user['sid'],'status':result['status'],'doi':p.get('doi'),'checks':result.get('checks',{}),
                'profile':p.get('learning_profile'),'excerpt_words':len(re.findall(r"[A-Za-z]+(?:[-’'][A-Za-z]+)*",p.get('excerpt',''))),'guide_present':bool(p.get('reading_guide'))})
        return {'status':'verified' if results and all(r['status']=='verified' for r in results) else 'no-paper','results':results,'email_sent':False}
    def tick(self,now=None):
        fixed=now is not None;now=now or datetime.now(SHANGHAI)
        if not self.service.send_enabled or not self.service.prepare_enabled:return {'status':'paused'}
        self.store.safe();results=[]
        for user in self.service.subscriptions.subscribers.values():
            current=now if fixed else datetime.now(SHANGHAI)
            try:slot=upcoming(user,current)
            except (ValueError,TypeError):results.append({'sid':user['sid'],'status':'invalid-preferences'});continue
            if not slot or slot-current>timedelta(minutes=30) or not self.service.subscriptions.active(user):continue
            # A completed/unknown daily claim is final, even after a preference change.
            claim='claims/'+self.store.email_key(user['email'])+'/'+slot.date().isoformat()+'.json'
            if self.store.read(claim):continue
            try:result=self.prepare_user(user,slot,current)
            except Exception:results.append({'sid':user['sid'],'status':'preparation-failed'});continue
            current=now if fixed else datetime.now(SHANGHAI)
            if not due(user,current) or result['status']!='ready':
                results.append({'sid':user['sid'],'status':result['status']});continue
            if not self.service.subscriptions.active(user):continue
            paper=result['paper'];validate_profile(paper,user,day(current))
            delivered=dispatch(self.store,self.service.sender,dict(user,confirmed=True,enabled=True),paper,
                self.service.subscriptions.link(user,'unsubscribe'),current,scheduled_for=slot)
            results.append({'sid':user['sid'],'status':delivered['status']})
        return {'status':'complete','results':results}
