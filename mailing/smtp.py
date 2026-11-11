"""Official QQ SMTP transport. TLS, authenticated sender, no automatic retries."""
import re,smtplib,ssl
from email.message import EmailMessage
from email.headerregistry import Address
from email.utils import format_datetime,make_msgid
from datetime import datetime,timezone
from .core import email_address

class QQSender:
    owner_only=True
    host='smtp.qq.com'
    port=465
    def __init__(self,account,authorization_code,enabled=False):
        self.account=email_address(account).lower()
        if not self.account.endswith('@qq.com'):raise ValueError('请使用QQ邮箱完整地址')
        if not re.fullmatch(r'[A-Za-z]{16}',authorization_code):raise ValueError('请填写16位邮箱授权码')
        self._authorization_code=authorization_code;self.enabled=enabled
    def _connect(self):
        connection=smtplib.SMTP_SSL(self.host,self.port,timeout=25,context=ssl.create_default_context())
        try:
            connection.login(self.account,self._authorization_code)
            return connection
        except Exception:
            connection.close()
            raise
    def check(self):
        # Authenticate and NOOP only: never creates or sends a message.
        with self._connect() as connection:
            code,_=connection.noop()
            if code!=250:raise ValueError('邮箱连接检查未通过')
        return {'status':'authenticated','provider':'qq-smtp','email_sent':False}
    def send(self,recipient,message):
        if not self.enabled:raise ValueError('真实发送未启用')
        recipient=email_address(recipient).lower()
        # This migration is a personal pilot, not a bulk subscriber transport.
        if not self.allowed(recipient):raise ValueError('收件人未获授权或已停止订阅')
        if '${DM:' in message['html'] or '${DM:' in message['text']:raise ValueError('阿里云退订占位符不能用于SMTP')
        mail=EmailMessage();mail['From']=Address('研读晨读',addr_spec=self.account)
        mail['To']=recipient;mail['Subject']=message['subject'];mail['Date']=format_datetime(datetime.now(timezone.utc))
        mail['Message-ID']=make_msgid(domain='qq.com')
        mail.set_content(message['text']);mail.add_alternative(message['html'],subtype='html')
        with self._connect() as connection:
            refused=connection.send_message(mail,from_addr=self.account,to_addrs=[recipient])
            if refused:raise ValueError('邮箱服务器未接受收件人')
        # Accepted means submission only. Inbox receipt still needs verification.
        return {'provider':'qq-smtp','message_id':str(mail['Message-ID']),'status':'accepted'}
    def allowed(self,recipient):return recipient==self.account

class QQMemberSender(QQSender):
    """Explicit, bounded allowlist plus a fresh server-side consent check."""
    owner_only=False
    def __init__(self,account,authorization_code,recipients,check,enabled=False):
        super().__init__(account,authorization_code,enabled)
        self.recipients={email_address(r).lower() for r in recipients};self._check=check
        if len(self.recipients)>2 or not callable(check):raise ValueError('受邀收件人配置无效')
    def allowed(self,recipient):return recipient in self.recipients and self._check(recipient) is True
