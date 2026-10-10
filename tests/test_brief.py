import os
import smtplib
import ssl
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, sentinel

import requests

from src.fetch_sources import Article, SourceResult, fetch_feed, fetch_x
from src.render_report import render_report, select_news
from src.send_email import send_email
from src.main import main

NOW = datetime(2026, 10, 10, 17, tzinfo=timezone.utc)


def article(source="Reuters", title="Microsoft AI server chip project announced", url="https://example.com/story"):
    return Article(title, url, source, NOW.isoformat(), "", ["AI", "半導體"])


class FetchTests(unittest.TestCase):
    def test_feed_filters_old_and_undated_and_bounds_metadata(self):
        feed = b'''<rss version="2.0"><channel><title>Test</title>
        <item><title>Microsoft AI chip announcement</title><link>https://example.com/new</link>
        <pubDate>Sat, 10 Oct 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;AI chip news&lt;/p&gt;</description></item>
        <item><title>AI old news</title><link>https://example.com/old</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate></item>
        <item><title>AI undated</title><link>https://example.com/undated</link></item>
        </channel></rss>'''
        with patch("src.fetch_sources.download", return_value=feed):
            result = fetch_feed(MagicMock(), "Reuters", "https://example.com/feed", NOW)
        self.assertEqual(len(result.articles), 1)
        self.assertEqual(result.articles[0].short_snippet, "AI chip news")
        self.assertEqual(set(result.articles[0].metadata()), {"title", "url", "source", "published_at", "short_snippet", "tags"})

    def test_source_denial_and_x_are_explicit(self):
        response = requests.Response()
        response.status_code = 403
        with patch("src.fetch_sources.download", side_effect=requests.HTTPError(response=response)):
            result = fetch_feed(MagicMock(), "Reddit", "https://example.com/feed", NOW)
        self.assertIn("目前無法取得", result.status)
        self.assertIn("403", result.status)
        self.assertEqual(result.articles, [])
        self.assertEqual(fetch_x().articles, [])

    def test_primary_link_kept_without_exceeding_metadata_limit(self):
        feed = b'''<rss version="2.0"><channel><title>Test</title><item>
        <title>Microsoft AI chip announcement</title><link>https://example.com/new</link>
        <pubDate>Sat, 10 Oct 2026 10:00:00 GMT</pubDate>
        <description>&lt;a href="https://blogs.microsoft.com/announcement"&gt;Official announcement&lt;/a&gt;</description>
        </item></channel></rss>'''
        with patch("src.fetch_sources.download", return_value=feed):
            result = fetch_feed(MagicMock(), "Reuters", "https://example.com/feed", NOW)
        self.assertIn("https://blogs.microsoft.com/announcement", result.articles[0].short_snippet)
        self.assertLessEqual(len(result.articles[0].short_snippet), 160)


class ReportTests(unittest.TestCase):
    def test_reuters_first_dedup_and_social_never_selected(self):
        results = [SourceResult("Hacker News", [article("Hacker News")], "ok"),
                   SourceResult("The Verge", [article("The Verge", url="https://example.com/copy")], "ok"),
                   SourceResult("Reuters", [article()], "ok")]
        selected = select_news(results)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].source, "Reuters")

    def test_timezone_and_missing_slots_and_no_false_confirmation(self):
        results = [SourceResult("Reuters", [article()], "ok"), SourceResult("X", [], "目前無法取得")]
        with tempfile.TemporaryDirectory() as tmp:
            path, subject, body = render_report(results, Path(tmp), NOW)
            self.assertEqual(path.name, "2026-10-11.md")
            self.assertEqual(subject, "科技新聞候選雷達 - 2026/10/11")
            self.assertEqual(path.read_text(encoding="utf-8"), body)
        self.assertIn("candidate discovery", body)
        self.assertIn("可用資訊程度：低", body)
        self.assertNotIn("5 秒版", body)

    def test_official_only_confirmed_and_similarity_not_confirmation(self):
        official = Article("Microsoft AI server chip project announced", "https://blogs.microsoft.com/story", "官方：Microsoft",
                           NOW.isoformat(), "Microsoft announces a new AI server chip platform for developers.", ["AI"])
        with tempfile.TemporaryDirectory() as tmp:
            _, _, body = render_report([SourceResult("official", [official], "ok")], Path(tmp), NOW, mode="links")
            self.assertIn("可信度：[Confirmed]", body)
            _, _, body = render_report([SourceResult("Reuters", [article()], "ok"),
                                       SourceResult("官方：Microsoft", [official], "ok")], Path(tmp), NOW, mode="links")
            self.assertIn("相似標題不代表交叉確認", body)
            self.assertIn("可信度：[Reported]", body)

    def test_empty_report_and_cli_default_do_not_send(self):
        with tempfile.TemporaryDirectory() as tmp, patch("src.main.ROOT", Path(tmp)), \
                patch("src.main.fetch_sources", return_value=[]), patch("src.main.send_email") as send, \
                patch("sys.argv", ["brief"]):
            self.assertEqual(main(), 0)
            send.assert_not_called()
            report = next((Path(tmp) / "reports").glob("*.md"))
            self.assertIn("目前沒有可用的新聞候選", report.read_text(encoding="utf-8"))

    def test_send_mode_missing_config_preserves_report_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp, patch("src.main.ROOT", Path(tmp)), \
                patch("src.main.fetch_sources", return_value=[]), patch.dict(os.environ, {}, clear=True), \
                patch("sys.argv", ["brief", "--send-email"]), patch("src.send_email.smtplib.SMTP") as smtp:
            self.assertEqual(main(), 1)
            self.assertEqual(len(list((Path(tmp) / "reports").glob("*.md"))), 2)
            smtp.assert_not_called()


class EmailTests(unittest.TestCase):
    config = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USER": "user",
              "SMTP_PASS": "not-real", "MAIL_FROM": "sender@example.com", "MAIL_TO": "receiver@example.com"}

    def setUp(self):
        # Windows certificate-store initialization depends on the host environment.
        # These are transport unit tests, so inject a context instead of loading it.
        context = patch("src.send_email.ssl.create_default_context", return_value=sentinel.tls_context)
        self.context_factory = context.start()
        self.addCleanup(context.stop)
        # No test may fall through to a real transport, including alternate ports.
        for name in ("SMTP", "SMTP_SSL"):
            guard = patch("src.send_email.smtplib." + name,
                          side_effect=AssertionError("Unexpected real SMTP connection"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_missing_and_invalid_settings_never_connect(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.send_email.smtplib.SMTP") as smtp:
            self.assertFalse(send_email("subject", "body"))
            smtp.assert_not_called()
        with patch.dict(os.environ, {**self.config, "SMTP_PORT": "invalid"}, clear=True):
            self.assertFalse(send_email("subject", "body"))

    def test_starttls_before_login_and_send(self):
        with patch.dict(os.environ, self.config, clear=True), patch("src.send_email.smtplib.SMTP") as factory:
            smtp = factory.return_value.__enter__.return_value
            self.assertTrue(send_email("還沒想到科技快報", "test body"))
            names = [call[0] for call in smtp.method_calls]
            smtp.starttls.assert_called_once_with(context=sentinel.tls_context)
            self.assertLess(names.index("starttls"), names.index("login"))
            self.assertLess(names.index("login"), names.index("send_message"))
            message = smtp.send_message.call_args.args[0]
            self.assertIn("test body", message.get_content())

    def test_ssl_and_transport_failure(self):
        with patch.dict(os.environ, {**self.config, "SMTP_PORT": "465"}, clear=True), \
                patch("src.send_email.smtplib.SMTP_SSL") as factory:
            self.assertTrue(send_email("subject", "body"))
            factory.return_value.__enter__.return_value.starttls.assert_not_called()
            self.assertIs(factory.call_args.kwargs["context"], sentinel.tls_context)
            smtp = factory.return_value.__enter__.return_value
            smtp.login.assert_called_once_with("user", "not-real")
            smtp.send_message.assert_called_once()
        with patch.dict(os.environ, self.config, clear=True), \
                patch("src.send_email.smtplib.SMTP", side_effect=smtplib.SMTPAuthenticationError(535, b"secret response")):
            self.assertFalse(send_email("subject", "body"))
    def test_tls_context_failure_is_safe_and_never_connects(self):
        with patch.dict(os.environ, self.config, clear=True), \
                patch("src.send_email.ssl.create_default_context", side_effect=ssl.SSLError("mock TLS failure")), \
                patch("src.send_email.smtplib.SMTP") as plain, \
                patch("src.send_email.smtplib.SMTP_SSL") as secure:
            self.assertFalse(send_email("subject", "body"))
            plain.assert_not_called()
            secure.assert_not_called()

    def test_starttls_failure_never_logs_in_or_sends(self):
        with patch.dict(os.environ, self.config, clear=True), \
                patch("src.send_email.smtplib.SMTP") as factory:
            smtp = factory.return_value.__enter__.return_value
            smtp.starttls.side_effect = ssl.SSLError("mock handshake failure")
            self.assertFalse(send_email("subject", "body"))
            smtp.login.assert_not_called()
            smtp.send_message.assert_not_called()



if __name__ == "__main__":
    unittest.main()
