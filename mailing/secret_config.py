"""Windows per-user DPAPI protection; never bundle this file's encrypted output."""
import ctypes,hashlib,json,os
from ctypes import wintypes
from pathlib import Path

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def transform(raw,protect):
    if os.name!='nt':raise RuntimeError('此配置器仅在Windows本机使用')
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    function=crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise OSError('无法使用当前Windows用户保护配置')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data,ctypes.c_void_p))

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=transform(json.dumps(value,ensure_ascii=False).encode(),True)
    temporary=path.with_suffix('.pending');temporary.write_bytes(raw);os.replace(temporary,path)

def load(path):return json.loads(transform(Path(path).read_bytes(),False))


def config_fingerprint(config):
    fields=('sender','recipient','model_endpoint','model','generation','allow_indexed_abstracts')
    if config.get('mail_transport','aliyun')!='aliyun':fields+=('mail_transport',)
    return hashlib.sha256(json.dumps({k:config.get(k) for k in fields},sort_keys=True).encode()).hexdigest()
