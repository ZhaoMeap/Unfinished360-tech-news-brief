import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.community import Discussion
from src.editor_report import render_editor_report, social_summary, topic_for
from src.fetch_sources import Article, SourceResult
from src.main import main

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

    def test_full_report_format_timezone_and_other_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, subject, body = render_editor_report(candidates(), Path(tmp), NOW)
            self.assertEqual(path.name, '2026-10-11_editor.md')
            self.assertEqual(subject, '還沒想到科技編輯簡報 - 2026/10/11')
            self.assertEqual(path.read_text(), body)
        for heading in ('今日科技主線', '今天最值得追的 3 則新聞', '其他候選新聞', '今日資料缺口', 'Ray 今天可以怎麼用'):
            self.assertIn('# ' + heading, body)
        for field in ('為什麼值得看', '目前我們知道什麼', '目前不知道什麼', 'Big Tech 影響',
                      '台灣科技業 / 半導體 / AI server 可能關聯', '社群回響摘要', 'Ray 的 Podcast 切入角度',
                      '建議後續補查來源', '可信度標籤'):
            self.assertEqual(body.count('**' + field + '：**'), 3)
        thread = body.split('# 今日科技主線\n')[1].split('# 今天最值得追')[0]
        self.assertEqual(thread.count('[Analysis]'), 4)
        other = body.split('# 其他候選新聞\n')[1].split('# 今日資料缺口')[0]
        self.assertEqual(other.count('- [Analysis] 觀察：'), 5)
        self.assertIn('metadata 不等於事件已確認', body)
        self.assertIn('需要公司財報原文', body)
        self.assertNotIn('待人工補充', body)

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
        self.assertNotIn('[Confirmed]', body)
        self.assertIn('title only', body)
        self.assertIn('目前沒有足夠公開資訊', body)
        self.assertIn('需要官方 press release', body)

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
            report = next((root / 'reports').glob('*_editor.md'))
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
                self.assertEqual(len(list((Path(tmp) / 'reports').glob('*_editor.md'))), 1)


if __name__ == '__main__':
    unittest.main()
