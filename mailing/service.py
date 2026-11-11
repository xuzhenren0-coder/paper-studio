"""Small-pilot jobs: prepare at 07:30 and deliver at 08:00, with durable duplicate suppression."""
from datetime import datetime
import secrets
from .core import SHANGHAI,day,choose_paper,dispatch,validate_paper

class MorningService:
    def __init__(self,store,sender,subscriptions,preparer,send_enabled=False,prepare_enabled=False):
        self.store=store;self.sender=sender;self.subscriptions=subscriptions;self.preparer=preparer
        self.send_enabled=send_enabled;self.prepare_enabled=prepare_enabled
    def prepare(self,now=None,verification=False):
        now=now or datetime.now(SHANGHAI);date=day(now).isoformat()
        if not self.prepare_enabled and not verification:return {'status':'paused'}
        self.store.safe()
        check=secrets.token_hex(16) if verification else None
        job_key='checks/prepare/'+check+'.json' if check else 'jobs/prepare/'+date+'.json'
        if not self.store.create(job_key,{'started_at':now.isoformat()}):return {'status':'already-prepared'}
        blocked=self.sender.blocked_recipients() if getattr(self.subscriptions,'managed_unsubscribe',False) else set()
        users=[u for u in self.subscriptions.subscribers.values() if self.subscriptions.active(u) and u['email'] not in blocked]
        if not users:return {'status':'no-subscribers'}
        topics=list(dict.fromkeys(t for u in users for t in u['topics']))[:8]
        histories=[{str(doi).lower() for doi in self.store.sent_dois(u['email'])} for u in users]
        # Keep a paper eligible while any active subscriber has not received it.
        common_read=set.intersection(*histories) if histories else set()
        pool=self.preparer(topics,day(now),exclude_dois=sorted(common_read))
        for paper in pool:validate_paper(paper,day(now))
        pool_key='checks/pools/'+check+'.json' if check else 'pools/'+date+'.json'
        report=getattr(self.preparer,'last_report',{})
        report=report if isinstance(report,dict) else {}
        self.store.create(pool_key,{'date':date,'papers':pool,'checks':report})
        return {'status':'verified' if check else 'prepared','papers':len(pool),'checks':report,**({'verification_pool':pool_key} if check else {})}
    def send(self,now=None):
        now=now or datetime.now(SHANGHAI)
        if not self.send_enabled:return {'status':'paused'}
        if not 8<=now.astimezone(SHANGHAI).hour<10:return {'status':'outside-window'}
        self.store.safe()
        pool=self.store.read('pools/'+day(now).isoformat()+'.json')
        if not pool:return {'status':'no-paper'}
        managed=getattr(self.subscriptions,'managed_unsubscribe',False)
        blocked=self.sender.blocked_recipients() if managed else set()
        results=[]
        for user in self.subscriptions.subscribers.values():
            if not self.subscriptions.active(user) or user['email'] in blocked:continue
            paper=choose_paper(pool['papers'],user['topics'],self.store.sent_dois(user['email']),day(now))
            if not paper:results.append({'sid':user['sid'],'status':'no-paper'});continue
            if not self.subscriptions.active(user):continue
            result=dispatch(self.store,self.sender,dict(user,confirmed=True,enabled=True),paper,
                self.subscriptions.link(user,'unsubscribe'),now,provider_unsubscribe=managed,
                owner_control=getattr(self.subscriptions,'owner_only',False) is True)
            results.append({'sid':user['sid'],'status':result['status']})
        return {'status':'complete','results':results}
