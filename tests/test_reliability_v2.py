import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts.history_store import HistoryStore
from src.render_report import TAIPEI
from src.scheduling import week_period,daily_slots,read_ledger,write_ledger,due_slots,claim,completeness,slot_id
from src.slot_runner import process_slots
from src.fetch_sources import Article,SourceResult
from src.weekly_curator import render_weekly,load_observations

NOW=datetime(2026,10,12,10,tzinfo=TAIPEI)


def source():
    a=Article('NVIDIA announced simulation tools','https://blogs.nvidia.com/test','官方：NVIDIA',NOW.isoformat(),
              'NVIDIA announced simulation tools for developers. The release describes physics and rendering tests for scenes.',[],'public summary')
    return [SourceResult(a.source,[a],'ok')]


class ReliabilityTests(unittest.TestCase):
    def test_delayed_sunday_keeps_intended_iso_week(self):
        for now in (datetime(2026,10,11,20,tzinfo=TAIPEI),datetime(2026,10,12,2,tzinfo=TAIPEI)):
            week,start,end=week_period(now)
            self.assertEqual(week,'2026-W41')
            self.assertEqual(start.day,5);self.assertEqual(end.day,12)
        self.assertEqual(week_period(datetime(2027,1,4,2,tzinfo=TAIPEI))[0],'2026-W53')
        self.assertEqual(week_period(NOW,'2026-W40')[0],'2026-W40')
        with self.assertRaises(ValueError):week_period(NOW,'2026-W99')

    def test_bounded_missing_slots_duplicate_execution_and_stale_claim(self):
        ledger={'version':1,'slots':{}}
        slots=due_slots(ledger,NOW,24)
        self.assertEqual(len(slots),3)
        claim(ledger,slots[-1],NOW,'a')
        self.assertEqual(len(due_slots(ledger,NOW,24)),2)
        self.assertEqual(len(due_slots(ledger,NOW+timedelta(minutes=31),24)),3)
        ledger['slots'][slot_id(slots[-1])]['status']='completed'
        self.assertFalse(claim(ledger,slots[-1],NOW,'b'))
        with self.assertRaises(ValueError):due_slots(ledger,NOW,999)

    def test_real_independent_checkouts_restore_and_skip_completed_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);remote=base/'remote.git'
            subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
            first=base/'first';first.mkdir()
            store=HistoryStore(first,remote=str(remote));self.assertFalse(store.load())
            with patch('src.slot_runner.fetch_sources',return_value=source()) as fetch,patch('src.slot_runner.collect_community',return_value=[]):
                reports=process_slots(first,NOW,'1',24,store.publish)
                self.assertEqual(len(reports),3);fetch.assert_called_once()
            second=base/'second';second.mkdir()
            store2=HistoryStore(second,remote=str(remote));self.assertTrue(store2.load())
            with patch('src.slot_runner.fetch_sources') as fetch:
                self.assertEqual(process_slots(second,NOW,'2',24,store2.publish),[])
                fetch.assert_not_called()
            records=read_ledger(second)['slots']
            self.assertEqual(len(records),3)
            self.assertTrue(all(r['status']=='completed' for r in records.values()))
            self.assertTrue(any(r['catch_up'] for r in records.values()))
            rows,_=load_observations(second,NOW)
            self.assertEqual(len(rows),1)  # One real fetch, not three historical collections.
            self.assertEqual(rows[0].seen,NOW)
            self.assertTrue(all('Collected at:' in p.read_text(encoding='utf-8') for p in (second/'reports/daily').glob('*.md')))

    def test_claim_publication_failure_prevents_fetch(self):
        with tempfile.TemporaryDirectory() as tmp,patch('src.slot_runner.fetch_sources') as fetch:
            def fail(_):raise RuntimeError('mock history push rejection')
            with self.assertRaises(RuntimeError):process_slots(Path(tmp),NOW,'race',24,fail)
            fetch.assert_not_called()

    def test_no_sources_records_failure_and_partial_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('src.slot_runner.fetch_sources',return_value=[SourceResult('Reuters',[],'HTTP 401')]),patch('src.slot_runner.collect_community',return_value=[]):
                with self.assertRaises(RuntimeError):process_slots(root,NOW,'fail',24)
            week,start,end=week_period(NOW)
            status=completeness(root,NOW,start,end)
            self.assertTrue(status['partial']);self.assertGreater(status['failed'],0)
            _,_,body=render_weekly(root,NOW)
            self.assertIn('Partial',body);self.assertIn('HTTP 401',body)

    def test_corrupt_ledger_and_missing_or_corrupt_output_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state').mkdir()
            (root/'state/slots.json').write_text('{broken',encoding='utf-8')
            week,start,end=week_period(NOW)
            self.assertTrue(completeness(root,NOW,start,end)['partial'])
            with self.assertRaises(ValueError):read_ledger(root)
            ledger={'version':1,'slots':{}}
            slot=list(daily_slots(start,end))[0];claim(ledger,slot,slot,'1')
            record=ledger['slots'][slot_id(slot)]
            record.update(status='completed',output_file='reports/daily/missing.md')
            write_ledger(root,ledger)
            self.assertEqual(completeness(root,NOW,start,end)['completed'],0)

    def test_out_of_week_recovery_is_not_historical_coverage(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);week,start,end=week_period(NOW)
            slot=list(daily_slots(start,end))[-1]
            ledger={'version':1,'slots':{}};claim(ledger,slot,NOW,'late')
            folder=root/'reports/daily';folder.mkdir(parents=True)
            report=folder/'recovery.md';report.write_text('delayed',encoding='utf-8')
            ledger['slots'][slot_id(slot)].update(status='completed',output_file='reports/daily/recovery.md',
                output_sha256=hashlib.sha256(report.read_bytes()).hexdigest())
            write_ledger(root,ledger)
            status=completeness(root,NOW,start,end)
            self.assertEqual(status['recovered'],1)
            self.assertTrue(status['partial'])
            self.assertTrue(any('歷史內容' in e for e in status['errors']))
            report.write_text('corrupt',encoding='utf-8')
            self.assertEqual(completeness(root,NOW,start,end)['completed'],0)

    def test_independent_events_do_not_merge_on_same_theme(self):
        from src.weekly_curator import cluster,Event,Observation
        rows=[]
        for i,title in enumerate(('Google launches medical AI research','NVIDIA launches simulation tools')):
            a=Article(title,f'https://example.com/{i}','The Verge',None,'',[])
            rows.append(Event([Observation(a,NOW,'fixture')]))
        self.assertEqual(len(cluster(rows)),2)
