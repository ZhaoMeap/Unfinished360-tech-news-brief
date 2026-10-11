import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts.restore_daily_artifacts import restore_zip
from src.editor_report import render_editor_report
from src.fetch_sources import Article, SourceResult
from src.main import main
from src.render_report import TAIPEI
from src.weekly_curator import load_observations, deduplicate, render_weekly, cluster, same_event

NOW = datetime(2026,10,11,20,tzinfo=TAIPEI)


def article(title='Omniverse simulation with AI agents',url='https://blogs.nvidia.com/test'):
    return Article(title,url,'官方：NVIDIA',NOW.isoformat(),'NVIDIA announced tools connecting physics and rendering and assembling assets. Developers can test scenes with the release.',[],'public summary')


def daily(root,when,item=None):
    render_editor_report([SourceResult('官方：NVIDIA',[item or article()],'ok')],root/'reports',when)


class WeeklyTests(unittest.TestCase):
    def test_read_dedup_stats_and_report_from_sample_daily_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            daily(root,NOW-timedelta(days=2))
            daily(root,NOW-timedelta(days=1))
            daily(root,NOW-timedelta(days=8))
            daily(root,NOW+timedelta(days=1))
            rows,warnings=load_observations(root,NOW)
            self.assertEqual(len(rows),2)
            self.assertEqual(warnings,[])
            self.assertIn('物理模擬', rows[0].facts)
            self.assertNotIn('[Analysis]', rows[0].facts)
            events=deduplicate(rows)
            self.assertEqual(len(events),1)
            self.assertEqual(len(events[0].observations),2)
            self.assertEqual(len(events[0].sources),1)
            self.assertEqual(events[0].first,NOW-timedelta(days=2))
            self.assertEqual(events[0].last,NOW-timedelta(days=1))
            path,subject,body=render_weekly(root,NOW)
            self.assertEqual(path,root/'reports/weekly/2026-W41_weekly.md')
            self.assertEqual(subject,'還沒想到科技週報 - 2026-W41')
            for heading in ('本週科技主線','Podcast 切入角度','下週追蹤清單','代表新聞','仍需查證'):
                self.assertIn(heading,body)
            self.assertIn('出現 2 次',body)
            self.assertIn('來源 1 個',body)
            self.assertIn('[Background]',body)
            self.assertIn('物理模擬',body)
            self.assertIn('[Analysis] Podcast', body)
            self.assertNotIn('網友已經',body)

    def test_json_optional_same_collection_not_double_counted_and_bad_json_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);daily(root,NOW)
            folder=root/'data/daily';folder.mkdir(parents=True)
            payload={'collected_at':NOW.isoformat(),'articles':[article().metadata()]}
            (folder/'2026-10-11_2000.json').write_text(json.dumps(payload), encoding="utf-8")
            (folder/'2026-10-10_0900.json').write_text('{broken', encoding="utf-8")
            rows,warnings=load_observations(root,NOW)
            self.assertEqual(len(rows),1)
            self.assertEqual(len(warnings),1)
            self.assertTrue(rows[0].facts)

    def test_static_daily_sample_keeps_facts_and_actual_community_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'reports/daily';folder.mkdir(parents=True)
            sample = """Subject: sample
## 1. Omniverse simulations with AI agents
- **來源：** [官方：NVIDIA](<https://blogs.nvidia.com/sample>)；2026-10-10；official source / 4。
### 1. 先講人話：這篇新聞在講什麼？
[Confirmed] NVIDIA 提到模擬開發流程。[Analysis] 可能縮短測試時間。
### 5. 網路上的人可能會怎麼看？
[Rumor] Hacker News 抽樣 3 位：整合與可攜性 2 位。樣本不代表共識。
### 7. 仍需查證的地方
- 工具版本。
"""
            fixture = folder/'2026-10-10_0900_editor.md'
            fixture.write_text(sample, encoding="utf-8")
            self.assertEqual(fixture.read_bytes(), sample.encode("utf-8"))
            rows,_=load_observations(root,NOW)
            self.assertEqual(len(rows),1)
            self.assertIn('模擬開發流程',rows[0].facts)
            self.assertNotIn('可能縮短',rows[0].facts)
            self.assertIn('抽樣 3 位',rows[0].social)
            _,_,body=render_weekly(root,NOW)
            self.assertIn('樣本不代表共識',body)

    def test_similar_titles_merge_but_contradictions_do_not(self):
        left=article('NVIDIA launches new Omniverse simulation tools for developers','https://example.com/a')
        right=article('NVIDIA launches new Omniverse simulation tools for developers!','https://example.com/b')
        self.assertTrue(same_event(left,right))
        self.assertFalse(same_event(left,article('NVIDIA stops new Omniverse simulation tools for developers','https://example.com/c')))
        self.assertTrue(same_event(article(url='https://example.com/a?utm_source=x'),article(url='https://example.com/a')))

    def test_related_company_cluster_retains_distinct_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            daily(root,NOW-timedelta(hours=6))
            daily(root,NOW,article('NVIDIA launches new GPU architecture','https://blogs.nvidia.com/gpu'))
            rows,_=load_observations(root,NOW)
            events=deduplicate(rows)
            self.assertEqual(len(events),2)
            self.assertEqual(len(cluster(events)),1)

    def test_weekly_cli_is_offline_and_never_emails(self):
        for args in (['brief','--weekly','--dry-run'],['brief','--weekly','--send-email']):
            with tempfile.TemporaryDirectory() as tmp, patch('src.main.ROOT',Path(tmp)), \
                    patch('src.main.fetch_sources') as fetch,patch('src.main.collect_community') as social, \
                    patch('src.main.send_email') as send,patch('sys.argv',args):
                self.assertEqual(main(),0)
                fetch.assert_not_called();social.assert_not_called();send.assert_not_called()
                path=next((Path(tmp)/'reports/weekly').glob('*.md'))
                self.assertIn('沒有可讀素材',path.read_text(encoding="utf-8"))

    def test_iso_year_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,_,_=render_weekly(Path(tmp),datetime(2027,1,1,tzinfo=TAIPEI))
            self.assertEqual(path.name,'2026-W53_weekly.md')

    def test_artifact_restore_filters_paths_and_restores_only_daily_markdown(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('daily/2026-10-11_0900_editor.md','sample')
            z.writestr('../../secret.txt','should not extract')
            z.writestr('2026-W41_weekly.md','not daily')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(restore_zip(buf.getvalue(),root,123),1)
            self.assertTrue((root/'reports/daily/123_2026-10-11_0900_editor.md').is_file())
            self.assertEqual(len(list(root.rglob('*.*'))),1)

    def test_weekly_workflow_schedule_restore_and_no_smtp(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/weekly-report.yml').read_text(encoding="utf-8")
        for value in ("cron: '0 12 * * 0'",'workflow_dispatch:','actions: read',
                      'restore_daily_artifacts.py','python -m src.main --weekly --dry-run',
                      'reports/weekly/*.md','weekly-tech-report-${{ github.run_id }}','retention-days: 14'):
            self.assertIn(value,text)
        self.assertNotIn('SMTP',text)
        self.assertNotIn('--send-email',text)
