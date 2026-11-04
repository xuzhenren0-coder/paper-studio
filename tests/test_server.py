"""Real PDF + persistence integration tests; model tests use a local stub, not a paid service."""
import sys, unittest, tempfile, json, threading, urllib.request, urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class ModelStub(BaseHTTPRequestHandler):
    bad_quote=False
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        text=body['messages'][1]['content']
        if '原文片段：\n' not in text:
            context=json.loads(text)
            reply={'items':[{'id':r['id'],'title_zh':'车辆控制论文标题译文','abstract_zh':'车辆控制方法摘要译文。' if r['abstract'] else ''} for r in context['items']]} if 'items' in context else {'query':'vehicle lateral control','text':'测试检索辅助结果'}
            raw=json.dumps({'choices':[{'message':{'content':json.dumps(reply)}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw);return
        # Use an exact extract from the supplied context, not a stored simulated analysis.
        context=text.split('原文片段：\n',1)[1]
        citation_id=context.split(']',1)[0][1:]
        source=context.split('\n',1)[1].split('\n\n[',1)[0]
        quote=source[:180] if not self.bad_quote else 'This quotation does not occur anywhere in the supplied paper.'
        reply={'text':'测试模型输出，仅用于验证接口和引用链路。','citations':[{'id':citation_id,'quote':quote}]}
        raw=json.dumps({'choices':[{'message':{'content':json.dumps(reply)}}],'usage':{'total_tokens':42}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target=server.ROOT/'test-results';target.mkdir(exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=target);server.DATA=Path(cls.temp.name)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.stub=ThreadingHTTPServer(('127.0.0.1',0),ModelStub)
        for s in (cls.http,cls.stub):threading.Thread(target=s.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
        cls.sample=(server.ROOT/'samples/vehicle-control.pdf').read_bytes()
        cls.paper=cls.request('/api/upload',cls.sample,raw=True)
    @classmethod
    def tearDownClass(cls):
        for s in (cls.http,cls.stub):s.shutdown();s.server_close()
        assert Path(cls.temp.name).resolve().is_relative_to((server.ROOT/'test-results').resolve())
        cls.temp.cleanup()
    @classmethod
    def request(cls,path,body=None,raw=False,headers=None):
        h={'X-Local-Request':'1','Content-Type':'application/pdf' if raw else 'application/json'}
        if headers:h.update(headers)
        data=body if raw else json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(cls.url+path,data=data,headers=h)
        with urllib.request.urlopen(req,timeout=30) as r:return json.loads(r.read())
    def configure(self):
        return self.request('/api/config',{'endpoint':f'http://127.0.0.1:{self.stub.server_port}/v1','model':'local-test-stub','key':'not-a-real-key'})
    def test_pdf_page_mapping_and_file(self):
        self.assertEqual(len(self.paper['pages']),14)
        self.assertTrue(self.paper['pages'][0]['chunks'][0]['id'].startswith('p1-'))
        self.assertGreater(len(self.paper['pages'][0]['text']),100)
        with urllib.request.urlopen(self.url+'/api/papers/'+self.paper['id']+'/pdf') as r:self.assertEqual(r.read(),self.sample)
    def test_notes_persistence_and_revisions(self):
        pid=self.paper['id'];self.request('/api/notes',{'paper_id':pid,'body':{'answerProblem':'学生首次解释'}})
        self.request('/api/notes',{'paper_id':pid,'body':{'answerProblem':'学生修改后的解释'}})
        notes=self.request('/api/papers/'+pid+'/notes');self.assertEqual(notes['body']['answerProblem'],'学生修改后的解释')
        with server.db() as c:self.assertGreaterEqual(c.execute('SELECT count(*) FROM revisions WHERE paper_id=?',(pid,)).fetchone()[0],2)
    def test_validated_citation_and_model_result_saved_separately(self):
        self.configure();ModelStub.bad_quote=False
        result=self.request('/api/learn',{'paper_id':self.paper['id'],'task':'preview','page':1})
        self.assertEqual(result['citations'][0]['page'],1)
        self.assertEqual(result['usage']['total_tokens'],42)
        self.assertTrue(self.request('/api/papers/'+self.paper['id']+'/runs'))
    def test_fabricated_citation_is_rejected(self):
        self.configure();ModelStub.bad_quote=True
        try:
            with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/learn',{'paper_id':self.paper['id'],'task':'ask','page':1,'question':'test'})
            self.assertEqual(err.exception.code,400)
            self.assertIn('没有通过原文引用匹配',json.loads(err.exception.read())['error'])
        finally:ModelStub.bad_quote=False
    def test_translation_requires_real_source_and_student_attempt(self):
        self.configure()
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/learn',{'paper_id':self.paper['id'],'task':'translation','page':1,'source':'Fabricated source text','attempt':'我的译文'})
        self.assertEqual(err.exception.code,400)
    def test_config_never_returns_key(self):
        self.configure();result=self.request('/api/config');self.assertNotIn('key',result);self.assertNotIn('not-a-real-key',json.dumps(result))
    def test_discovery_translation_protocol_cache_and_recommendations(self):
        from unittest.mock import patch
        from test_discovery import candidate
        self.configure()
        with patch('discovery.openalex',return_value=([candidate()],1)),patch('discovery.crossref',return_value=([],0)):
            result=self.request('/api/discovery/search',{'query':'vehicle lateral control','quality':'broad','force':True})
        key=result['results'][0]['key'];cached=self.request('/api/discovery/translations',{'keys':[key]});self.assertEqual(cached['missing'],[key])
        translated=self.request('/api/discovery/translations',{'keys':[key],'run':True});self.assertIn('车辆控制',translated['translations'][key]['title_zh'])
        self.assertFalse(self.request('/api/discovery/translations',{'keys':[key]})['missing'])
        suggestions=self.request('/api/discovery/recommendations?paper_id='+self.paper['id']);self.assertTrue(suggestions['deepen'])
    def test_mutation_requires_local_header(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/config/clear',{},headers={'X-Local-Request':''})
        self.assertEqual(err.exception.code,403)
    def test_plain_http_external_provider_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/config',{'endpoint':'http://example.org/v1','model':'x','key':'x'})
        self.assertEqual(err.exception.code,400)
    def test_no_model_does_not_fabricate_feedback(self):
        self.request('/api/config/clear',{})
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/learn',{'paper_id':self.paper['id'],'task':'preview','page':1})
        self.assertIn('请先',json.loads(err.exception.read())['error'])
    def test_invalid_upload_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/upload',b'not a pdf',raw=True)
        self.assertEqual(err.exception.code,400)
    def test_metadata_title_and_date_validation(self):
        pid=self.paper['id']
        self.request('/api/metadata',{'paper_id':pid,'title':'Verified test title','published':'2026-09-07','doi':'10.3389/fmech.2026.1932727','source':'publisher','review_status':'待核实'})
        p=self.request('/api/papers/'+pid)
        self.assertEqual(p['title'],'Verified test title')
        self.assertEqual(p['metadata']['published'],'2026-09-07')
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/metadata',{'paper_id':pid,'published':'not-a-date'})
    def test_browser_selection_ligature_and_hyphenation(self):
        paper={'pages':[{'page':1,'text':'An efﬁcient non-\nlinear method controls 1-2 vehicles.'}]}
        found=server.resolve_source(paper,1,'An efficient nonlinear method')
        self.assertEqual(found['page'],1)
        self.assertIn('efﬁcient',found['selected'])
        with self.assertRaises(ValueError):server.resolve_source(paper,1,'controls 12 vehicles')
    def test_selection_spanning_chunk_boundary_uses_original_context(self):
        text='A'*1390+' validated vehicle model '+'B'*1000
        found=server.resolve_source({'pages':[{'page':2,'text':text}]},2,'validated vehicle model')
        self.assertEqual(found['selected'],'validated vehicle model')
        self.assertEqual(found['id'],'s-p2')
    def test_direct_translation_requires_canonical_selection(self):
        self.configure();ModelStub.bad_quote=False
        source=self.paper['pages'][0]['text'][100:200]
        result=self.request('/api/learn',{'paper_id':self.paper['id'],'task':'translate','page':1,'source':source})
        self.assertEqual(result['source_page'],1)
        self.assertEqual(result['source'],source.strip())
        self.assertEqual(result['citations'][0]['id'],'s-p1')
    def test_optional_search_ai_expansion_uses_configured_gateway(self):
        self.configure()
        r=self.request('/api/discovery/assist',{'task':'expand','topic':'车辆横向控制'})
        self.assertEqual(r['query'],'vehicle lateral control')

if __name__=='__main__':unittest.main(verbosity=2)
