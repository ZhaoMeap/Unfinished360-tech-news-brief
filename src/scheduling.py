"""Taipei schedule calculations and durable slot ledger, independent of Actions."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .render_report import TAIPEI

HOURS = (9,15,21)
UTC = timezone.utc


def utc(instant):
    if instant.tzinfo is None:
        raise ValueError('timezone-aware datetime required')
    return instant.astimezone(UTC).isoformat()


def daily_slots(start,end):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError('timezone-aware range required')
    day=start.astimezone(TAIPEI).replace(hour=0,minute=0,second=0,microsecond=0)
    while day < end:
        for hour in HOURS:
            slot=day.replace(hour=hour,minute=17)
            if start <= slot < end:
                yield slot
        day+=timedelta(days=1)


def slot_id(slot):
    return slot.astimezone(TAIPEI).strftime('daily-%Y-%m-%d-%H%M')


def week_period(now,iso_week=None):
    local=now.astimezone(TAIPEI)
    if iso_week:
        match=re.fullmatch(r'(\d{4})-W(\d{2})',iso_week)
        if not match:
            raise ValueError('week must be YYYY-Www')
        day=datetime.fromisocalendar(int(match[1]),int(match[2]),1).replace(tzinfo=TAIPEI)
    else:
        # Latest scheduled Sunday 20:00, including a Monday-delayed Sunday run.
        due=local.replace(hour=20,minute=0,second=0,microsecond=0)-timedelta(days=(local.weekday()+1)%7)
        if due>local:
            due-=timedelta(days=7)
        day=(due-timedelta(days=6)).replace(hour=0,minute=0,second=0,microsecond=0)
    iso=day.isocalendar()
    return f'{iso.year}-W{iso.week:02d}',day,day+timedelta(days=7)


def read_ledger(root):
    path=root/'state/slots.json'
    if not path.exists():
        return {'version':1,'slots':{}}
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('version')!=1 or not isinstance(data.get('slots'),dict):
        raise ValueError('invalid slot ledger')
    return data


def write_ledger(root,data):
    folder=root/'state';folder.mkdir(parents=True,exist_ok=True)
    temporary=folder/'slots.tmp'
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(folder/'slots.json')


def due_slots(ledger,now,lookback_hours=48):
    if not 1<=lookback_hours<=168:
        raise ValueError('lookback must be 1–168 hours')
    result=[]
    for slot in daily_slots(now-timedelta(hours=lookback_hours),now+timedelta(microseconds=1)):
        record=ledger['slots'].get(slot_id(slot),{})
        status=record.get('status')
        if status=='completed':
            continue
        if status=='running':
            started=datetime.fromisoformat(record['actual_started_at_utc'])
            if now-started<timedelta(minutes=30):
                continue
        if record.get('attempts',0)>=3:
            continue
        result.append(slot)
    return result


def claim(ledger,slot,now,run_id):
    key=slot_id(slot)
    old=ledger['slots'].get(key,{})
    if old.get('status')=='completed':
        return False
    ledger['slots'][key]=dict(scheduled_slot_id=key,scheduled_at_utc=utc(slot),actual_started_at_utc=utc(now),
        completed_at_utc=None,status='running',catch_up=now-slot>timedelta(minutes=30),run_id=str(run_id),
        output_file=None,attempts=old.get('attempts',0)+1,
        previous_attempts=old.get('previous_attempts',[])+([{k:v for k,v in old.items() if k!='previous_attempts'}] if old else []))
    return True


def completeness(root,now,start,end):
    expected=list(daily_slots(start,end))
    try:
        ledger=read_ledger(root)
        errors=[]
    except (ValueError,OSError):
        ledger={'slots':{}};errors=['slot ledger 無法讀取']
    counts=dict(expected=len(expected),completed=0,recovered=0,missing=0,failed=0,pending=0)
    for slot in expected:
        record=ledger['slots'].get(slot_id(slot),{})
        if record.get('status')=='completed':
            path=root/str(record.get('output_file') or '')
            if path.is_file():
                if record.get('output_sha256') and hashlib.sha256(path.read_bytes()).hexdigest()!=record['output_sha256']:
                    errors.append(f'{slot_id(slot)} 的報告校驗失敗')
                    counts['missing']+=1
                    continue
                actual=datetime.fromisoformat(record['actual_started_at_utc'])
                if not start<=actual<end:
                    errors.append(f'{slot_id(slot)} 於週範圍外補跑，不代表歷史內容已還原')
                counts['completed']+=1
                counts['recovered']+=int(bool(record.get('catch_up')))
                continue
            errors.append(f'{slot_id(slot)} 的完成報告遺失')
        if slot>now:
            counts['pending']+=1
        elif record.get('status')=='failed':
            counts['failed']+=1
        else:
            counts['missing']+=1
    restored=root/'state/restore_status.json'
    if restored.exists():
        try:
            status=json.loads(restored.read_text(encoding='utf-8'))
            errors.extend(status.get('errors',[]))
        except (OSError,ValueError):
            errors.append('restore status 無法讀取')
    counts['errors']=errors
    counts['partial']=counts['completed']!=counts['expected'] or bool(errors)
    return counts
