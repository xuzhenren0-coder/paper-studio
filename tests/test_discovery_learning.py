import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import discovery,discovery_learning,discovery_venues,server
from test_discovery import candidate

class DiscoveryLearningTests(unittest.TestCase):
    def setUp(self):
        self.original=server.DATA;self.temp=tempfile.TemporaryDirectory(dir=server.ROOT/'test-results');server.DATA=Path(self.temp.name)
        self.service=discovery.Discovery(server.db,server.import_pdf);self.model=Mock(side_effect=self.translator);self.learning=discovery_learning.DiscoveryLearning(self.service,self.model)
    def tearDown(self):server.DATA=self.original;self.temp.cleanup()
    @staticmethod
    def translator(context,*args):return {'items':[{'id':r['id'],'title_zh':'车辆横向控制研究','abstract_zh':'提出车辆控制方法，保留原研究的条件与局限。' if r['abstract'] else ''} for r in context['items']]}
    def search(self,rows=None,**options):
        with patch('discovery.openalex',return_value=(rows or [candidate()],1)),patch('discovery.crossref',return_value=([],0)),patch('discovery.arxiv',return_value=([],0)):
            return self.service.search({'query':'vehicle lateral control','quality':'broad',**options})
    def test_strict_is_default_and_rejects_unknown_and_conflicting_issn(self):
        self.assertEqual(self.service.options({'query':'vehicle control'})['quality'],'curated')
        accepted=candidate(identifier='10.12/yes');accepted.update(source='Vehicle System Dynamics',issns=['0042-3114'])
        conflict=candidate(identifier='10.12/no');conflict.update(source='Vehicle System Dynamics',issns=['9999-9999'])
        result=self.search([accepted,conflict,candidate()],quality='curated')
        self.assertEqual([r['doi'] for r in result['results']],['10.12/yes']);self.assertTrue(result['results'][0]['venue']['url'].startswith('https://www.tandfonline.com/'))
    def test_openalex_restricts_upstream_source_and_preserves_pdf_version(self):
        data={'results':[{'type':'article','display_name':'Vehicle control','doi':'https://doi.org/10.12/a','publication_date':discovery.today().isoformat(),'language':'en','primary_location':{'source':{'display_name':'Vehicle System Dynamics','type':'journal','issn':['0042-3114']},'is_published':True},'best_oa_location':{'is_oa':True,'pdf_url':'https://repository.example.org/pdf','source':{'display_name':'University repository'}}}]}
        with patch('discovery.json_get',return_value=data) as fetch:
            rows,_=discovery.openalex('control','2025-01-01','2026-12-01',True)
        from urllib.parse import urlparse,parse_qs
        filters=parse_qs(urlparse(fetch.call_args.args[0]).query)['filter'][0]
        self.assertIn('primary_location.source.issn:0042-3114|1744-5159',filters);self.assertIn('language:en',filters);self.assertEqual(rows[0]['pdf_source'],'University repository')
    def test_preprints_do_not_enter_strict_formal_list(self):
        pre=candidate(kind='预印本或存储库版本')
        r=self.search([pre],quality='curated',preprints=True)
        self.assertFalse(r['results']);self.assertEqual(len(r['preprint_results']),1)
    def test_legacy_topic_does_not_reuse_broad_cache_as_curated(self):
        self.service.ensure()
        options={'query':'vehicle lateral control','days':365,'preprints':False,'exclude_doi':''}
        with server.db() as c:
            c.execute('INSERT INTO discovery_topics(id,name,options) VALUES(?,?,?)',('old','旧主题',json.dumps(options)))
            c.execute('INSERT INTO discovery_cache VALUES(?,?,?)',('old',json.dumps({'results':[candidate()]}),0))
        self.assertEqual(self.service.state()['topics'][0]['options']['quality'],'curated');self.assertIsNone(self.service.topic_result('old'))
    def test_translation_cache_survives_new_instance_and_hover_never_calls_model(self):
        key=self.search()['results'][0]['key'];self.assertEqual(self.learning.translations([key])['missing'],[key]);self.model.assert_not_called()
        first=self.learning.translations([key],True);second=discovery_learning.DiscoveryLearning(self.service,self.model).translations([key],True)
        self.assertEqual(first['translations'],second['translations']);self.model.assert_called_once()
    def test_changed_abstract_invalidates_translation_cache(self):
        r=self.search()['results'][0];self.learning.translations([r['key']],True)
        changed=candidate();changed['abstract']='A changed vehicle control abstract.';self.search([changed],force=True)
        self.assertEqual(self.learning.translations([r['key']])['missing'],[r['key']])
    def test_missing_abstract_cannot_receive_invented_introduction(self):
        r=candidate();r['abstract']='';key=self.search([r])['results'][0]['key']
        self.model.side_effect=None;self.model.return_value={'items':[{'id':'0','title_zh':'车辆控制','abstract_zh':'模型凭空补写的摘要'}]}
        self.assertEqual(self.learning.translations([key],True)['translations'][key]['abstract_zh'],'')
    def test_malformed_translation_not_saved_and_batch_limit_enforced(self):
        key=self.search()['results'][0]['key'];self.model.side_effect=None;self.model.return_value={'items':[{'id':'0','title_zh':'English only','abstract_zh':'Also English'}]}
        self.assertEqual(self.learning.translations([key],True)['missing'],[key])
        with self.assertRaises(ValueError):self.learning.translations([key]*11,True)
    def test_import_does_not_become_reading_evidence(self):
        with server.db() as c:c.execute('INSERT INTO papers VALUES(?,?,?,?,?,?)',('paper','Vehicle lateral control','x.pdf','[]',0,'{}'))
        result=self.learning.recommendations();self.assertEqual(result['seed_count'],0);self.assertFalse(result['deepen'][0]['basis'])
    def test_learning_signals_use_metadata_and_never_private_note_text(self):
        with server.db() as c:
            c.execute('INSERT INTO papers VALUES(?,?,?,?,?,?)',('paper','Vehicle lateral control and model predictive control','x.pdf','[]',0,'{}'))
            c.execute('INSERT INTO notes VALUES(?,?,?)',('paper',json.dumps({'personalNotes':'PRIVATE_STUDENT_NOTE'}),10))
        result=self.learning.recommendations();raw=json.dumps(result);self.assertNotIn('PRIVATE_STUDENT_NOTE',raw);self.assertEqual(result['seed_count'],1)
        terms=[r['term'] for r in result['deepen']];self.assertIn('lateral control',terms);self.assertTrue(result['explore'])
        self.learning.ignore('lateral control');self.assertNotIn('lateral control',[r['term'] for r in self.learning.recommendations()['deepen']])
    def test_bookmark_is_explicit_interest_evidence(self):
        key=self.search()['results'][0]['key'];self.service.bookmark(key,True)
        result=self.learning.recommendations();self.assertEqual(result['seed_count'],1);self.assertEqual(result['deepen'][0]['basis'][0]['reason'],'收藏论文');self.model.assert_not_called()
    def test_rate_limit_retries_once_after_requested_short_cooldown(self):
        import urllib.error
        response=Mock();response.read.return_value=b'{"results": []}';response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        failure=urllib.error.HTTPError('https://api.openalex.org',429,'rate limit',{'Retry-After':'3'},None)
        with patch('urllib.request.urlopen',side_effect=[failure,response]) as request,patch('discovery.time.sleep') as sleep:
            self.assertEqual(discovery.json_get('https://api.openalex.org/works'),{'results':[]});sleep.assert_called_once_with(3);self.assertEqual(request.call_count,2)
    def test_long_rate_cooldown_is_not_ignored_or_retried_early(self):
        import urllib.error
        failure=urllib.error.HTTPError('https://api.crossref.org',429,'rate limit',{'Retry-After':'120'},None)
        with patch('urllib.request.urlopen',side_effect=failure) as request,patch('discovery.time.sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError):discovery.json_get('https://api.crossref.org/works')
            request.assert_called_once();sleep.assert_not_called()

if __name__=='__main__':unittest.main()
