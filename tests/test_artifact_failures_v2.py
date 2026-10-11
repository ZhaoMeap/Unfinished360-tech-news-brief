import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.restore_daily_artifacts import main,restore_zip
from src.weekly_curator import render_weekly
from src.render_report import TAIPEI
from datetime import datetime


class ArtifactFailureTests(unittest.TestCase):
    def test_listing_failure_persists_error_and_raises(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo'}), \
                patch('scripts.restore_daily_artifacts.Path') as paths, \
                patch('scripts.restore_daily_artifacts.subprocess.run',side_effect=subprocess.CalledProcessError(1,['gh'])):
            # ROOT selector only; all status I/O uses real pathlib paths.
            paths.return_value.resolve.return_value.parents=[None,Path(tmp)]
            with self.assertRaises(RuntimeError):main()
            status=json.loads((Path(tmp)/'state/restore_status.json').read_text(encoding='utf-8'))
            self.assertTrue(status['fatal']);self.assertTrue(status['errors'])
            _,_,body=render_weekly(Path(tmp),datetime(2026,10,12,tzinfo=TAIPEI))
            self.assertIn('Partial',body);self.assertIn('Artifact 列表',body)

    def test_invalid_listing_persists_error(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo'}), \
                patch('scripts.restore_daily_artifacts.Path') as paths, \
                patch('scripts.restore_daily_artifacts.subprocess.run',return_value=subprocess.CompletedProcess(['gh'],0,b'broken')):
            paths.return_value.resolve.return_value.parents=[None,Path(tmp)]
            with self.assertRaises(RuntimeError):main()
            status=json.loads((Path(tmp)/'state/restore_status.json').read_text(encoding='utf-8'))
            self.assertTrue(status['fatal'])
            self.assertIn('格式無效',status['errors'][0])

    def test_corrupted_zip_cannot_be_reported_as_restored(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(zipfile.BadZipFile):restore_zip(b'not a zip',Path(tmp),1)

    def test_source_denial_keeps_diagnostics(self):
        import requests
        from src.fetch_sources import fetch_feed
        with patch('src.fetch_sources.download',side_effect=requests.ProxyError if hasattr(requests,'ProxyError') else requests.exceptions.ProxyError):
            result=fetch_feed(None,'Official test','https://example.com/feed',datetime(2026,10,12,tzinfo=TAIPEI))
        self.assertEqual(result.articles,[])
        self.assertIn('ProxyError',result.status)
