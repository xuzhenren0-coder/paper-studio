import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import discovery,server,learning_flow
from test_discovery import candidate

class LearningFlowTests(unittest.TestCase):
    def setUp(self):
        self.old=server.DATA;self.temp=tempfile.TemporaryDirectory(dir=server.ROOT/'test-results');server.DATA=Path(self.temp.name)
        self.p=server.import_pdf((server.ROOT/'samples/vehicle-control.pdf').read_bytes(),'test-learning.pdf')
        self.service=discovery.Discovery(server.db,server.import_pdf);self.service.ensure()
    def tearDown(self):server.DATA=self.old;self.temp.cleanup()
    def test_pdf_doi_mismatch_is_rejected_before_import(self):
        with patch('discovery.openalex',return_value=([candidate()],1)),patch('discovery.crossref',return_value=([],0)):
            key=self.service.search({'query':'vehicle control','quality':'broad'})['results'][0]['key']
        with server.db() as c:before=c.execute('SELECT count(*) FROM papers').fetchone()[0]
        with patch('discovery.download_pdf',return_value=(server.ROOT/'samples/vehicle-control.pdf').read_bytes()),self.assertRaisesRegex(ValueError,'DOI'):self.service.import_candidate(key)
        with server.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM papers').fetchone()[0],before)
    def test_next_paper_uses_recent_curated_reserve_and_excludes_completed(self):
        rows=[]
        for i in range(4):
            row=candidate(title='Vehicle lateral control using '+['alpha','beta','gamma','delta'][i],identifier='10.1234/next-'+str(i));row.update(source='Vehicle System Dynamics',issns=['0042-3114']);rows.append(row)
        with patch('discovery.openalex',return_value=(rows,4)),patch('discovery.crossref',return_value=([],0)):
            result=self.service.search({'query':'vehicle lateral control'})
        rows=result['results'];notes={'studyGoal':'测试目标'};notes['studyCompletion']={'signature':learning_flow.signature(notes),'at':1}
        with server.db() as c:
            c.execute('UPDATE papers SET metadata=? WHERE id=?',(json.dumps({'doi':rows[0]['doi']}),self.p['id']))
            other=dict(rows[1]);other['published']='2000-01-01';c.execute('UPDATE discovery_candidates SET body=? WHERE id=?',(json.dumps(other),other['key']))
            other=dict(rows[2]);other['issns']=['9999-9999'];other['source']='Unknown Journal';c.execute('UPDATE discovery_candidates SET body=? WHERE id=?',(json.dumps(other),other['key']))
        nexts=server.STUDY.next_papers(server.get_paper(self.p['id']),['lateral control'])
        self.assertEqual([p['doi'] for p in nexts['papers']],[rows[3]['doi']]);self.assertIn('lateral control',nexts['papers'][0]['reason'])
    def test_only_opening_preview_is_not_a_substantive_learning_signal(self):
        from discovery_learning import DiscoveryLearning
        with server.db() as c:
            c.execute('UPDATE papers SET title=? WHERE id=?',('Model predictive control for path tracking',self.p['id']))
            c.execute('INSERT INTO runs(paper_id,task,body,created) VALUES(?,?,?,?)',(self.p['id'],'preview','{}',1))
        result=DiscoveryLearning(self.service,lambda *_:None).recommendations()
        self.assertEqual(result['seed_count'],0)

if __name__=='__main__':unittest.main()
