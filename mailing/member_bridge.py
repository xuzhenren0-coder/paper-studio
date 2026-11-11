"""Authenticated HTTPS control-plane client; no model or mailbox credentials here."""
import hashlib,hmac,json,secrets,time,urllib.request,re
import urllib.error
from urllib.parse import urlparse
from .core import email_address,https_url

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class BridgeError(ValueError):
    def __init__(self,status=None,reason='connection',clock_skew=None,detail=None):
        self.status=status;self.reason=reason;self.clock_skew=clock_skew;self.detail=detail
        super().__init__('无法连接订阅服务，请检查站点与连接配置。')

class MemberBridge:
    def __init__(self,origin,secret,service_token=''):
        u=urlparse(https_url(origin))
        if u.path not in ('','/') or u.query or u.fragment or u.username or u.password:raise ValueError('订阅站点地址无效')
        if not isinstance(secret,str) or len(secret)<32:raise ValueError('订阅连接配置无效')
        if service_token and origin.rstrip('/')!='https://paper-studio-morning-members.xuzhenren0.chatgpt.site':
            raise ValueError('平台服务凭据只能用于其原订阅站点')
        self.origin=origin.rstrip('/');self._secret=secret;self._service_token=service_token
    def call(self,path,body=None):
        if not path.startswith(('/api/admin/','/api/bridge/')):raise ValueError('不支持的订阅接口')
        raw=json.dumps(body or {},ensure_ascii=False,separators=(',',':')).encode();stamp=str(int(time.time()));nonce=secrets.token_hex(16)
        canonical='\n'.join((stamp,nonce,'POST',path,hashlib.sha256(raw).hexdigest()))
        headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'PaperStudioMorning/1.0','x-morning-time':stamp,'x-morning-nonce':nonce,
            'x-morning-signature':hmac.new(self._secret.encode(),canonical.encode(),hashlib.sha256).hexdigest()}
        if self._service_token:headers['OAI-Sites-Authorization']='Bearer '+self._service_token
        try:
            request=urllib.request.Request(self.origin+path,data=raw,headers=headers,method='POST')
            with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
                data=response.read(262145)
            if len(data)>262144:raise ValueError()
            result=json.loads(data)
            if not isinstance(result,dict):raise ValueError()
            return result
        except urllib.error.HTTPError as error:
            reason='http';skew=None;detail=None
            try:
                data=error.read(16384);text=data.decode('utf8','replace')
                if '服务身份验证失败' in text:reason='signature'
                elif '服务请求已处理' in text:reason='replay'
                elif 'error code: 1010' in text:reason='edge-client-header'
                elif 'error code: 1009' in text:reason='edge-region'
                elif 'error code:' in text:reason='edge'
                try:
                    obj=json.loads(text)
                    values=[obj.get(k) for k in ('code','error','message','detail','error_code')]
                    detail=' | '.join(str(v) for v in values if isinstance(v,str))[:180]
                except Exception:
                    title=re.search(r'<title[^>]*>(.*?)</title>',text,re.S|re.I)
                    title_text=re.sub(r'<[^>]+>',' ',title.group(1) if title else '')
                    body=re.sub(r'<style.*?</style>|<script.*?</script>','',text,flags=re.S|re.I)
                    body=re.sub(r'<[^>]+>',' ',body)
                    code=re.search(r'(?:Error|error code:)\s*(\d{4})',body)
                    detail=title_text+' | '+(code.group(0) if code else ' '.join(body.split())[:130])
                detail=re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b','[IP]',detail or '')
                detail=re.sub(r'[A-Za-z0-9_-]{24,}','[redacted]',detail)[:180]
                from email.utils import parsedate_to_datetime
                if error.headers.get('Date'):skew=round(parsedate_to_datetime(error.headers['Date']).timestamp()-time.time())
            except Exception:pass
            raise BridgeError(error.code,reason,skew,detail) from None
        except urllib.error.URLError as error:
            import socket,ssl
            cause=error.reason
            reason='dns' if isinstance(cause,socket.gaierror) else 'tls' if isinstance(cause,ssl.SSLError) else 'timeout' if isinstance(cause,TimeoutError) else 'network'
            detail=re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b','[IP]',str(cause))[:160]
            try:
                families=[row[0] for row in socket.getaddrinfo(urlparse(self.origin).hostname,443,type=socket.SOCK_STREAM)]
                detail+='; IPv4='+str(families.count(socket.AF_INET))+'; IPv6='+str(families.count(socket.AF_INET6))
            except Exception:pass
            raise BridgeError(None,reason,detail=detail) from None
        except Exception as error:raise BridgeError(None,type(error).__name__) from None
    def state(self):return self.call('/api/admin/state')
    def invite(self,body):return self.call('/api/admin/invite',{k:body[k] for k in ('email','name','topics') if k in body})
    def pause(self,body):return self.call('/api/admin/pause',{'id':body.get('id'),'paused':body.get('paused')})

class BridgeSubscriptions:
    """Snapshot for preparation; fresh authoritative status before each SMTP submit."""
    managed_unsubscribe=False
    owner_only=False
    def __init__(self,bridge,tokens):
        self.bridge=bridge;self.subscribers={}
        rows=bridge.call('/api/bridge/subscribers')['users']
        if not isinstance(rows,list) or len(rows)>2:raise ValueError('订阅人数超限')
        for row in rows:
            address=email_address(row['email']).lower();sid=tokens.subscriber_id(address)
            if sid in self.subscribers:raise ValueError('订阅邮箱重复')
            topics=row['topics']
            if not isinstance(topics,list) or not 1<=len(topics)<=3:raise ValueError('关键词设置无效')
            self.subscribers[sid]=dict(row,email=address,sid=sid,unsubscribe_url=https_url(row['unsubscribe_url']))
    def active(self,user):return self.bridge.call('/api/bridge/active',{'id':user['id'],'generation':user['generation'],**({'preferences_version':user['preferences_version']} if 'preferences_version' in user else {})}).get('active') is True
    def link(self,user,purpose,now=None):
        if purpose!='unsubscribe':raise ValueError('请通过邀请邮件验证')
        return user['unsubscribe_url']

def local_bridge(root,require_active=True):
    from .secret_config import load
    path=root/'.local/morning/member-site.dpapi'
    if not path.exists():raise ValueError('订阅服务尚未连接。')
    cfg=load(path)
    if require_active and cfg.get('active') is not True:
        raise ValueError('邀请邮件云端连接尚未通过，暂未启用。' if cfg.get('stage')=='repair-pending' else '订阅页保持私有，邀请与云端发信尚未启用。')
    bridge=MemberBridge(cfg['origin'],cfg['secret'],cfg.get('service_token',''));bridge.live_enabled=cfg.get('active') is True
    return bridge
