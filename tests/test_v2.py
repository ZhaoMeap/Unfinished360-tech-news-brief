import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.community import Discussion, canonical, hn_discussion, reddit_discussion, summarize_comments
from src.fetch_links import HEAD_LIMIT, download_head, fetch_links, parse_head, read_links, validate_public_url
from src.fetch_sources import Article, SourceResult
from src.fetch_sources import fetch_feed
from src.render_report import community_view, render_report
from src.source_quality import quality_for
from src.main import main


class LinksTests(unittest.TestCase):
    def test_parse_metadata_and_public_summary_without_body(self):
        head = b'''<head><title>OpenAI launches developer tools</title>
        <meta name="description" content="OpenAI introduces an API platform for developers with new tools.">
        <meta property="article:published_time" content="2026-10-10T10:00:00Z">
        <script type="application/ld+json">{"@type":"NewsArticle","description":"OpenAI launches tools for API deployment and testing.","articleBody":"SECRET FULL ARTICLE DO NOT READ"}</script></head>'''
        a = parse_head(head, 'https://example.com/story')
        self.assertNotIn('SECRET', a.short_snippet)
        self.assertEqual(a.quality_hint, 'public summary')
        self.assertEqual(a.published_at, '2026-10-10T10:00:00+00:00')
        self.assertEqual(len(a.metadata()), 6)

    def test_paid_structured_description_not_extracted(self):
        a = parse_head(b'''<title>News</title><script type="application/ld+json">{"@type":"NewsArticle","isAccessibleForFree":false,"description":"Paid summary", "articleBody":"Paid body"}</script>''', 'https://example.com')
        self.assertEqual(a.short_snippet, '')
        self.assertIsNone(a.published_at)

    def test_stream_stops_at_head_and_does_not_consume_body(self):
        consumed = []
        def chunks(*args):
            consumed.append('head')
            yield b'<html><head><title>News</title></head>'
            consumed.append('body')
            yield b'<body>FULL ARTICLE</body>'
        response = MagicMock()
        response.status_code = 200
        response.headers = {'Content-Type': 'text/html'}
        response.iter_content.side_effect = chunks
        session = MagicMock()
        session.get.return_value.__enter__.return_value = response
        with patch('src.fetch_links.validate_public_url', side_effect=lambda url: url):
            data, _ = download_head(session, 'https://example.com')
        self.assertEqual(consumed, ['head'])
        self.assertNotIn(b'FULL ARTICLE', data)
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    def test_invalid_private_and_redirect_urls_blocked(self):
        for url in ('http://example.com', 'https://user:pass@example.com', 'https://localhost', 'https://127.0.0.1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_public_url(url)
        response = MagicMock(status_code=302)
        response.headers = {'Location': 'http://example.com'}
        session = MagicMock()
        session.get.return_value.__enter__.return_value = response
        with patch('src.fetch_links.socket.getaddrinfo', return_value=[(0,0,0,'',('93.184.216.34',443))]):
            with self.assertRaises(ValueError):
                download_head(session, 'https://example.com')
        self.assertEqual(session.get.call_count, 1)

    def test_cloud_proxy_dns_and_direct_private_dns(self):
        with patch('src.fetch_links.requests.utils.get_environ_proxies',return_value={'https':'https://proxy.example'}), \
                patch('src.fetch_links.socket.getaddrinfo') as resolver:
            self.assertEqual(validate_public_url('https://example.com'),'https://example.com')
            resolver.assert_not_called()
        with patch('src.fetch_links.requests.utils.get_environ_proxies',return_value={}), \
                patch('src.fetch_links.socket.getaddrinfo',return_value=[(0,0,0,'',('10.0.0.2',443))]):
            with self.assertRaises(ValueError):
                validate_public_url('https://example.com')

    def test_large_head_is_bounded_and_partial_metadata_usable(self):
        response=MagicMock(status_code=206)
        response.headers={'Content-Type':'text/html'}
        response.iter_content.return_value=iter([b'<head><title>AI news</title>',b' ' * HEAD_LIMIT,b'<body>FULL ARTICLE'])
        session=MagicMock()
        session.get.return_value.__enter__.return_value=response
        with patch('src.fetch_links.validate_public_url',side_effect=lambda url:url):
            data,url=download_head(session,'https://example.com')
        self.assertEqual(len(data),HEAD_LIMIT)
        self.assertNotIn(b'FULL ARTICLE',data)
        self.assertEqual(parse_head(data,url).title,'AI news')

    def test_read_links_dedup_and_error_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'links.txt'
            path.write_text('# comment\nhttps://example.com\nhttps://example.com\n')
            self.assertEqual(read_links(path), ['https://example.com'])
            path.write_text('http://example.com')
            with self.assertRaises(ValueError):
                read_links(path)
        with patch('src.fetch_links.download_head', side_effect=requests.Timeout):
            results = fetch_links(['https://example.com/news'])
        self.assertIn('待人工補充', results[0].status)
        self.assertEqual(results[0].articles[0].url, 'https://example.com/news')


class QualityReportTests(unittest.TestCase):
    def test_all_quality_categories_and_title_only_official_is_low(self):
        def a(source='Media', snippet='', hint='', url='https://example.com'):
            return Article('News',url,source,None,snippet,[],hint)
        self.assertEqual(quality_for(a()).kind, 'title only')
        self.assertEqual(quality_for(a(snippet='Description')).score, 2)
        self.assertEqual(quality_for(a(snippet='Summary', hint='public summary')).score, 3)
        self.assertEqual(quality_for(a('官方：Google', 'Summary',url='https://blog.google')).availability, '高')
        self.assertEqual(quality_for(a('官方：Google',url='https://blog.google')).availability, '低')
        self.assertEqual(quality_for(a('Reddit', 'A discussion')).kind, 'community discussion')

    def test_link_report_and_radar_copy_and_missing_information(self):
        article = Article('Title only', 'https://example.com','Media',None,'',[])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            path, subject, body = render_report([SourceResult('Media',[article],'ok')],output)
            radar = output / (path.stem + '-radar.md')
            self.assertTrue(radar.exists())
            _, subject, body = render_report([SourceResult('Media',[article],'ok')],output,mode='links')
            self.assertTrue(subject.startswith('還沒想到科技快報'))
            self.assertIn('待人工補充',body)
            self.assertNotIn('**5 秒版',body)
            self.assertIn('科技新聞候選雷達',radar.read_text())

    def test_links_cli_never_fetches_automatic_news_or_sends(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'links.txt'
            p.write_text('https://example.com')
            with patch('src.main.ROOT',Path(tmp)), patch('src.main.fetch_links',return_value=[]) as fetch, \
                    patch('src.main.fetch_sources') as auto, patch('src.main.collect_community',return_value=[]), \
                    patch('src.main.send_email') as send, patch('sys.argv',['brief','--dry-run','--links',str(p)]):
                self.assertEqual(main(),0)
                fetch.assert_called_once_with(['https://example.com'])
                auto.assert_not_called()
                send.assert_not_called()


class CommunityTests(unittest.TestCase):
    def test_hn_rss_keeps_discussion_id_and_query_identity(self):
        from datetime import datetime, timezone
        feed = b'''<rss version="2.0"><channel><title>HN</title><item>
        <title>AI agent API deployment</title><link>https://example.com/article</link>
        <comments>https://news.ycombinator.com/item?id=123</comments>
        <pubDate>Sat, 10 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'''
        with patch('src.fetch_sources.download',return_value=feed):
            result=fetch_feed(MagicMock(),'Hacker News','https://hnrss.org/frontpage',datetime(2026,10,10,12,tzinfo=timezone.utc))
        self.assertEqual(result.articles[0].url,'https://news.ycombinator.com/item?id=123')
        self.assertNotEqual(canonical('https://news.ycombinator.com/item?id=123'),canonical('https://news.ycombinator.com/item?id=124'))
        self.assertEqual(canonical('https://example.com?a=1&utm_source=feed'),canonical('https://example.com?a=1'))

    def test_sample_unique_authors_concerns_and_technical_no_fake_consensus(self):
        discussion = summarize_comments(Discussion('HN','https://example.com','Title',total=4),[
            ('a','I worry about privacy and API deployment security.'),
            ('a','Privacy privacy privacy'),
            ('b','Privacy is a concern with this API.'),
            ('c','The benchmark performance looks interesting.')])
        self.assertEqual(discussion.sampled,3)
        self.assertEqual(discussion.concerns['隱私與資料使用'],2)
        view=community_view(discussion)
        self.assertIn('少量討論',view['size'])
        self.assertIn('隱私',view['concerns'])
        self.assertIn('效能',view['engineers'])
        self.assertFalse(hasattr(discussion,'comments'))

    def test_hn_api_deleted_comments_excluded(self):
        a=Article('AI story','https://news.ycombinator.com/item?id=123','Hacker News',None,'',[])
        with patch('src.community.json_get',side_effect=[{'type':'story','url':'https://example.com','descendants':20,'kids':[1,2]},
                    {'type':'comment','by':'a','text':'API deployment cost is a concern'}, {'type':'comment','deleted':True}]):
            d=hn_discussion(MagicMock(),a)
        self.assertEqual(d.sampled,1)
        self.assertEqual(d.total,20)
        self.assertEqual(d.target_url,'https://example.com')
        self.assertIn('不足兩位',community_view(d)['concerns'])

    def test_reddit_submission_not_counted_as_comment_and_failure_safe(self):
        a=Article('Story','https://www.reddit.com/r/technology/comments/abc/title/','Reddit',None,'',[])
        parsed=MagicMock(entries=[{'link':a.url,'author':'poster','summary':'privacy'},
            {'link':a.url+'def/','author':'commenter','summary':'API cost is expensive'}])
        with patch('src.community.download',return_value=b'feed'),patch('src.community.feedparser.parse',return_value=parsed):
            d=reddit_discussion(MagicMock(),a)
        self.assertEqual(d.sampled,1)
        with patch('src.community.download',side_effect=requests.Timeout):
            d=reddit_discussion(MagicMock(),a)
        self.assertIn('待人工補充',d.status)


if __name__ == '__main__':
    unittest.main()
