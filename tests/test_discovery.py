import json, sqlite3, tempfile, unittest, time
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import discovery, server

def candidate(title='Vehicle lateral control with MPC',identifier='10.1234/example',kind='正式出版候选'):
    return {'key':'provider-id','doi':identifier,'title':title,'published':discovery.today().isoformat(),'date_label':'发表日期','source':'Test Journal','authors':'Test Author','abstract':'A vehicle lateral control model predictive method.','landing_url':'https://example.org/article','pdf_url':'https://example.org/paper.pdf','license':'cc-by','publication_kind':kind,'providers':['OpenAlex'],'citations':0,'provider_rank':0,'review_status':'待核实'}

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.original=server.DATA;target=server.ROOT/'test-results';target.mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(dir=target);server.DATA=Path(self.temp.name)
        self.service=discovery.Discovery(server.db,server.import_pdf);self.options={'query':'vehicle lateral control','days':365,'preprints':False,'quality':'broad'}
    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to((server.ROOT/'test-results').resolve())
        server.DATA=self.original;self.temp.cleanup()
    def search(self,rows=None,**data):
        with patch('discovery.openalex',return_value=(rows if rows is not None else [candidate()],1)),patch('discovery.crossref',return_value=([],0)):
            return self.service.search({**self.options,**data})
    def test_chinese_terms_are_editable_not_silent_translation(self):
        r=discovery.prepare_topic('低附着路面的车辆横向控制')
        self.assertIn('low friction',r['query']);self.assertIn('lateral control',r['query'])
        self.assertTrue(discovery.prepare_topic('未知专业词语')['unmapped'])
    def test_abstract_inverted_index(self):self.assertEqual(discovery.reconstruct({'control':[1],'vehicle':[0,2]}),'vehicle control vehicle')
    def test_same_doi_and_title_are_deduplicated(self):
        first=candidate(kind='预印本或存储库版本');second=candidate();second['providers']=['Crossref'];second['pdf_url']=''
        r=discovery.merge_rank([first,second],self.options['query']);self.assertEqual(len(r),1);self.assertEqual(r[0]['publication_kind'],'正式出版候选');self.assertEqual(r[0]['providers'],['Crossref','OpenAlex']);self.assertEqual(r[0]['citations'],0)
    def test_preprints_are_opt_in(self):
        r=candidate(kind='预印本或存储库版本');self.assertFalse(discovery.merge_rank([r],self.options['query']));self.assertEqual(len(discovery.merge_rank([r],self.options['query'],preprints=True)),1)
    def test_seed_paper_is_excluded(self):self.assertFalse(discovery.merge_rank([candidate()],self.options['query'],exclude_doi='10.1234/example'))
    def test_search_cache_no_second_network_request(self):
        self.search()
        with patch('discovery.openalex',side_effect=AssertionError('must use cache')):
            self.assertTrue(self.service.search(self.options)['cached'])
    def test_refresh_marks_new_candidates_and_keeps_first_seen(self):
        first=self.search();self.assertTrue(first['first_search']);self.assertFalse(first['new_ids'])
        second=self.search([candidate(),candidate('Vehicle lateral control robust','10.1234/new')],force=True)
        self.assertEqual(second['new_ids'],['doi:10.1234/new']);self.assertEqual(first['results'][0]['first_seen'],second['results'][0]['first_seen'])
    def test_partial_failure_retains_other_source(self):
        with patch('discovery.openalex',side_effect=TimeoutError()),patch('discovery.crossref',return_value=([candidate()],1)):
            r=self.service.search(self.options);self.assertEqual(len(r['results']),1);self.assertTrue(r['warnings'])
    def test_all_failure_preserves_cached_result(self):
        self.search()
        with patch('discovery.openalex',side_effect=TimeoutError()),patch('discovery.crossref',side_effect=TimeoutError()):
            with self.assertRaises(ValueError):self.service.search({**self.options,'force':True})
        self.assertEqual(len(self.service.search(self.options)['results']),1)
    def test_topics_bookmarks_and_pause_persist(self):
        r=self.search();self.service.save_topic({**self.options,'name':'车辆控制'})
        other=discovery.Discovery(server.db,server.import_pdf);s=other.state();self.assertEqual(s['topics'][0]['name'],'车辆控制')
        other.toggle_topic(s['topics'][0]['id'],False);self.assertFalse(other.refresh()['started'])
        other.bookmark(r['results'][0]['key'],True);self.assertEqual(len(self.service.state()['bookmarks']),1)
        other.bookmark(r['results'][0]['key'],False);self.assertFalse(other.state()['bookmarks'])
    def test_background_refresh_uses_cache_and_respects_cooldown(self):
        self.search();self.service.save_topic(self.options);self.assertTrue(self.service.refresh()['started'])
        end=time.time()+3
        while self.service.refreshing and time.time()<end:time.sleep(.02)
        self.assertFalse(self.service.refreshing);self.assertGreater(self.service.state()['topics'][0]['last_checked'],0);self.assertFalse(self.service.refresh()['started'])
    def test_private_import_and_redirect_targets_rejected(self):
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):discovery.validate_public_url('https://example.org/pdf')
        with self.assertRaises(ValueError):discovery.validate_public_url('file:///secret')
    def test_real_pdf_import_is_idempotent_and_does_not_claim_peer_review(self):
        key=self.search([candidate(identifier='10.3389/fmech.2026.1932727')])['results'][0]['key'];raw=(server.ROOT/'samples/vehicle-control.pdf').read_bytes()
        with patch('discovery.download_pdf',return_value=raw) as download:
            first=self.service.import_candidate(key);second=self.service.import_candidate(key);self.assertEqual(first['paper_id'],second['paper_id']);download.assert_called_once()
        self.assertEqual(server.get_paper(first['paper_id'])['metadata']['review_status'],'待核实')
    def test_openalex_software_excluded(self):
        payload={'results':[{'type':'software','title':'Vehicle control'}],'meta':{'count':1}}
        with patch('discovery.json_get',return_value=payload):self.assertFalse(discovery.openalex('x','2025-01-01','2026-01-01')[0])
    def test_wrong_date_options_rejected(self):
        with self.assertRaises(ValueError):self.service.options({'query':'vehicle','days':-1})
    def test_manual_topic_refresh_bypasses_cache(self):
        self.search();self.service.save_topic(self.options)
        with patch('discovery.openalex',return_value=([candidate()],1)) as fetch,patch('discovery.crossref',return_value=([],0)):
            self.assertTrue(self.service.refresh(force=True)['started'])
            end=time.time()+3
            while self.service.refreshing and time.time()<end:time.sleep(.02)
            self.assertFalse(self.service.refreshing);fetch.assert_called_once()
    def test_provider_future_and_missing_dates_are_not_frontier_results(self):
        a=candidate();a['published']='2099-01-01';b=candidate('Vehicle lateral control undated','10.1234/undated');b['published']=''
        self.assertFalse(self.search([a,b])['results'])

if __name__=='__main__':unittest.main(verbosity=2)
