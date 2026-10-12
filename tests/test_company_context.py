import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from editor_fixture import generated

from src.company_context import CACHE, company_cards, load_profiles
from src.editor_report import render_editor_report
from src.fetch_sources import Article, SourceResult


class CompanyContextTests(unittest.TestCase):
    def test_known_companies_products_relevance_and_cache_reuse(self):
        a=Article('Anthropic isolates evaluations','https://example.com/news','The Verge',None,'',[])
        before=(CACHE/'anthropic.json').read_bytes()
        first=company_cards(a)
        self.assertEqual(first[0]['name'],'Anthropic')
        self.assertIn('Claude API',first[0]['main_products'])
        self.assertFalse(first[0]['fallback'])
        self.assertEqual(first,company_cards(a))
        self.assertEqual(before,(CACHE/'anthropic.json').read_bytes())

    def test_unknown_company_and_missing_or_corrupt_cache_no_rankings(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'invalid.json').write_text('{broken', encoding="utf-8")
            self.assertEqual(load_profiles(folder),[])
            a=Article('UnknownCorp launches a tool','https://example.com/news','Media',None,'',[])
            self.assertTrue(company_cards(a,folder)[0]['fallback'])
            _,_,body=render_editor_report([SourceResult('Media',[a],'ok')],folder/'reports')
            self.assertIn('素材索引',body)
            self.assertNotIn('## 1.',body)
            self.assertNotIn('世界第一',body)
            self.assertNotIn('市場龍頭',body)

    def test_unverified_market_rank_is_suppressed(self):
        profile=json.loads((CACHE/'nvidia.json').read_text(encoding="utf-8"))
        profile['industry_position']='全球最大、市佔 99% 的市場龍頭'
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'nvidia.json').write_text(json.dumps(profile), encoding="utf-8")
            actual=load_profiles(Path(tmp))[0]['industry_position']
            self.assertIn('缺少可驗證排名資料',actual)
            self.assertNotIn('99%',actual)

    def test_multiple_companies_official_publisher_and_no_false_name_match(self):
        a=Article('NVIDIA and Anthropic compare tools','https://example.com/news','Media',None,'',[])
        self.assertEqual({p['name'] for p in company_cards(a)},{'NVIDIA','Anthropic'})
        fake=Article('Research update','https://example.com/fake','官方：Google',None,'',[])
        self.assertTrue(company_cards(fake)[0]['fallback'])
        official=Article('Clinical research','https://blog.google/test','官方：Google',None,'',[])
        self.assertTrue(company_cards(official)[0]['fallback'])
        self.assertTrue(company_cards(Article('NVIDIAish tools','https://example.com','Media',None,'',[]))[0]['fallback'])

    @patch('src.editor_report.synthesize',side_effect=generated)
    def test_all_main_stories_have_context_fields_and_nine_sections(self,synthesis):
        rows=[SourceResult('Media',[Article(f'{name} releases tools',f'https://example.com/{i}','Media',None,f'{name} announced testing tools for developers. The release describes an API and deployment workflow.',[],'public summary')],'ok')
              for i,name in enumerate(('NVIDIA','Anthropic','Google'))]
        with tempfile.TemporaryDirectory() as tmp:
            _,_,body=render_editor_report(rows,Path(tmp)/'reports')
        for text in ('### 1. 公司背景卡：這家公司是誰？','### 4. 對科技業的影響是什麼？',
                     '### 6. 未來展望','### 9. 仍需查證的地方','**核心業務：**','**主要產品／解決方案：**','**產業地位／市場定位：**'):
            self.assertEqual(body.count(text),3)
        self.assertIn('[Company Context] [Background]',body)
        self.assertNotIn('世界第一',body)
