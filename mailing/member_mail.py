"""At-most-once invitation/login relay. Never retries ambiguous SMTP submissions."""
from html import escape
from urllib.parse import urlparse,parse_qs
from .core import email_address

def account_message(job,origin):
    purpose=job.get('purpose');url=job.get('url','');u=urlparse(url)
    if purpose not in ('invite','login') or u.scheme!='https' or u.netloc!=urlparse(origin).netloc or u.path!='/' or u.query:
        raise ValueError('邀请链接无效')
    token=parse_qs(u.fragment).get(purpose,[''])[0]
    import re
    if not re.fullmatch('[a-f0-9]{64}',token):raise ValueError('邀请令牌无效')
    address=email_address(job['email']).lower();label='确认订阅' if purpose=='invite' else '登录晨读'
    detail='邀请有效期48小时，确认后每天北京时间08:00接收晨读。' if purpose=='invite' else '登录链接15分钟内有效，只能使用一次。'
    text=f'{label}\n\n{detail}\n{url}\n\n如果不是你本人申请，请忽略本邮件。'
    html=f'<html lang="zh-CN"><body style="font:16px/1.8 sans-serif;color:#173b40;padding:24px"><h2>研读 · {label}</h2><p>{escape(detail)}</p><p><a href="{escape(url,quote=True)}">{label}</a></p><p>如果不是你本人申请，请忽略本邮件。</p></body></html>'
    return address,{'subject':'研读 · '+label,'text':text,'html':html}

class MemberMailRelay:
    def __init__(self,store,bridge,sender):self.store=store;self.bridge=bridge;self.sender=sender
    def check(self):
        state=self.bridge.call('/api/admin/state')
        if state.get('limit')!=2 or len(state.get('users',[]))>2:raise ValueError('订阅队列配置无效')
        return {'status':'ready','pending':sum(job.get('status')=='pending' for job in state.get('outbox',[]))}
    def run(self):
        stage='storage'
        try:
            self.store.safe();stage='claim';job=self.bridge.call('/api/bridge/claim').get('job')
        except Exception as error:
            return {'status':'failed','stage':stage,'error_type':type(error).__name__,'http_status':getattr(error,'status',None)}
        if not job:return {'status':'idle'}
        import re
        if not re.fullmatch('[a-f0-9-]{36}',str(job.get('id',''))):raise ValueError('邮件任务无效')
        if not self.store.create('member-mail/'+job['id']+'.json',{'status':'claimed'}):return {'status':'already-claimed'}
        if self.bridge.call('/api/bridge/mail-active',{'id':job['id']}).get('active') is not True:
            self.bridge.call('/api/bridge/finish',{'id':job['id'],'status':'rejected'});return {'status':'cancelled'}
        recipient,message=account_message(job,self.bridge.origin)
        # A one-recipient capability is created only for this claimed, validated job.
        sender=self.sender([recipient],lambda address:self.bridge.call('/api/bridge/mail-active',{'id':job['id']}).get('active') is True)
        try:sender.send(recipient,message)
        except Exception:
            self.bridge.call('/api/bridge/finish',{'id':job['id'],'status':'unknown'})
            return {'status':'unknown'}
        self.bridge.call('/api/bridge/finish',{'id':job['id'],'status':'accepted'})
        return {'status':'accepted'}
