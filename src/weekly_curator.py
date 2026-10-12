"""Curate saved seven-day inputs; no fetching, full text, or email."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from .community import canonical
from .editor_report import topic_for
from .explain_report import explain
from .fetch_sources import Article, is_official
from .render_report import TAIPEI, md, reference
from .story_narrative import entities, product_names
from .events import same_event, normalized
from .evidence import assess, event_id, subjects, coverage
from .scheduling import week_period, completeness,read_ledger

MAX_FILE_BYTES = 2_000_000


@dataclass
class Observation:
    article: Article
    seen: datetime
    origin: str
    facts: str = ''
    social: str = ''
    label: str = 'Reported'
    evidence_level: str = 'C'
    stable_id: str = ''


@dataclass
class Event:
    observations: list[Observation] = field(default_factory=list)

    @property
    def representative(self):
        return max(self.observations, key=lambda o: (bool(o.facts), o.seen, len(o.article.short_snippet)))

    @property
    def first(self):
        return min(o.seen for o in self.observations)

    @property
    def last(self):
        return max(o.seen for o in self.observations)

    @property
    def sources(self):
        return {o.article.source for o in self.observations}

    @property
    def event_id(self):
        return next((o.stable_id for o in self.observations if o.stable_id),event_id(min(self.observations,key=lambda o:(o.seen,o.article.url)).article))


def timestamp(path, data=None):
    value = (data or {}).get('collected_at')
    if value:
        try:
            instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if instant.tzinfo:
                return instant.astimezone(TAIPEI)
        except (ValueError, AttributeError, TypeError):
            pass
    match = re.search(r'(\d{4}-\d{2}-\d{2})(?:_(\d{4}))?', path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match[1] + (match[2] or '0000'), '%Y-%m-%d%H%M').replace(tzinfo=TAIPEI)
    except ValueError:
        return None


def sections(block):
    return {m[1]: m[2].strip() for m in re.finditer(r'^### ([^\n]+)\n(.*?)(?=^### |\Z)', block, re.M | re.S)}


def labeled_facts(text):
    text = text.replace('\\[', '[').replace('\\]', ']')
    return ' '.join(m[0].strip() for m in re.finditer(
        r'\[(?:Reported|Confirmed)\].*?(?=\[(?:Analysis|Background|Reported|Confirmed|Rumor)\]|\Z)', text, re.S))[:1400]


def read_markdown(path, seen):
    body = path.read_text(encoding='utf-8')
    collected=re.search(r'^(?:<!-- )?Collected at: ([^\n]+)$',body,re.M)
    if collected:
        seen=datetime.fromisoformat(collected[1]).astimezone(TAIPEI)
    rows = []
    for block in re.split(r'^## (?=\d+\.)', body, flags=re.M)[1:]:
        block = re.split(r'^# ', block, maxsplit=1, flags=re.M)[0]
        title = re.sub(r'^\d+\.\s*', '', block.splitlines()[0])
        link = re.search(r'\*\*來源：\*\*\s*\[([^\]]+)\]\(<(https://[^>]+)>\)', block)
        if not link:
            continue
        parts = sections(block)
        narrative = next((v for k,v in parts.items() if '這篇新聞在講什麼' in k), '')
        facts = labeled_facts(narrative)
        social = next((v for k,v in parts.items() if '網路上的人' in k), '')
        # Keep actual sampled discussion only, never hypothetical questions.
        social = social.replace('\\[', '[').replace('\\]', ']')
        social = social if '[Rumor]' in social and '抽樣' in social else ''
        date = re.search(r'；(?:刊登時間 )?(\d{4}-\d{2}-\d{2}[^；\n]*)', block)
        label = 'Confirmed' if '[Confirmed]' in facts and is_official(link[2]) and link[1].startswith('官方：') else 'Reported'
        proof=re.search(r'\*\*證據：\*\* ([ABC])',block)
        level=proof[1] if proof else 'C'
        article = Article(title, link[2], link[1], date[1] if date else None, facts[:400], [], 'public summary' if level in ('A','B') else '')
        rows.append(Observation(article, seen, str(path), facts if level in ('A','B') else '', social[:700], label,level))
    # Secondary candidates are useful discovery signals, not facts.
    other = re.search(r'^# (?:其他候選新聞|未選入主題的來源索引)\n(.*?)(?=^# |\Z)', body, re.M | re.S)
    if other:
        for item in re.finditer(r'^- \[Analysis\] 觀察：(.*?) — \[([^\]]+)\]\(<(https://[^>]+)>\)', other[1], re.M):
            rows.append(Observation(Article(item[1],item[3],item[2],None,'',[]),seen,str(path)))
    return rows


def read_json(path):
    payload = json.loads(path.read_text(encoding='utf-8'))
    metadata = payload if isinstance(payload, dict) else {}
    seen = timestamp(path, metadata)
    if seen is None:
        raise ValueError('缺少 collected_at 或日期檔名')
    rows = payload if isinstance(payload,list) else payload.get('articles',[])
    if not isinstance(rows,list):
        raise ValueError('articles 必須是陣列')
    output = []
    for row in rows[:200]:
        if not isinstance(row,dict) or not all(isinstance(row.get(k),str) for k in ('title','url','source')):
            continue
        if not row['url'].startswith('https://'):
            continue
        tags = row.get('tags',[])
        proof=metadata.get('evidence',{}).get(canonical(row['url']),{})
        article = Article(row['title'][:200],row['url'],row['source'],row.get('published_at'),
                          str(row.get('short_snippet') or '')[:400],tags if isinstance(tags,list) else [], proof.get('quality_hint',''))
        if article.source in ('Hacker News', 'Reddit', 'X'):
            output.append(Observation(article,seen,str(path),'','','Rumor'))
            continue
        evidence=assess(article)
        label=evidence.label
        # Paraphrase recognized claims only, not the original public snippet.
        facts = labeled_facts(' '.join(explain(article,topic_for(article),label)['sentences'])) if evidence.level in ('A','B') else ''
        output.append(Observation(article,seen,str(path),facts,'',label,evidence.level,proof.get('event_id','')))
    return output


def load_observations(root, now, start=None, end=None):
    start = start or now - timedelta(days=7)
    end = end or now + timedelta(microseconds=1)
    output, warnings = [], []
    for folder, suffix in ((root/'reports/daily','md'),(root/'data/daily','json')):
        for path in sorted(folder.glob('*.'+suffix)):
            seen = timestamp(path)
            # Skip clearly out-of-range files before reading their contents.
            if suffix == 'md' and seen is None:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise ValueError('超過素材大小上限')
                rows = read_markdown(path,seen) if suffix == 'md' else read_json(path)
                output.extend(o for o in rows if start <= o.seen < end and o.seen<=now)
            except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
                warnings.append(f'{path.name}：無法讀取（{type(exc).__name__}）')
    # MD and JSON for the same collection should not double-count an observation.
    unique = {}
    for o in output:
        key = (o.seen,canonical(o.article.url))
        if key not in unique or len(o.facts) > len(unique[key].facts):
            unique[key] = o
    return sorted(unique.values(),key=lambda o:o.seen), warnings


def deduplicate(rows):
    events = []
    for row in rows:
        event = next((e for e in events if any((row.stable_id and row.stable_id==o.stable_id) or same_event(row.article,o.article) for o in e.observations)),None)
        if event is None:
            event = Event()
            events.append(event)
        event.observations.append(row)
    return events


def podcast_score(event):
    article=event.representative.article
    topic=topic_for(article)
    level=event.representative.evidence_level
    technical=bool(re.search(r'API|GPU|firmware|security|eval|simulation|模型|測試|權限',article.title+' '+article.short_snippet,re.I))
    users=bool(re.search(r'user|privacy|patient|wallet|phone|users|隱私|病人|使用者',article.title,re.I))
    dimensions=dict(technology=2 if topic.weight>=8 else 1, engineering=2 if technical else 1,
                    users=2 if users else 1, evidence={'A':2,'B':1,'C':0}[level],
                    storytelling=2 if re.search(r'launch|release|tamper|cutting off|study|發布|評測',article.title,re.I) else 1,
                    explainability=2 if topic!=topic_for(Article('','https://example.com','',None,'',[])) else 0)
    total=sum(dimensions.values())
    if topic.weight<=1:
        total=min(total,4)
    return total,dimensions


def cluster(events):
    groups=[]
    for event in events:
        article=event.representative.article
        groups.append(dict(topic=topic_for(article),companies=set(subjects(article)),products=set(product_names(article.title)),
                           events=[event],score=podcast_score(event)[0],dimensions=podcast_score(event)[1]))
    return sorted(groups,key=lambda g:(-g['score'],-g['topic'].weight,g['events'][0].event_id))


def suitability(group):
    level=group['events'][0].representative.evidence_level
    if level=='C' or group['topic'].weight<=1:
        return '只觀察'
    return 'Podcast' if group['score']>=9 else 'IG Threads'


def render_weekly(root: Path, now: datetime | None = None, iso_week: str | None = None):
    now = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    week,start,end=week_period(now,iso_week)
    status=completeness(root,now,start,end)
    rows,warnings = load_observations(root,now,start,end)
    events = deduplicate(rows)
    groups = cluster(events)
    selected = groups[:5]
    if warnings:
        status['partial']=True
        status['errors'].extend(warnings)
    lines = [f'Subject: 還沒想到科技週報 - {week}', '', '# 本週一句話',
             '[Analysis] ' + ('本週素材聚焦「'+'、'.join(g['topic'].name for g in selected[:3])+'」：先追工作流程如何改變，再看測試與落地門檻。' if selected else '本週沒有可讀素材；先恢復 daily collection，不編造科技趨勢。'),
             '', '# 素材完整性', '部分週報（Partial）' if status['partial'] else '完整 slot 覆蓋；不代表全部事實已查證',
             f"Expected {status['expected']} / Completed {status['completed']} / Recovered {status['recovered']} / Missing {status['missing']} / Failed {status['failed']} / Pending {status['pending']}",
             *['- '+md(e) for e in status['errors']], '', '# 本週科技主線',
             f'指定台灣日期範圍 {start:%Y-%m-%d %H:%M} 至 {end:%Y-%m-%d %H:%M}（不含終點）；實際整理時間 {now:%Y-%m-%d %H:%M}；{len(rows)} 次素材、{len(events)} 個獨立事件。']
    followups = []
    for index,g in enumerate(selected,1):
        best = max(g['events'],key=lambda e:(topic_for(e.representative.article).weight,bool(e.representative.facts),e.representative.label=='Confirmed'))
        o = best.representative
        ex = explain(o.article,g['topic'],o.label)
        followups.extend(ex['gaps'])
        names = '、'.join(sorted(g['products'] or g['companies']))
        lines += ['',f'## {index}. {md(o.article.title)}',
                  f"證據 {o.evidence_level}；跨來源網域 {coverage([v.article for v in best.observations])}；Podcast 分數 {g['score']}/12。",
                  '[Analysis] 選題理由：'+md(g['topic'].name)+'；評分面向 '+md(str(g['dimensions']))+'。同主題的其他事件不併成事實。', '### 發生了什麼']
        for e in g['events'][:5]:
            r = e.representative
            lines += [f'- {md(r.facts) if r.facts else "[Analysis] 僅有標題線索："+md(r.article.title)} — {reference(r.article)}']
        if o.evidence_level=='C':
            lines += ['[Analysis] 只作候選觀察；尚未取得足夠事件證據，不填充詳細工程分析。', '### 仍需查證的地方', '- 具體公開事件摘要、官方文件與可辨識的動作／產品。']
            continue
        lines += ['### 工程師應該注意什麼', '[Analysis] '+md(ex['attention']),
                  '### 技術背景補充'] + ['- [Background] '+md(b) for b in ex['background']]
        lines += ['### 代表新聞']
        for e in g['events'][:5]:
            lines.append(f'- [{md(e.representative.article.title)}](<{e.representative.article.url}>)；首次 {e.first:%m/%d %H:%M}、最後 {e.last:%m/%d %H:%M}；出現 {len(e.observations)} 次；來源 {len(e.sources)} 個（{md("、".join(sorted(e.sources)))}）。')
            refs = {o.article.url:o.article for o in e.observations}
            if len(refs)>1:
                lines.append('  其他同事件連結：'+'、'.join(reference(a) for a in refs.values() if a.url!=e.representative.article.url))
        areas = re.findall(r'AI server|data center|GPU|memory|PCB|HBM|SSD|advanced packaging|CoWoS|ODM|OEM|資料中心|先進封裝|記憶體', ' '.join(e.representative.article.title for e in g['events']), re.I)
        connection = ('素材點名 '+ '、'.join(sorted(g['companies']))+'；' if g['companies'] else '') + ('技術線索涉及 '+ '、'.join(sorted(set(areas)))+'，可追規格、相容性、供電與散熱測試。' if areas else '可從工作流程與工具整合追 AI 應用，沒有直接硬體採購或台廠訂單證據。')
        lines += ['### Big Tech / AI / data center / 台灣科技業關聯', '[Analysis] '+md(connection),
                  '### 網路社群回響']
        social = list(dict.fromkeys(o.social for e in g['events'] for o in e.observations if o.social))
        lines += [md(s) for s in social[:2]] if social else ['沒有取得對應事件的實際討論樣本；以下是編輯提問，不是網友共識。']+['- [Analysis] '+md(q) for q in ex['questions']]
        lines += ['### Ray 的 Podcast 切入角度','[Analysis] '+md(ex['opening']),
                  '### 適合程度', '[Analysis] '+suitability(g)+'：依素材能否解釋事件與工程問題判斷，正式錄音前仍需核對來源。',
                  '### 仍需查證的地方'] + ['- '+md(gap) for gap in ex['gaps']]
    if len(selected)<3:
        lines.append(f'只有 {len(selected)} 條可辨識主線；不足三條不湊數。')
    lines += ['', '# 主題觀察（不是同一事件）']
    themes={}
    for g in groups:
        themes.setdefault(g['topic'].name,[]).append(g['events'][0].representative.article.title)
    lines += ['- [Analysis] '+md(name)+'：'+', '.join(ids)+'；僅屬主題相近。' for name,ids in themes.items() if len(ids)>1]
    lines += ['', '# 本週最適合 Podcast 的 3 個題目']
    podcasts = [g for g in groups if suitability(g)=='Podcast'][:3]
    lines += ['- [Analysis] '+md(g['events'][0].representative.article.title)+'：'+md(explain(g['events'][0].representative.article,g['topic'],'Reported')['opening']) for g in podcasts]
    if len(podcasts)<3:
        lines.append(f'目前只有 {len(podcasts)} 個可推薦的 Podcast 題目，其餘先觀察；不把重複報導當成確認。')
    lines += ['', '# 本週只適合觀察的題目']
    observed = [g for g in groups if suitability(g)=='只觀察']
    lines += ['- [Analysis] '+md(g['topic'].name)+'：只有候選線索或偏財務／人物消息，先補具体技術事件與來源。' for g in observed] or ['- 沒有額外純觀察題目；仍以各主線的查證清單為準。']
    lines += ['', '# 下週追蹤清單'] + ['- '+md(x) for x in list(dict.fromkeys(followups))[:12]]
    if not followups:
        lines.append('- 先確認 daily artifacts 可下載，或放入最近七天的日報素材。')
    lines += ['', '# 來源可用性']
    diagnostics={}
    for file in (root/'data/daily').glob('*.json'):
        try:
            payload=json.loads(file.read_text(encoding='utf-8'))
            seen=timestamp(file,payload if isinstance(payload,dict) else {})
            if seen and start<=seen<end and seen<=now and isinstance(payload,dict):
                for source in payload.get('source_diagnostics',[]):
                    diagnostics[source['source']]=source['status']
        except (OSError,ValueError,TypeError,KeyError):
            pass
    try:
        for record in read_ledger(root)['slots'].values():
            scheduled=datetime.fromisoformat(record['scheduled_at_utc'])
            if start<=scheduled<end:
                for source in record.get('source_diagnostics',[]):
                    diagnostics[source['source']]=source['status']+'（實際採集 '+record['actual_started_at_utc']+'）'
    except (ValueError,OSError,KeyError):
        pass
    lines += ['- '+md(k)+'：'+md(v) for k,v in diagnostics.items()] or ['- 舊 Markdown 素材未保存結構化來源診斷，不能宣稱來源都可用。']
    lines += ['', '# 素材與使用原則'] + ['- '+md(w) for w in warnings]
    lines += ['只整理本機保存的日報／JSON；不抓新聞全文、不繞過付費牆、不輸出全文、不寄信。日報是素材，週報是 Ray 檢查與選題用，仍不是可直接發布的已查證稿。',
              '[Reported]／[Confirmed] 保留來源發布主張，不因重複出現而升級；[Background] 是一般工程知識，[Analysis] 是編輯判斷，[Rumor] 是有限社群討論。',
              '同公司／產品／技術合併只表示選題相關，不代表同一事件、因果關係或独立交叉確認。']
    formatted = []
    for line in lines:
        if line.startswith('#'):
            if formatted and formatted[-1] != '':
                formatted.append('')
            formatted.extend([line, ''])
        else:
            formatted.append(line)
    body = '\n'.join(formatted).replace('具体','具體').replace('独立','獨立')+'\n'
    folder = root/'reports/weekly'
    folder.mkdir(parents=True,exist_ok=True)
    path = folder/f'{week}_weekly.md'
    path.write_text(body,encoding='utf-8')
    return path,lines[0][9:],body
