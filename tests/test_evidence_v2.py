import tempfile
import unittest
from pathlib import Path
from src.fetch_sources import Article, SourceResult
from src.evidence import assess, subjects, event_id
from src.editor_report import render_editor_report, topic_for
from src.company_context import company_cards
from src.explain_report import explain


class EvidenceTests(unittest.TestCase):
    def test_headline_and_metadata_stay_concise(self):
        for hint in ('','metadata'):
            a=Article('Ledger wallet tampering suspected','https://example.com/a','The Verge',None,
                      'Reports describe suspected Ledger hardware wallet tampering. The cause remains under investigation.',[],hint)
            self.assertEqual(assess(a).level,'C')
            with tempfile.TemporaryDirectory() as tmp:
                _,_,body=render_editor_report([SourceResult('The Verge',[a],'ok')],Path(tmp))
            self.assertNotIn('### 1.',body)
            self.assertNotIn('暫不生成九段分析',body)
            self.assertNotIn('事件 ID',body)
            self.assertNotIn('## 1.',body)

    def test_primary_and_reported_evidence_and_security_specific_analysis(self):
        a=Article('Ledger wallet tampering suspected','https://example.com/a','The Verge',None,
                  'Reports describe suspected Ledger hardware wallet tampering. The cause remains under investigation.',[],'public summary')
        self.assertEqual(assess(a).level,'B')
        ex=explain(a,topic_for(a),'Reported')
        self.assertIn('裝置',ex['attention']);self.assertIn('韌體',ex['impact'])
        self.assertNotIn('新功能採用',ex['impact'])
        official=Article('NVIDIA releases tools','https://blogs.nvidia.com/a','官方：NVIDIA',None,
                         'NVIDIA announced new simulation tools for developers. The release describes physics tests and scene validation.',[],'public summary')
        self.assertEqual(assess(official).level,'A')
        self.assertEqual(event_id(official),event_id(official))

    def test_publisher_is_not_subject(self):
        a=Article('Anthropic releases a model','https://blog.google/a','官方：Google',None,'',[])
        self.assertEqual(subjects(a),['Anthropic'])
        self.assertEqual([c['name'] for c in company_cards(a)],['Anthropic'])
        unknown=Article('An unnamed team announces a study','https://blog.google/b','官方：Google',None,'',[])
        self.assertEqual(subjects(unknown),[])
        self.assertTrue(company_cards(unknown)[0]['fallback'])

    def test_preview_is_not_a_verified_product_event(self):
        a=Article("What to expect from Apple's launch event",'https://example.com/preview','The Verge',None,
                  'Apple is coming up on its launch event. We expect smart home announcements and product refreshes.',[],'public summary')
        self.assertEqual(assess(a).level,'C')
