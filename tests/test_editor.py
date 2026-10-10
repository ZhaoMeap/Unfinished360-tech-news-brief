import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.community import Discussion
from src.editor_report import render_editor_report, social_summary, topic_for, rank_candidates, score
from src.fetch_sources import Article, SourceResult
from src.main import main
from src.explain_report import explain
from src.story_narrative import describe, financial_numbers, engineering_lens

NOW = datetime(2026, 10, 10, 17, tzinfo=timezone.utc)


def candidates():
    titles = [
        ('DIGITIMES', 'Phison revenue rises as AI sales grow'),
        ('The Verge', 'NVIDIA server GPU supply plans'),
        ('Reuters', 'FTC antitrust case against platform'),
        ('The Verge', 'AI agents and private data privacy'),
        ('官方：Google', 'Clinical research for patient AI assistance'),
        ('DIGITIMES', 'Startup investment funding round'),
        ('The Verge', 'Android phone product launch'),
        ('The Verge', 'Gaming platform changes fees'),
    ]
    return [SourceResult(source, [Article(title, f'https://example.com/{i}', source, NOW.isoformat(),
             'Public description about the topic and its proposed plans for developers.', ['AI'])], 'ok')
            for i, (source, title) in enumerate(titles)]


class EditorTests(unittest.TestCase):
    def test_topic_does_not_invent_ai_or_privacy_connection(self):
        def item(title):
            return Article(title,'https://example.com','Media',None,'',[])
        self.assertEqual(topic_for(item('Huawei price reset as memory costs surge')).name, '記憶體成本與裝置定價')
        self.assertEqual(topic_for(item('Omniverse simulations with AI agents')).name, 'AI 模擬與開發流程')
        self.assertEqual(topic_for(item('AI agent workflow automation')).name, 'AI 代理與工作流程')
        medal = Article('Trump awards science medal to Jensen Huang','https://example.com','Media',None,'NVIDIA semiconductor chips and AI servers',['半導體'])
        self.assertEqual(topic_for(medal).name,'科技人物與榮譽')

    def test_three_runs_have_distinct_taipei_time_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for hour, expected in ((1, '0900'), (7, '1500'), (13, '2100')):
                instant = datetime(2026, 10, 11, hour, tzinfo=timezone.utc)
                path, _, _ = render_editor_report(candidates(), Path(tmp), instant)
                self.assertEqual(path.name, f'2026-10-11_{expected}_editor.md')
                self.assertEqual(path.parent, Path(tmp) / 'daily')
                paths.append(path)
            self.assertEqual(len(set(paths)), 3)
            self.assertTrue(all(path.is_file() for path in paths))

    def test_full_report_format_timezone_and_other_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, subject, body = render_editor_report(candidates(), Path(tmp), NOW)
            self.assertEqual(path.name, '2026-10-11_0100_editor.md')
            self.assertEqual(path.parent, Path(tmp) / 'daily')
            self.assertEqual(subject, '還沒想到科技編輯簡報 - 2026/10/11')
            self.assertEqual(path.read_text(), body)
        for heading in ('今日科技主線', '今天最值得追的 3 則新聞', '其他候選新聞', '今日資料缺口', 'Ray 今天可以怎麼用'):
            self.assertIn('# ' + heading, body)
        for heading in ('1. 先講人話：這篇新聞在講什麼？', '2. 背景補充：工程小白需要先懂什麼？',
                        '3. 工程師應該注意什麼？', '4. 目前可能的解法或業界方向',
                        '5. 網路上的人可能會怎麼看？', '6. Ray 的 Podcast 切入角度', '7. 仍需查證的地方'):
            self.assertEqual(body.count('### ' + heading), 3)
        for field in ('來源','來源連結','可信度標籤'):
            self.assertEqual(body.count('**' + field + '：**'), 3)
        thread = body.split('# 今日科技主線\n')[1].split('# 今天最值得追')[0]
        self.assertEqual(thread.count('[Analysis]'), 4)
        other = body.split('# 其他候選新聞\n')[1].split('# 今日資料缺口')[0]
        self.assertEqual(other.count('- [Analysis] 觀察：'), 5)
        self.assertIn('metadata 不等於事件已確認', body)
        self.assertNotIn('毛利率', body)
        self.assertNotIn('法說指引', body)
        self.assertNotIn('待人工補充', body)

    def test_explain_background_is_separate_and_gaps_are_last(self):
        item = Article('Omniverse simulations with AI agents', 'https://blogs.nvidia.com/test',
                       '官方：NVIDIA', NOW.isoformat(), 'Connecting physics and rendering.', [])
        explanation = explain(item, topic_for(item), 'Confirmed')
        self.assertTrue(5 <= len(explanation['sentences']) <= 8)
        self.assertTrue(explanation['sentences'][0].startswith('[Confirmed]'))
        for word in ('資料不足', '合法閱讀', '來源未提供'):
            self.assertNotIn(word, ' '.join(explanation['sentences']))
        self.assertIn('物理模擬', ' '.join(explanation['background']))
        self.assertIn('渲染', ' '.join(explanation['background']))
        self.assertIn('一般工程方向', explanation['solution'])
        self.assertEqual(len(explanation['questions']), 3)
        with tempfile.TemporaryDirectory() as tmp:
            _, _, body = render_editor_report([SourceResult(item.source, [item], 'ok')], Path(tmp), NOW)
        self.assertIn('[Background]', body)
        self.assertIn('不是實際網友發言', body)
        story = body.split('\n## 1.')[1].split('\n# 其他候選新聞')[0]
        self.assertLess(story.index('背景補充'), story.index('仍需查證'))
        self.assertNotIn('合法閱讀', story)
        self.assertEqual(body.count('完整文章如需補查'), 1)

    def test_explain_evaluation_and_clinical_context_not_news_facts(self):
        for title, term in (('Anthropic is cutting off its internal evaluations from the internet', '資料污染'),
                            ('Study in The Lancet suggests AI could improve patient-physician relationships.', '對照組')):
            item = Article(title, 'https://example.com/x', 'The Verge', NOW.isoformat(), '', [])
            explanation = explain(item, topic_for(item), 'Reported')
            self.assertIn(term, ' '.join(explanation['background']))
            self.assertTrue(any(s.startswith('[Reported]') for s in explanation['sentences']))
            self.assertNotIn('[Confirmed]', ' '.join(explanation['sentences']))
            self.assertIn('不是', explanation['solution'])

    def test_engineering_ranking_deprioritizes_finance_even_with_ai_tags(self):
        rows = candidates() + [SourceResult('DIGITIMES', [Article('TPCA Show AI computing keynote', 'https://example.com/event', 'DIGITIMES', NOW.isoformat(), 'New features for server chip architecture at the event.', ['AI'])], 'ok'), SourceResult('官方：Google', [Article('Play Fest prizes and daily deals', 'https://example.com/promo', '官方：Google', NOW.isoformat(), 'Gaming leagues and rewards.', ['AI'])], 'ok'), SourceResult('官方：NVIDIA', [Article(
            'Omniverse simulation with AI agents', 'https://blogs.nvidia.com/new',
            '官方：NVIDIA', NOW.isoformat(), 'Connecting physics and rendering.', ['AI'])], 'ok')]
        chosen, others = rank_candidates(rows, NOW, [])
        self.assertTrue(any('simulation' in a.title for a in chosen))
        self.assertFalse(any('revenue' in a.title or 'funding' in a.title or 'Play Fest' in a.title or 'keynote' in a.title for a in chosen))
        finance = rows[0].articles[0]
        self.assertTrue(all(score(a, NOW, []) > score(finance, NOW, []) for a in chosen))

    def test_engineering_limits_and_solutions_do_not_invent_evidence(self):
        article = Article('Omniverse simulation with AI agents', 'https://example.com/a',
                          'Media', NOW.isoformat(), 'Connecting physics and rendering.', [])
        lens = engineering_lens(article, topic_for(article))
        self.assertIn('來源未提供', lens['limits'])
        self.assertIn('實體測試', lens['limits'])
        self.assertIn('可重跑', lens['attention'])
        self.assertIn('[Reported]', lens['solution'])
        self.assertIn('尚缺', lens['solution'])
        evaluation = Article('Anthropic is cutting off its internal evaluations from the internet', 'https://example.com/eval', 'The Verge', NOW.isoformat(), 'AI agents being evaluated.', [])
        self.assertEqual(topic_for(evaluation).name, 'AI 評測與可靠性')
        self.assertIn('測試環境', ' '.join(describe(evaluation, topic_for(evaluation))['sentences']))
        self.assertIn('網際網路隔開', engineering_lens(evaluation, topic_for(evaluation))['solution'])
        unknown = Article('An unexplained topic', 'https://example.com/b', 'Media', None, '', [])
        self.assertIn('目前只看到問題，還沒有看到明確解法', engineering_lens(unknown, topic_for(unknown))['solution'])
        self.assertIn('沒有取得對應', social_summary(article, []))
        unrelated = Discussion('Hacker News', 'https://news.ycombinator.com/item?id=1',
                               'Other', target_url='https://example.com/unrelated', sampled=3, themes={'替代方案': 3})
        self.assertNotIn('替代方案', social_summary(article, [unrelated]))

    def test_revenue_story_preserves_amount_metric_period_and_qualifiers(self):
        article = Article('Zhen Ding posts record September sales on mobile demand and AI applications',
                          'https://example.com/news','DIGITIMES',NOW.isoformat(),
                          'Zhen Ding said September 2026 consolidated revenue reached NT$26.358 billion, up 36.13% year over year and 27.54% from August.', ['AI'])
        story = describe(article,topic_for(article))
        text = ' '.join(story['sentences'])
        self.assertGreaterEqual(len(story['sentences']),5)
        self.assertLessEqual(len(story['sentences']),8)
        import re
        self.assertLessEqual(len(re.findall(r'[。！？]',text)),8)
        for fact in ('臻鼎','2026年9月','新台幣263.58億元','去年同期增加36.13%','較8月增加27.54%'):
            self.assertIn(fact,text)
        self.assertIn('尚未核對',text)
        self.assertIn('毛利率',story['important'])
        self.assertIn('目前沒有直接證據',story['taiwan'])
        self.assertIn('目前資料不足，不能判斷',story['big'])

    def test_simulation_explains_actual_steps_and_not_unreported_functions(self):
        article = Article('Omniverse: ideas into simulations with AI agents','https://blogs.nvidia.com/example',
                          '官方：NVIDIA',NOW.isoformat(),
                          'Turning ideas into applications requires assembling assets, connecting physics and rendering, and checking that the scene behaves as intended.', ['AI'])
        story=describe(article,topic_for(article))
        text=' '.join(story['sentences'])
        for step in ('場景素材','物理模擬','畫面渲染','場景是否按預期運作'):
            self.assertIn(step,text)
        self.assertIn('Omniverse',text)
        self.assertIn('NVIDIA',text)
        self.assertIn('NVIDIA',story['big'])
        self.assertNotIn('加速50%',text)
        self.assertIn('目前沒有直接證據',story['taiwan'])

    def test_agent_story_names_source_product_and_separates_permission_analysis(self):
        article=Article('AI agent makers are promising privacy — will they deliver?', 'https://example.com/news','The Verge',NOW.isoformat(),
                        "At OpenAI DevDay, CEO Sam Altman unveiled the company's new AI agent Dots.", ['AI'])
        story=describe(article,topic_for(article))
        text=' '.join(story['sentences'])
        for fact in ('OpenAI','Dots','Sam Altman','DevDay','隱私承諾'):
            self.assertIn(fact,text)
        self.assertNotIn('讀取email',text)
        self.assertIn('如果',story['important'])
        self.assertIn('email',story['important'])
        self.assertIn('操作紀錄',story['big'])
        self.assertEqual(story['opening'].count('？'),1)
        self.assertEqual(story['opening'].count('。'),1)

    def test_missing_summary_does_not_invent_actor_numbers_or_customers(self):
        article=Article('A new technology changes things','https://example.com/20261010','Media',None,'',[])
        story=describe(article,topic_for(article))
        self.assertIn('目前只有標題',' '.join(story['sentences']))
        self.assertIn('未提供',' '.join(story['sentences']))
        self.assertIn('來源未具名',' '.join(story['sentences']))
        self.assertNotIn('20261010',' '.join(story['sentences']))
        self.assertIn('目前資料不足，不能判斷',story['big'])
        self.assertIn('目前沒有直接證據',story['taiwan'])
        self.assertEqual(financial_numbers('Model version 26.358; URL https://example.com/36313'),[])
        self.assertIn('較8月減少5%',financial_numbers('revenue down 5% from August'))
        self.assertEqual(financial_numbers('Revenue 5% from August'),['較8月變動5%（摘錄未明示方向）'])

    def test_empty_sources_not_fabricated_and_failures_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, body = render_editor_report([SourceResult('Reuters', [], '目前無法取得（HTTP 401）')], Path(tmp), NOW)
        self.assertIn('HTTP 401', body)
        self.assertIn('沒有可用新聞', body)
        self.assertIn('目前沒有足夠公開資訊', body)
        self.assertNotIn('## 1.', body)

    def test_title_only_official_not_confirmed_or_recommended_for_news(self):
        item = Article('NVIDIA server chip plans', 'https://blogs.nvidia.com/test', '官方：NVIDIA', NOW.isoformat(), '', ['半導體'])
        with tempfile.TemporaryDirectory() as tmp:
            _, _, body = render_editor_report([SourceResult(item.source, [item], 'ok')], Path(tmp), NOW)
        self.assertNotIn('**可信度標籤：** [Confirmed]', body)
        self.assertIn('title only', body)
        self.assertIn('目前沒有足夠公開資訊', body)
        self.assertIn('可重現測試', body)

    def test_social_only_exact_url_and_no_consensus(self):
        article = candidates()[0].articles[0]
        discussion = Discussion('Hacker News', 'https://news.ycombinator.com/item?id=1', 'Similar title',
                                target_url='https://example.com/other', sampled=6, themes={'成本': 5})
        self.assertNotIn('成本 5', social_summary(article, [discussion]))
        discussion.target_url = article.url
        summary = social_summary(article, [discussion])
        self.assertIn('[Rumor]', summary)
        self.assertIn('抽樣 6 位', summary)
        self.assertIn('樣本不代表共識', summary)

    def test_editor_cli_generates_report_no_email_and_preserves_radar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'reports').mkdir()
            radar = root / 'reports' / 'existing-radar.md'
            radar.write_text('existing report')
            with patch('src.main.ROOT', root), patch('src.main.fetch_sources', return_value=candidates()), \
                    patch('src.main.collect_community', return_value=[]), patch('src.main.send_email') as send, \
                    patch('sys.argv', ['brief', '--dry-run', '--editor']):
                self.assertEqual(main(), 0)
                send.assert_not_called()
            report = next((root / 'reports').glob('daily/*_editor.md'))
            self.assertIn('還沒想到科技編輯簡報', report.read_text())
            self.assertEqual(radar.read_text(), 'existing report')

    def test_editor_never_sends_even_with_send_email_and_smtp_config(self):
        import os
        settings = {'SMTP_HOST': 'smtp.example.com', 'SMTP_PORT': '587', 'SMTP_USER': 'mock-user',
                    'SMTP_PASS': 'mock-password', 'MAIL_FROM': 'mock@example.com', 'MAIL_TO': 'mock@example.com'}
        for args in (['brief', '--editor'], ['brief', '--editor', '--send-email']):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as tmp, \
                    patch('src.main.ROOT', Path(tmp)), patch('src.main.fetch_sources', return_value=candidates()), \
                    patch('src.main.collect_community', return_value=[]), patch.dict(os.environ, settings), \
                    patch('src.main.send_email') as send, patch('sys.argv', args):
                self.assertEqual(main(), 0)
                send.assert_not_called()
                self.assertEqual(len(list((Path(tmp) / 'reports').glob('daily/*_editor.md'))), 1)


if __name__ == '__main__':
    unittest.main()
