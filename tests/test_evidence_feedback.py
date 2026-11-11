"""Offline protocol and adversarial fixtures; no professional model-quality claims."""
import copy,json,unittest
import evidence_feedback as ef
import server
from pathlib import Path

class EvidenceFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.paper={'id':'fixture','pages':[{'page':1,'text':'First context. Repeated source sentence. Next context. Repeated source sentence. Final context.', 'chunks':[]},
            {'page':10,'text':'The controller is evaluated only at 20 m/s. The result does not establish stability on ice.', 'chunks':[]}]}
        self.notes={'answerProblem':'该控制器不能据此声称适用于冰面。','studyEvidence':{'answerProblem':[{'page':10,'quote':'The result does not establish stability on ice.'}]}}
    def test_required_evidence_is_first_even_with_chinese_answers(self):
        snap,chunks,bindings=ef.prepare(self.paper,self.notes,server.resolve_source,[{'id':'p1-c1','page':1,'text':self.paper['pages'][0]['text']}])
        self.assertEqual(chunks[0]['page'],10);self.assertEqual(bindings['answerProblem'][0]['quote'],self.notes['studyEvidence']['answerProblem'][0]['quote'])
        self.assertEqual(snap['answerMethod'],'')
    def test_forged_or_wrong_page_evidence_is_not_sent(self):
        for page,quote in [(10,'Invented unsupported source.'),(1,self.notes['studyEvidence']['answerProblem'][0]['quote'])]:
            n=copy.deepcopy(self.notes);n['studyEvidence']['answerProblem']=[{'page':page,'quote':quote}]
            with self.subTest(page=page),self.assertRaises(ValueError):ef.prepare(self.paper,n,server.resolve_source,[])
    def test_evidence_overflow_blocks_before_model_and_is_not_silently_truncated(self):
        paper={'id':'large','pages':[{'page':1,'text':'A sentence for source material. '*230,'chunks':[]}]}
        n={'answerProblem':'测试作答','studyEvidence':{'answerProblem':[{'page':1,'quote':paper['pages'][0]['text'][:5900]}]*6}}
        with self.assertRaisesRegex(ValueError,'上下文容量'):ef.prepare(paper,n,server.resolve_source,[])
    def test_answers_overflow_blocks_before_model(self):
        with self.assertRaisesRegex(ValueError,'作答超过'):ef.prepare(self.paper,{'answerProblem':'字'*10001},server.resolve_source,[])
    def test_repeated_quote_needs_verified_surroundings(self):
        quote='Repeated source sentence.'
        self.assertTrue(ef.anchor(self.paper,1,quote)['ambiguous'])
        a=ef.anchor(self.paper,1,quote,{'prefix':ef.text_key('Next context. '),'suffix':ef.text_key(' Final context.')})
        self.assertFalse(a['ambiguous']);self.assertEqual(a['offset'],ef.text_key(self.paper['pages'][0]['text']).rfind(ef.text_key(quote)))
    def test_ai_chunk_context_disambiguates_citation(self):
        a=ef.anchor(self.paper,1,'Repeated source sentence.',context='Next context. Repeated source sentence. Final context.')
        self.assertFalse(a['ambiguous']);self.assertIn('nextcontext.',a['prefix'])
    def test_document_version_rejects_stale_anchor(self):
        with self.assertRaisesRegex(ValueError,'文档已变化'):ef.anchor(self.paper,10,'The controller',{'document':'old-document'})
    def test_one_real_citation_does_not_certify_other_claims(self):
        obj={'feedback':[{'field':'answerProblem','claims':[
            {'text':'保留20m/s工况。','status':'supported','evidence_ids':['C1']},
            {'text':'可推广到冰面。','status':'supported','evidence_ids':[]},
            {'text':'图2证明稳定。','status':'supported','evidence_ids':['UNKNOWN']}]}]}
        rows=ef.validate_feedback(obj,[{'ref':'C1'}],ef.snapshot(self.notes))
        self.assertEqual([c['status'] for c in rows[0]['claims']],['supported','insufficient','insufficient'])
        self.assertEqual(rows[0]['status'],'insufficient');self.assertEqual(len(rows),4)
    def test_partial_invalid_ref_does_not_pass_with_one_good_ref(self):
        obj={'feedback':[{'field':'answerProblem','claims':[{'text':'判断','status':'contradicted','evidence_ids':['C1','fake']}]}]}
        row=ef.validate_feedback(obj,[{'ref':'C1'}],ef.snapshot(self.notes))[0]
        self.assertEqual(row['claims'][0]['status'],'insufficient')
    def test_missing_evidence_can_be_saved_as_insufficient(self):
        rows=ef.validate_feedback({'feedback':[{'field':'answerProblem','claims':[{'text':'当前材料未覆盖此条件。','status':'insufficient','evidence_ids':[]}]}]},[],ef.snapshot(self.notes))
        self.assertEqual(len(rows),4);self.assertTrue(all(r['status']=='insufficient' for r in rows))
    def test_blank_answer_cannot_be_marked_supported(self):
        rows=ef.validate_feedback({'feedback':[{'field':'answerMethod','claims':[{'text':'模型代答','status':'supported','evidence_ids':['C1']}]}]},[{'ref':'C1'}],ef.snapshot(self.notes))
        self.assertEqual(rows[1]['status'],'insufficient')
    def test_duplicate_or_unknown_fields_and_bad_shapes_are_rejected(self):
        for rows in [[{'field':'invented','claims':[]}],[{'field':'answerProblem','claims':[] }]*2,[{'field':'answerProblem','claims':'bad'}]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):ef.validate_feedback({'feedback':rows},[],ef.snapshot(self.notes))
    def test_ligature_hyphenation_normalization_keeps_number_ranges(self):
        self.assertEqual(ef.text_key('efﬁcient non-\nlinear'),ef.text_key('efficient nonlinear'))
        self.assertNotEqual(ef.text_key('1-2 vehicles'),ef.text_key('12 vehicles'))
    def test_acceptance_cases_have_explicit_source_and_rubric(self):
        cases=json.loads((Path(__file__).parent/'fixtures/evidence_learning_cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cases['cases']),12)
        for case in cases['cases']:
            self.assertIn(case['quote'],cases['source']);self.assertIn(case['expected'],ef.STATUS);self.assertTrue(case['rubric'])

if __name__=='__main__':unittest.main()
