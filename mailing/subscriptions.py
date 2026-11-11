"""Scoped invitations and append-only consent for a small, private pilot."""
import base64,hashlib,hmac,json,re,time
from .core import email_address,https_url

def encoded(raw):return base64.urlsafe_b64encode(raw).decode().rstrip('=')
def decoded(value):return base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)

class Tokens:
    def __init__(self,secret):
        self.secret=bytes.fromhex(secret)
        if len(self.secret)<32:raise ValueError('订阅签名密钥至少32字节')
    def subscriber_id(self,email):
        return hmac.new(self.secret,b'email:'+email_address(email).lower().encode(),hashlib.sha256).hexdigest()
    def issue(self,sid,generation,purpose,expires=None):
        if purpose not in ('confirm','unsubscribe'):raise ValueError('无效令牌用途')
        body={'sid':sid,'generation':generation,'purpose':purpose,'expires':expires}
        payload=encoded(json.dumps(body,sort_keys=True,separators=(',',':')).encode())
        return payload+'.'+encoded(hmac.new(self.secret,payload.encode(),hashlib.sha256).digest())
    def verify(self,token,purpose,now=None):
        try:
            if not isinstance(token,str) or len(token)>1500:raise ValueError()
            payload,signature=token.split('.')
            expected=hmac.new(self.secret,payload.encode(),hashlib.sha256).digest()
            if not hmac.compare_digest(decoded(signature),expected):raise ValueError()
            body=json.loads(decoded(payload))
            if set(body)!={'sid','generation','purpose','expires'} or body['purpose']!=purpose:raise ValueError()
            if not re.fullmatch(r'[a-f0-9]{64}',body['sid']) or not re.fullmatch(r'[a-f0-9]{32}',body['generation']):raise ValueError()
            expiry=body['expires']
            if purpose=='confirm' and not isinstance(expiry,int):raise ValueError()
            if expiry is not None and (not isinstance(expiry,int) or expiry<=(now if now is not None else time.time())):raise ValueError()
            return body
        except (ValueError,TypeError,KeyError,UnicodeError):raise ValueError('链接无效或已过期') from None

class Subscriptions:
    def __init__(self,store,tokens,subscribers,page_url):
        self.store=store;self.tokens=tokens;self.page_url=https_url(page_url) if page_url else None
        if page_url and ('#' in page_url or '?' in page_url):raise ValueError('订阅页面地址不得包含参数')
        if not 1<=len(subscribers)<=10:raise ValueError('内测限1—10个受邀邮箱')
        self.subscribers={};emails=set()
        for user in subscribers:
            email=email_address(user['email']).lower();sid=tokens.subscriber_id(email)
            if email in emails:raise ValueError('受邀邮箱不能重复')
            emails.add(email)
            if not re.fullmatch(r'[a-f0-9]{32}',user.get('generation','')):raise ValueError('缺少订阅代次')
            topics=user.get('topics',[])
            if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(not isinstance(t,str) or not 2<=len(t)<=120 for t in topics):raise ValueError('请配置1—8个研究关键词')
            self.subscribers[sid]=dict(user,email=email,sid=sid,name=str(user.get('name') or '同学')[:40])
    def record_key(self,kind,user):return kind+'/'+user['sid']+'/'+user['generation']+'.json'
    def active(self,user):
        # Read unsubscribe before every delivery; submitted messages cannot be recalled.
        return bool(self.store.read(self.record_key('confirmed',user))) and not self.store.read(self.record_key('unsubscribed',user))
    def confirm(self,token,now=None):
        body=self.tokens.verify(token,'confirm',now);user=self.subscribers.get(body['sid'])
        if not user or user['generation']!=body['generation']:raise ValueError('邀请已失效')
        if self.store.read(self.record_key('unsubscribed',user)):raise ValueError('此邀请已退订，请重新申请邀请')
        self.store.create(self.record_key('confirmed',user),{'consented_at':int(now if now is not None else time.time()),'topics':user['topics']})
        return {'status':'confirmed','message':'已订阅，每天北京时间08:00发送。'}
    def unsubscribe(self,token,now=None):
        body=self.tokens.verify(token,'unsubscribe',now)
        key='unsubscribed/'+body['sid']+'/'+body['generation']+'.json'
        self.store.create(key,{'unsubscribed_at':int(now if now is not None else time.time())})
        return {'status':'unsubscribed','message':'已退订。'}
    def link(self,user,purpose,now=None):
        if not self.page_url:raise ValueError('未配置订阅页面')
        expiry=int((now if now is not None else time.time())+48*3600) if purpose=='confirm' else None
        token=self.tokens.issue(user['sid'],user['generation'],purpose,expiry)
        # Fragments keep consent tokens out of the static site's request URL and access log.
        return self.page_url+'#'+purpose+'='+token

class ManagedSubscriptions(Subscriptions):
    managed_unsubscribe=True
    def __init__(self,store,tokens,subscribers):super().__init__(store,tokens,subscribers,None)
    def link(self,user,purpose,now=None):
        from .core import MANAGED_UNSUBSCRIBE
        if purpose!='unsubscribe':raise ValueError('内测订阅由管理员核实并登记同意')
        return MANAGED_UNSUBSCRIBE

class OwnerSubscriptions(Subscriptions):
    """Personal QQ pilot: the authenticated account receives its own digest only."""
    owner_only=True
    stop_url='https://help.mail.qq.com/detail/106/985'
    def __init__(self,store,tokens,subscribers,account):
        super().__init__(store,tokens,subscribers,None)
        if len(self.subscribers)!=1 or next(iter(self.subscribers.values()))['email']!=email_address(account).lower():
            raise ValueError('QQ晨读仅允许本人邮箱订阅')
    def link(self,user,purpose,now=None):
        if purpose!='unsubscribe':raise ValueError('本人晨读需由邮箱所有者确认')
        return self.stop_url
