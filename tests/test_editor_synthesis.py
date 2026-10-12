import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.editor_synthesis import synthesize, validate, ENDPOINT
from src.editor_report import render_editor_report, rank_candidates
from src.evidence import assess
from src.fetch_sources import Article, SourceResult
from datetime import datetime, timezone


def article():
    return Article('ExampleCo releases an agent API','https://example.com/api','Tech media',None,
                   'ExampleCo releases an agent API for developers. The API includes per-tool permissions and audit logs for operations.',[],'public summary')


def response():
    return dict(ready=True,facts=[
        dict(text='報導說 ExampleCo 推出讓開發者串接代理的程式介面。',evidence='ExampleCo releases an agent API for developers.'),
        dict(text='這個介面包含工具層級的權限與操作紀錄。',evidence='The API includes per-tool permissions and audit logs for operations.')],
        background='API 是程式溝通的介面；權限則規定哪些操作可以被執行。',
        impact='企業若把代理接上內部系統，可能需要重新檢查工具的授權範圍。',
        attention='檢查代理呼叫工具失敗時能否回復，以及操作紀錄是否完整。',
        outlook='觀察公開的權限模型與實際整合案例，不能從發表推定已廣泛部署。',
        opening='把工作交給 AI，也代表要把哪些鑰匙交出去？今天這則消息讓我們拆開工具權限和操作紀錄。',
        questions=['能否只允許讀取檔案，禁止刪除？'],gaps=['需官方 API 文件確認預設權限與失敗回復流程。'])


class SynthesisTests(unittest.TestCase):
    def test_no_key_never_calls_api_and_report_is_not_complete_brief(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch('src.editor_synthesis.requests.post') as post, tempfile.TemporaryDirectory() as tmp:
            _,subject,body=render_editor_report([SourceResult('Tech media',[article()],'ok')],Path(tmp))
        post.assert_not_called()
        self.assertIn('素材索引',subject)
        self.assertIn('未設定 OPENAI_API_KEY',body)
        self.assertNotIn('## 1.',body)
        self.assertNotIn('事件 ID',body)
        self.assertNotIn('暫不生成九段分析',body)

    def test_unknown_company_not_rejected_by_static_alias_list(self):
        self.assertEqual(assess(article()).level,'B')
        chinese=Article('新公司推出測試工具','https://example.com/t','Tech media',None,
                        '新公司推出測試工具，可以讓開發者檢查程式相容性，公開摘要描述版本比較與錯誤紀錄。',[],'public summary')
        self.assertEqual(assess(chinese).level,'B')

    def test_mocked_api_generates_grounded_chinese_narrative(self):
        import json
        transport=Mock();transport.__enter__=Mock(return_value=transport);transport.__exit__=Mock(return_value=False)
        transport.json.return_value={'choices':[{'message':{'content':json.dumps(response(),ensure_ascii=False)}}]}
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fake-test-only'}),patch('src.editor_synthesis.requests.post',return_value=transport) as post,tempfile.TemporaryDirectory() as tmp:
            _,_,body=render_editor_report([SourceResult('Tech media',[article()],'ok')],Path(tmp))
        self.assertEqual(post.call_args.args[0],ENDPOINT)
        self.assertIn('代理的程式介面',body)
        self.assertIn('權限與操作紀錄',body)
        self.assertIn('### 8. Ray 的 Podcast 切入角度',body)
        self.assertNotIn('fake-test-only',body)
        self.assertNotIn('事件 ID',body)
        self.assertNotIn('ExampleCo releases an agent API for developers.',body)

    def test_rejects_missing_quotes_invented_numbers_and_bad_schema(self):
        for mutate in (
            lambda d:d['facts'][0].update(evidence='A claim that never appeared in the source'),
            lambda d:d['facts'][0].update(text='報導說效能提升 999%，可直接部署。'),
            lambda d:d.update(ready=False),
            lambda d:d.update(facts=[]),
            lambda d:d.update(opening=None),
            lambda d:d.update(questions=['x']*4)):
            data=copy.deepcopy(response());mutate(data)
            with self.assertRaises(ValueError):validate(data,article())

    def test_transport_failure_never_echoes_secret(self):
        import requests
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fake-test-only'}),patch('src.editor_synthesis.requests.post',side_effect=requests.RequestException('fake-test-only')):
            data,error=synthesize(article())
        self.assertIsNone(data);self.assertNotIn('fake-test-only',error)

    def test_metadata_does_not_call_model_even_when_key_exists(self):
        from dataclasses import replace
        item=replace(article(),quality_hint='metadata')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fake-test-only'}),patch('src.editor_synthesis.requests.post') as post:
            self.assertIsNone(synthesize(item)[0])
        post.assert_not_called()

    def test_metadata_cannot_displace_explainable_news(self):
        item=article();weak=Article('New AI agent architecture launched','https://example.com/weak','Other',None,'',[])
        chosen,_=rank_candidates([SourceResult('Other',[weak,item],'ok')],datetime.now(timezone.utc),[])
        self.assertEqual(chosen[0].url,item.url)

    def test_recovery_batch_renders_once_and_keeps_actual_time_hidden(self):
        from src.slot_runner import process_slots
        from src.weekly_curator import read_markdown
        instant=datetime(2026,10,12,2,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp, \
                patch('src.slot_runner.fetch_sources',return_value=[SourceResult('Tech media',[article()],'ok')]), \
                patch('src.slot_runner.collect_community',return_value=[]), \
                patch('src.slot_runner.render_editor_report',wraps=render_editor_report) as render, \
                patch('src.editor_report.synthesize',return_value=(response(),None)):
            paths=process_slots(Path(tmp),instant,'isolated-test',24)
            self.assertEqual(len(paths),3)
            render.assert_called_once()
            for path in paths:
                text=path.read_text(encoding='utf-8')
                self.assertTrue(text.startswith('<!-- Collected at:'))
                self.assertNotIn('事件 ID',text)
                rows=read_markdown(path,instant)
                self.assertEqual(rows[0].seen,instant)
                self.assertIn('程式介面',rows[0].facts)
