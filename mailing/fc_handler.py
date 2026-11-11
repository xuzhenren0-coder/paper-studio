"""FC 3.0 HTTP mappings and timer events; no HTTP route can submit mail or run a model."""
import base64,json,os
from .aliyun import AliyunSender
from .subscriptions import Tokens,Subscriptions,ManagedSubscriptions,OwnerSubscriptions
from .smtp import QQSender,QQMemberSender
from .cloud_store import OssStore
from .service import MorningService
from .papers import ModelTranslator,PaperPreparer,verify_source

def environment_service():
    import alibabacloud_oss_v2 as oss
    key=os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID') or os.environ.get('OSS_ACCESS_KEY_ID','')
    secret=os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET') or os.environ.get('OSS_ACCESS_KEY_SECRET','')
    token=os.environ.get('ALIBABA_CLOUD_SECURITY_TOKEN') or os.environ.get('OSS_SESSION_TOKEN','')
    if not key or not secret:raise ValueError('云函数执行角色未提供临时凭据')
    cfg=oss.config.load_default();cfg.region=os.environ['MORNING_OSS_REGION'];cfg.signature_version='v4'
    cfg.credentials_provider=oss.credentials.StaticCredentialsProvider(key,secret,token)
    cfg.retry_max_attempts=1;cfg.enabled_redirect=False;cfg.connect_timeout=8;cfg.readwrite_timeout=20
    store=OssStore(oss.Client(cfg),oss,os.environ['MORNING_BUCKET'])
    managed=os.environ.get('MORNING_SUBSCRIPTION_MODE')=='managed'
    owner=os.environ.get('MORNING_SUBSCRIPTION_MODE')=='owner'
    members=os.environ.get('MORNING_SUBSCRIPTION_MODE')=='members'
    transport=os.environ.get('MORNING_MAIL_TRANSPORT','aliyun')
    if (owner or members)!=(transport=='qq-smtp') or transport not in ('aliyun','qq-smtp'):
        raise ValueError('发信通道与订阅方式不一致')
    send_enabled=os.environ.get('MORNING_SEND_ENABLED')=='true' and (not managed or os.environ.get('MORNING_UNSUBSCRIBE_VERIFIED')=='true')
    if owner:send_enabled=send_enabled and os.environ.get('MORNING_OWNER_STOP_VERIFIED')=='true'
    tokens=Tokens(os.environ['MORNING_TOKEN_SECRET']);users=json.loads(os.environ['MORNING_SUBSCRIBERS_JSON'])
    relay=None
    if members:
        from .member_bridge import MemberBridge,BridgeSubscriptions
        from .member_mail import MemberMailRelay
        bridge=MemberBridge(os.environ['MEMBER_SITE_ORIGIN'],os.environ['MEMBER_BRIDGE_SECRET'],os.environ.get('MEMBER_SITE_SERVICE_TOKEN',''))
        subscriptions=BridgeSubscriptions(bridge,tokens)
        by_email={u['email']:u for u in subscriptions.subscribers.values()}
        sender=QQMemberSender(os.environ['MORNING_SENDER'],os.environ.get('MORNING_SMTP_AUTHORIZATION_CODE',''),by_email,
            lambda address:subscriptions.active(by_email[address]),enabled=send_enabled)
        factory=lambda recipients,check:QQMemberSender(os.environ['MORNING_SENDER'],os.environ.get('MORNING_SMTP_AUTHORIZATION_CODE',''),recipients,check,
            enabled=os.environ.get('MORNING_MEMBER_MAIL_ENABLED')=='true')
        relay=MemberMailRelay(store,bridge,factory)
    elif owner:
        sender=QQSender(os.environ['MORNING_SENDER'],os.environ.get('MORNING_SMTP_AUTHORIZATION_CODE',''),enabled=send_enabled)
        subscriptions=OwnerSubscriptions(store,tokens,users,sender.account)
    else:
        subscriptions=ManagedSubscriptions(store,tokens,users) if managed else Subscriptions(store,tokens,users,os.environ['MORNING_PAGE_URL'])
        sender=AliyunSender(os.environ['MORNING_SENDER'],key,secret,os.environ.get('MORNING_MAIL_REGION','cn-hangzhou'),token,
            enabled=send_enabled,managed_unsubscribe=managed)
    indexed=os.environ.get('MORNING_ALLOW_INDEXED_ABSTRACTS')=='true'
    preparer=PaperPreparer(ModelTranslator(os.environ.get('MORNING_MODEL_ENDPOINT',''),os.environ.get('MORNING_MODEL',''),os.environ.get('MORNING_MODEL_KEY','')),
        verifier=lambda row:verify_source(row,allow_indexed=indexed))
    service=MorningService(store,sender,subscriptions,preparer,send_enabled,os.environ.get('MORNING_PREPARE_ENABLED')=='true')
    service.member_relay=relay
    return service

def route(event,service_factory=environment_service,origin=None):
    if isinstance(event,(bytes,str)):event=json.loads(event)
    if not isinstance(event,dict):raise ValueError('无效事件')
    http=(event.get('requestContext') or {}).get('http')
    if http:
        method=http.get('method','GET').upper();path=event.get('rawPath') or http.get('path','/')
        headers={str(k).lower():str(v) for k,v in (event.get('headers') or {}).items()}
        allowed=origin or os.environ.get('MORNING_PAGE_ORIGIN','')
        cors={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
        if headers.get('origin')==allowed and allowed:
            cors.update({'Access-Control-Allow-Origin':allowed,'Vary':'Origin','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type'})
        def response(code,body):return {'statusCode':code,'headers':cors,'body':json.dumps(body,ensure_ascii=False)}
        if method=='OPTIONS':return response(204,{})
        if method=='GET' and path=='/health':return response(200,{'status':'ok'})
        if method!='POST' or path not in ('/confirm','/unsubscribe'):return response(404,{'message':'页面不存在'})
        if headers.get('origin')!=allowed or not allowed:return response(403,{'message':'来源不受支持'})
        try:
            raw=event.get('body','')
            if len(raw)>5000:raise ValueError('请求过大')
            if event.get('isBase64Encoded'):raw=base64.b64decode(raw,validate=True).decode()
            body=json.loads(raw)
            if set(body)!={'token'}:raise ValueError('无效请求')
            service=service_factory();subscriptions=service.subscriptions
            result=subscriptions.confirm(body['token']) if path=='/confirm' else subscriptions.unsubscribe(body['token'])
            return response(200,result)
        except (ValueError,TypeError,KeyError):return response(400,{'message':'链接无效或已过期'})
        except Exception:return response(503,{'message':'暂时无法处理，请稍后重试'})
    payload=event.get('payload','{}')
    if isinstance(payload,str):payload=json.loads(payload)
    jobs={'morning-prepare':'prepare','morning-send':'send','morning-preflight':'preflight','morning-prepare-check':'prepare-check','morning-member-mail':'member-mail','morning-member-host-check':'member-host-check','morning-personal-tick':'personal-tick','morning-personal-check':'personal-check'}
    action=jobs.get(event.get('triggerName'))
    if not action or payload!={'action':action}:raise ValueError('未识别的云端任务')
    from .member_bridge import BridgeError
    if action=='member-host-check':
        from .member_bridge import MemberBridge
        try:
            bridge=MemberBridge(os.environ['MEMBER_SITE_ORIGIN'],os.environ['MEMBER_BRIDGE_SECRET'],os.environ.get('MEMBER_SITE_SERVICE_TOKEN',''))
            result=bridge.call('/api/bridge/subscribers')
            return {'status':'ready','users':len(result['users'])}
        except BridgeError as error:
            return {'status':'blocked','http_status':error.status,'reason':error.reason,'detail':error.detail}
    try:service=service_factory()
    except BridgeError as error:
        return {'status':'blocked','dependency':'members','http_status':error.status,'reason':error.reason,'clock_skew_seconds':error.clock_skew,'detail':error.detail}
    if action=='preflight':
        service.store.safe()
        if isinstance(service.sender,QQSender):service.sender.check()
        else:service.sender.blocked_recipients()
        if getattr(service,'member_relay',None):
            queue=service.member_relay.check()
            if queue.get('status')!='ready':return {'status':'blocked','dependency':'member-mail-outbox'}
        return {'status':'ready','sending_enabled':service.send_enabled,'prepare_enabled':service.prepare_enabled}
    if action=='prepare-check':return service.prepare(verification=True)
    if action in ('prepare','send') and os.environ.get('MORNING_PERSONALIZED_ENABLED')=='true':
        return {'status':'superseded'}
    if action=='personal-check':
        from .personal import PersonalMorning
        return PersonalMorning(service).check()
    if action=='personal-tick':
        if os.environ.get('MORNING_PERSONALIZED_ENABLED')!='true':return {'status':'paused'}
        from .personal import PersonalMorning
        return PersonalMorning(service).tick()
    if action=='member-mail':
        if os.environ.get('MORNING_MEMBER_MAIL_ENABLED')!='true':return {'status':'paused'}
        if not getattr(service,'member_relay',None):raise ValueError('订阅邮件未配置')
        return service.member_relay.run()
    return service.prepare() if action=='prepare' else service.send()

def handler(event,context):
    try:result=route(event)
    except Exception:
        # Do not log SDK exceptions, signed requests, recipient addresses, or model responses.
        print(json.dumps({'status':'failed','message':'检查服务配置、来源可用性与发送记录'}),flush=True)
        raise RuntimeError('晨读任务未完成') from None
    if 'statusCode' not in result:print(json.dumps(result),flush=True)
    return result
