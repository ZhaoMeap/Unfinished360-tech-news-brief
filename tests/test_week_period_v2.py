import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from src.render_report import TAIPEI
from src.scheduling import week_period
from src.weekly_curator import render_weekly


class WeekPeriodTests(unittest.TestCase):
    def test_sunday_to_monday_and_explicit_week(self):
        self.assertEqual(week_period(datetime(2026,10,12,1,tzinfo=TAIPEI))[0],'2026-W41')
        self.assertEqual(week_period(datetime(2027,1,4,1,tzinfo=TAIPEI))[0],'2026-W53')
        self.assertEqual(week_period(datetime(2026,10,12,tzinfo=TAIPEI),'2026-W40')[0],'2026-W40')

    def test_no_ledger_is_explicit_partial_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,_,body=render_weekly(Path(tmp),datetime(2026,10,12,tzinfo=TAIPEI))
        self.assertIn('Partial',body)
        self.assertIn('Expected 21',body)
        self.assertIn('Completed 0',body)
