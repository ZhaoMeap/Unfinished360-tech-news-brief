"""Idempotent slot execution. Persistence callbacks publish each claim before fetch."""
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from .daily_snapshot import save_snapshot
from .scheduling import read_ledger, write_ledger, due_slots, claim, slot_id, utc
from .fetch_sources import fetch_sources
from .community import collect_community
from .editor_report import render_editor_report


def process_slots(root,now=None,run_id='local',lookback_hours=48,persist=lambda message:None):
    now=now or datetime.now(timezone.utc)
    ledger=read_ledger(root)
    slots=due_slots(ledger,now,lookback_hours)
    claimed=[]
    for slot in slots:
        if claim(ledger,slot,now,run_id):
            claimed.append(slot)
    if not claimed:
        return []
    write_ledger(root,ledger)
    persist('Claim daily collection slots')
    outputs=[]
    try:
        # One actual fetch for the recovery batch: never pretend to fetch past content.
        results=fetch_sources(now)
        discussions=collect_community(results)
        for slot in claimed:
            key=slot_id(slot);record=ledger['slots'][key]
            (root/'reports').mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=root/'reports') as tmp:
                _,_,body=render_editor_report(results,Path(tmp),now,discussions)
            target=root/'reports/daily'/f'{slot:%Y-%m-%d_%H%M}_editor.md'
            banner=f'Collected at: {utc(now)}\nScheduled slot: {key}\nCatch-up: {record["catch_up"]}\nActual run: {run_id}\n\n'
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(banner+body,encoding='utf-8')
            save_snapshot(root,results,now,target,key)
            usable=any(r.articles for r in results if r.source not in ('Hacker News','Reddit','X'))
            record.update(status='completed' if usable else 'failed',completed_at_utc=utc(datetime.now(timezone.utc)),
                          output_file=str(target.relative_to(root)),output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                          error=None if usable else 'No non-community source available',
                          source_diagnostics=[dict(source=r.source,status=r.status) for r in results])
            outputs.append(target)
        write_ledger(root,ledger)
        persist('Record daily slot results and source provenance')
    except Exception as exc:
        for slot in claimed:
            record=ledger['slots'][slot_id(slot)]
            if record['status']=='running':
                record.update(status='failed',completed_at_utc=utc(datetime.now(timezone.utc)),error=type(exc).__name__)
        write_ledger(root,ledger)
        # If persistence fails, do not claim the run is durable or successful.
        persist('Record failed daily slot attempts')
        raise
    if any(ledger['slots'][slot_id(s)]['status']=='failed' for s in claimed):
        raise RuntimeError('Source collection failed; slot diagnostics persisted')
    return outputs
