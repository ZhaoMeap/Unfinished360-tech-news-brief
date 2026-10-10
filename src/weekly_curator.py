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

MAX_FILE_BYTES = 2_000_000


@dataclass
class Observation:
    article: Article
    seen: datetime
    origin: str
    facts: str = ''
    social: str = ''
    label: str = 'Reported'


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
        date = re.search(r'；(\d{4}-\d{2}-\d{2}[^；\n]*)', block)
        label = 'Confirmed' if '[Confirmed]' in facts and is_official(link[2]) and link[1].startswith('官方：') else 'Reported'
        article = Article(title, link[2], link[1], date[1] if date else None, facts[:400], [])
        rows.append(Observation(article, seen, str(path), facts, social[:700], label))
    # Secondary candidates are useful discovery signals, not facts.
    other = re.search(r'^# 其他候選新聞\n(.*?)(?=^# |\Z)', body, re.M | re.S)
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
        article = Article(row['title'][:200],row['url'],row['source'],row.get('published_at'),
                          str(row.get('short_snippet') or '')[:400],tags if isinstance(tags,list) else [])
        if article.source in ('Hacker News', 'Reddit', 'X'):
            output.append(Observation(article,seen,str(path),'','','Rumor'))
            continue
        official = article.source.startswith('官方：') and is_official(article.url) and bool(article.short_snippet)
        label = 'Confirmed' if official else 'Reported'
        # Paraphrase recognized claims only, not the original public snippet.
        facts = labeled_facts(' '.join(explain(article,topic_for(article),label)['sentences'])) if article.short_snippet else ''
        output.append(Observation(article,seen,str(path),facts,'',label))
    return output


def load_observations(root, now):
    start = now - timedelta(days=7)
    output, warnings = [], []
    for folder, suffix in ((root/'reports/daily','md'),(root/'data/daily','json')):
        for path in sorted(folder.glob('*.'+suffix)):
            seen = timestamp(path)
            # Skip clearly out-of-range files before reading their contents.
            if suffix == 'md' and (seen is None or not start <= seen <= now):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise ValueError('超過素材大小上限')
                rows = read_markdown(path,seen) if suffix == 'md' else read_json(path)
                output.extend(o for o in rows if start <= o.seen <= now)
            except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
                warnings.append(f'{path.name}：無法讀取（{type(exc).__name__}）')
    # MD and JSON for the same collection should not double-count an observation.
    unique = {}
    for o in output:
        key = (o.seen,canonical(o.article.url))
        if key not in unique or len(o.facts) > len(unique[key].facts):
            unique[key] = o
    return sorted(unique.values(),key=lambda o:o.seen), warnings


def normalized(title):
    return re.sub(r'[^\w\u4e00-\u9fff]+',' ',title.lower()).strip()


def same_event(a,b):
    if canonical(a.url) == canonical(b.url):
        return True
    left,right = normalized(a.title), normalized(b.title)
    if left == right:
        return True
    # Long, highly similar titles only; opposite actions/numbers stay separate.
    if len(left) < 25 or len(right) < 25:
        return False
    if re.findall(r'\d+(?:\.\d+)?',left) != re.findall(r'\d+(?:\.\d+)?',right):
        return False
    polarity = r'\b(?:not|no|fails?|halts?|stops?|cuts?|increases?|decreases?)\b|停止|增加|減少'
    if set(re.findall(polarity,left)) != set(re.findall(polarity,right)):
        return False
    return SequenceMatcher(None,left,right).ratio() >= .92


def deduplicate(rows):
    events = []
    for row in rows:
        event = next((e for e in events if any(same_event(row.article,o.article) for o in e.observations)),None)
        if event is None:
            event = Event()
            events.append(event)
        event.observations.append(row)
    return events


def cluster(events):
    """Merge related events into themes; retain each event and its evidence."""
    groups = []
    for event in events:
        article = event.representative.article
        topic = topic_for(article)
        text = article.title + ' ' + article.short_snippet
        companies = set(entities(text + (' ' + article.source if article.source.startswith('官方：') else '')))
        products = set(product_names(text))
        group = next((g for g in groups if g['topic'].name == topic.name or
                      (companies & g['companies']) or (products & g['products'])),None)
        if group is None:
            group = dict(topic=topic, companies=set(), products=set(), events=[])
            groups.append(group)
        if topic.weight > group['topic'].weight:
            group['topic'] = topic
        group['companies'].update(companies)
        group['products'].update(products)
        group['events'].append(event)
    return sorted(groups,key=lambda g:(-g['topic'].weight,-sum(bool(e.representative.facts) for e in g['events'])))


def suitability(group):
    facts = sum(bool(e.representative.facts) for e in group['events'])
    if group['topic'].weight <= 1 or not facts:
        return '只觀察'
    return 'Podcast' if facts >= 2 or any(e.representative.label == 'Confirmed' for e in group['events']) else 'IG Threads'


def render_weekly(root: Path, now: datetime | None = None):
    now = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    rows,warnings = load_observations(root,now)
    events = deduplicate(rows)
    groups = cluster(events)
    selected = groups[:5]
    iso = now.isocalendar()
    week = f'{iso.year}-W{iso.week:02d}'
    lines = [f'Subject: 還沒想到科技週報 - {week}', '', '# 本週一句話',
             '[Analysis] ' + ('本週素材聚焦「'+'、'.join(g['topic'].name for g in selected[:3])+'」：先追工作流程如何改變，再看測試與落地門檻。' if selected else '本週沒有可讀素材；先恢復 daily collection，不編造科技趨勢。'),
             '', '# 本週科技主線', f'涵蓋台灣時間 {now-timedelta(days=7):%Y-%m-%d %H:%M} 至 {now:%Y-%m-%d %H:%M}；{len(rows)} 次素材出現、{len(events)} 個去重事件。出現次數不是市場熱度，來源數量不代表獨立查證。']
    followups = []
    for index,g in enumerate(selected,1):
        best = max(g['events'],key=lambda e:(topic_for(e.representative.article).weight,bool(e.representative.facts),e.representative.label=='Confirmed'))
        o = best.representative
        ex = explain(o.article,g['topic'],o.label)
        followups.extend(ex['gaps'])
        names = '、'.join(sorted(g['products'] or g['companies']))
        lines += ['',f'## {index}. {md(g["topic"].name)}'+(f'：{md(names)}' if names else ''),
                  '### 發生了什麼']
        for e in g['events'][:5]:
            r = e.representative
            lines += [f'- {md(r.facts) if r.facts else "[Analysis] 僅有標題線索："+md(r.article.title)} — {reference(r.article)}']
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
    lines += ['', '# 本週最適合 Podcast 的 3 個題目']
    podcasts = [g for g in groups if suitability(g)=='Podcast'][:3]
    lines += ['- [Analysis] '+md(g['topic'].name)+'：'+md(explain(g['events'][0].representative.article,g['topic'],'Reported')['opening']) for g in podcasts]
    if len(podcasts)<3:
        lines.append(f'目前只有 {len(podcasts)} 個可推薦的 Podcast 題目，其餘先觀察；不把重複報導當成確認。')
    lines += ['', '# 本週只適合觀察的題目']
    observed = [g for g in groups if suitability(g)=='只觀察']
    lines += ['- [Analysis] '+md(g['topic'].name)+'：只有候選線索或偏財務／人物消息，先補具体技術事件與來源。' for g in observed] or ['- 沒有額外純觀察題目；仍以各主線的查證清單為準。']
    lines += ['', '# 下週追蹤清單'] + ['- '+md(x) for x in list(dict.fromkeys(followups))[:12]]
    if not followups:
        lines.append('- 先確認 daily artifacts 可下載，或放入最近七天的日報素材。')
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
