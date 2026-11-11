"""OSS V4 storage. Atomic create uses OSS forbid-overwrite, not unsupported If-None-Match."""
import hashlib,io,json,re
from urllib.parse import quote,unquote

def service_error(error,sdk):
    """Unwrap the SDK's operation context without exposing signed requests."""
    for _ in range(5):
        if isinstance(error,sdk.exceptions.ServiceError):return error
        operation_error=getattr(sdk.exceptions,'OperationError',())
        if not operation_error or not isinstance(error,operation_error):return None
        error=error.unwrap()
    return None

class OssStore:
    def __init__(self,client,sdk,bucket,prefix='morning/'):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]',bucket):raise ValueError('无效Bucket名称')
        self.client=client;self.sdk=sdk;self.bucket=bucket;self.prefix=prefix
        if not re.fullmatch(r'[a-z0-9/-]+/',prefix) or '..' in prefix:raise ValueError('无效存储前缀')
    def safe(self):
        version=self.client.get_bucket_versioning(self.sdk.GetBucketVersioningRequest(bucket=self.bucket)).version_status
        acl=self.client.get_bucket_acl(self.sdk.GetBucketAclRequest(bucket=self.bucket)).acl
        if version not in (None,'') or acl!='private':raise ValueError('晨读Bucket必须为私有且从未启用版本控制')
    def key(self,key):
        if not isinstance(key,str) or key.startswith('/') or any(x in ('..','.') for x in key.split('/')):raise ValueError('无效存储路径')
        return self.prefix+key
    def read(self,key):
        try:
            result=self.client.get_object(self.sdk.GetObjectRequest(bucket=self.bucket,key=self.key(key)))
            try:
                chunks=[];size=0
                for chunk in result.body.iter_bytes():
                    size+=len(chunk)
                    if size>2*1024*1024:raise ValueError('晨读数据过大')
                    chunks.append(chunk)
                raw=b''.join(chunks)
            finally:result.body.close()
            if len(raw)>2*1024*1024:raise ValueError('晨读数据过大')
            return json.loads(raw)
        except Exception as error:
            failure=service_error(error,self.sdk)
            if failure is None:raise
            if failure.status_code==404 and failure.code=='NoSuchKey':return None
            raise RuntimeError('云存储读取失败') from None
    def create(self,key,value):
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        if len(raw)>2*1024*1024:raise ValueError('晨读数据过大')
        try:
            self.client.put_object(self.sdk.PutObjectRequest(bucket=self.bucket,key=self.key(key),body=io.BytesIO(raw),
                content_type='application/json',server_side_encryption='AES256',forbid_overwrite=True))
            return True
        except Exception as error:
            failure=service_error(error,self.sdk)
            if failure is None:raise
            if failure.status_code==409 and failure.code=='FileAlreadyExists':return False
            raise RuntimeError('云存储写入失败') from None
    def keys(self,prefix):
        full=self.key(prefix)
        for page in self.client.list_objects_v2_paginator().iter_page(self.sdk.ListObjectsV2Request(bucket=self.bucket,prefix=full)):
            for item in page.contents or []:yield item.key[len(self.prefix):]
    def email_key(self,email):return hashlib.sha256(email.strip().lower().encode()).hexdigest()
    def claim(self,key,body):
        prefix=self.email_key(body['recipient'])
        if not self.create('claims/'+prefix+'/'+body['day']+'.json',dict(body,claim_id=key)):return False
        # A lost response may reserve a paper without delivering it. Never retry blindly.
        return self.create('papers/'+prefix+'/'+quote(body['doi'].lower(),safe=''),{'claim_id':key})
    def finish(self,key,status,result):return self.create('results/'+key+'.json',{'status':status,'provider':result})
    def sent_dois(self,email):
        prefix='papers/'+self.email_key(email)+'/'
        return [unquote(key[len(prefix):]) for key in self.keys(prefix)]
