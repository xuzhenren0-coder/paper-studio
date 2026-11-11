import copy,io,json,tempfile,unittest,urllib.parse
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from mailing.core import validate_paper,choose_paper,render,dispatch,day,SHANGHAI
from mailing.aliyun import AliyunSender,signed_parameters
from mailing.store import LocalStore
from mailing.demo import sample

def paper():
    p=sample();p.update(doi='10.1234/morning-test',source='Vehicle System Dynamics',issns=['0042-3114'],publication_kind='正式出版候选',rights_verified=True)
    return p
class MorningMailTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'test-results');self.store=LocalStore(Path(self.temp.name)/'deliveries.sqlite3');self.sender=Mock();self.sender.send.return_value={'EnvId':'test-message','RequestId':'test-request'}
        self.user={'email':'reader@example.org','name':'同学','enabled':True,'confirmed':True};self.now=datetime.combine(day(),datetime.min.time(),tzinfo=SHANGHAI).replace(hour=8)
    def tearDown(self):self.temp.cleanup()
    def test_original_source_and_license_are_required(self):
        p=paper();validate_paper(p)
        for field,value in [('rights_verified',False),('license_url','https://creativecommons.org/licenses/by-nd/4.0/'),('excerpt','Invented quotation'),('issns',['9999-9999'])]:
            bad=copy.deepcopy(p);bad[field]=value
            with self.assertRaises(ValueError):validate_paper(bad)
    def test_undated_future_and_old_papers_excluded(self):
        for offset in (-1,366):
            p=paper();p['published']=(day()-timedelta(days=offset)).isoformat()
            self.assertIsNone(choose_paper([p],['vehicle'],[]))
    def test_personalization_and_no_repeat(self):
        p=paper();self.assertIsNotNone(choose_paper([p],['vehicle'],[]));self.assertIsNone(choose_paper([p],['battery'],[]));self.assertIsNone(choose_paper([p],['vehicle'],[p['doi']]))
    def test_email_is_escaped_and_includes_text_translation_and_unsubscribe(self):
        p=paper();p['title_zh']='<script>测试</script>';result=render(p,'<同学>','https://mail.example.net/unsubscribe/token')
        self.assertNotIn('<script>',result['html']);self.assertIn('&lt;script&gt;',result['html']);self.assertIn('中文译文',result['text']);self.assertIn('退订',result['html']);self.assertNotIn('example.org/demo-unsubscribe',result['html'])
    def test_unconfirmed_recipient_and_early_invocation_never_send(self):
        user=dict(self.user,confirmed=False)
        self.assertEqual(dispatch(self.store,self.sender,user,paper(),'https://mail.example.net/unsubscribe/x',self.now)['status'],'not-subscribed')
        self.assertEqual(dispatch(self.store,self.sender,self.user,paper(),'https://mail.example.net/unsubscribe/x',self.now.replace(hour=7))['status'],'outside-window');self.sender.send.assert_not_called()
    def test_sample_unsubscribe_url_blocks_live_delivery(self):
        with self.assertRaises(ValueError):dispatch(self.store,self.sender,self.user,paper(),'https://example.org/demo-unsubscribe',self.now)
        self.sender.send.assert_not_called()
    def test_duplicate_job_and_reopened_store_cannot_send_again(self):
        first=dispatch(self.store,self.sender,self.user,paper(),'https://mail.example.net/unsubscribe/x',self.now);self.assertEqual(first['status'],'accepted')
        store=LocalStore(self.store.path);second=dispatch(store,self.sender,self.user,paper(),'https://mail.example.net/unsubscribe/x',self.now);self.assertEqual(second['status'],'already-read');self.sender.send.assert_called_once()
    def test_uncertain_delivery_cannot_be_retried_next_day(self):
        self.sender.send.side_effect=TimeoutError()
        self.assertEqual(dispatch(self.store,self.sender,self.user,paper(),'https://mail.example.net/unsubscribe/x',self.now)['status'],'unknown')
        self.assertEqual(dispatch(self.store,self.sender,self.user,paper(),'https://mail.example.net/unsubscribe/x',self.now+timedelta(days=1))['status'],'already-read');self.sender.send.assert_called_once()
    def test_rpc_signature_is_stable_and_encodes_special_characters(self):
        p=signed_parameters({'Action':'SingleSendMail','Subject':'A B+中文'},'test-id','test-secret',timestamp='2026-11-04T00:00:00Z',nonce='fixed')
        q=signed_parameters({'Subject':'A B+中文','Action':'SingleSendMail'},'test-id','test-secret',timestamp='2026-11-04T00:00:00Z',nonce='fixed')
        self.assertEqual(p['Signature'],q['Signature']);self.assertNotIn('test-secret',json.dumps(p));self.assertIn('Signature',p)
    def test_transport_defaults_off_and_never_uses_multiple_recipients(self):
        sender=AliyunSender('sender@example.org','test-id','test-secret')
        with patch('urllib.request.build_opener') as network:
            with self.assertRaises(ValueError):sender.send('reader@example.org',{'subject':'x','html':'x','text':'x'})
            network.assert_not_called()
        sender.enabled=True
        with self.assertRaises(ValueError):sender.send('a@example.org,b@example.org',{'subject':'x','html':'x','text':'x'})
    def test_transport_uses_configured_address_one_recipient_and_records_acceptance(self):
        response=Mock();response.read.return_value=b'{"EnvId":"test-message","RequestId":"test-request"}';response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        sender=AliyunSender('sender@example.org','test-id','test-secret',enabled=True)
        with patch('urllib.request.build_opener') as network:
            network.return_value.open.return_value=response
            self.assertEqual(sender.send('reader@example.org',{'subject':'测试标题','html':'<p>测试</p>','text':'测试'}),{'EnvId':'test-message','RequestId':'test-request'})
            request=network.return_value.open.call_args.args[0];fields=urllib.parse.parse_qs(request.data.decode())
            self.assertEqual(fields['ToAddress'],['reader@example.org']);self.assertEqual(fields['AddressType'],['1']);self.assertEqual(request.full_url,'https://dm.aliyuncs.com/')
            self.assertIn('HtmlBody',fields);self.assertIn('TextBody',fields);network.return_value.open.assert_called_once()

    def test_block_lists_accept_live_schema_without_request_id_and_follow_pages(self):
        responses=[{'Data':[{'BlockEmail':'stopped@example.org'}],'NextToken':'page-2'},
                   {'Data':[],'NextToken':''},{'Data':[],'NextToken':''}]
        sender=AliyunSender('sender@example.org','test-id','test-secret')
        with patch('urllib.request.build_opener') as network:
            network.return_value.open.side_effect=[io.BytesIO(json.dumps(x).encode()) for x in responses]
            self.assertEqual(sender.blocked_recipients(),{'stopped@example.org'})
            second=network.return_value.open.call_args_list[1].args[0]
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(second.full_url).query)['NextToken'],['page-2'])

    def test_block_list_error_or_missing_schema_never_becomes_empty_success(self):
        sender=AliyunSender('sender@example.org','test-id','test-secret')
        for response in ({'Code':'Forbidden','Data':[],'NextToken':''},{'Success':False,'Data':[],'NextToken':''},{'RequestId':'request'},{'Data':[],'NextToken':None}):
            with self.subTest(response=response),patch('urllib.request.build_opener') as network:
                network.return_value.open.return_value=io.BytesIO(json.dumps(response).encode())
                with self.assertRaises(ValueError):sender.blocked_recipients()

if __name__=='__main__':unittest.main()
