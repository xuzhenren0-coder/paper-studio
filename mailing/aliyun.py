"""Aliyun DirectMail classic RPC signing. No credentials or requests at import time."""
import base64,hashlib,hmac,json,os,urllib.parse,urllib.request,uuid
from datetime import datetime,timezone
from .core import email_address

ENDPOINTS={'cn-hangzhou':'https://dm.aliyuncs.com/','ap-southeast-1':'https://dm.ap-southeast-1.aliyuncs.com/','us-west-1':'https://dm.us-west-1.aliyuncs.com/'}
def percent(value):return urllib.parse.quote(str(value),safe='~')
def signed_parameters(parameters,key_id,secret,token='',timestamp=None,nonce=None):
    p=dict(parameters,AccessKeyId=key_id,Format='JSON',SignatureMethod='HMAC-SHA1',SignatureVersion='1.0',Version='2015-11-23',Timestamp=timestamp or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),SignatureNonce=nonce or str(uuid.uuid4()))
    if token:p['SecurityToken']=token
    canonical='&'.join(percent(k)+'='+percent(v) for k,v in sorted(p.items()))
    string='POST&%2F&'+percent(canonical)
    p['Signature']=base64.b64encode(hmac.new((secret+'&').encode(),string.encode(),hashlib.sha1).digest()).decode()
    return p
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('邮件API重定向已拒绝')
class AliyunSender:
    def __init__(self,account_name,key_id,secret,region='cn-hangzhou',token='',reply_to=True,enabled=False):
        if region not in ENDPOINTS:raise ValueError('未配置支持的发信地域')
        self.account=email_address(account_name);self.key_id=key_id;self.secret=secret;self.region=region;self.token=token;self.reply_to=reply_to;self.enabled=enabled
    def send(self,recipient,message):
        if not self.enabled:raise ValueError('真实发送未启用')
        if not self.key_id or not self.secret:raise ValueError('缺少服务端凭据')
        p=signed_parameters({'Action':'SingleSendMail','RegionId':self.region,'AccountName':self.account,'AddressType':'1','ReplyToAddress':str(self.reply_to).lower(),'ToAddress':email_address(recipient),'FromAlias':'研读晨读','Subject':message['subject'],'HtmlBody':message['html'],'TextBody':message['text'],'ClickTrace':'0','UnSubscribeLinkType':'default','UnSubscribeFilterLevel':'mailfrom'},self.key_id,self.secret,self.token)
        request=urllib.request.Request(ENDPOINTS[self.region],data=urllib.parse.urlencode(p).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
        # No automatic network retry; the caller must treat lost responses as uncertain.
        with urllib.request.build_opener(NoRedirect).open(request,timeout=25) as response:result=json.loads(response.read(100000))
        if not result.get('EnvId') or not result.get('RequestId'):raise ValueError('邮件服务未返回可确认的提交结果')
        return {'EnvId':result['EnvId'],'RequestId':result['RequestId']}
