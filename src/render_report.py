"""Distinct candidate radar and evidence-based, user-curated brief outputs."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, StrictUndefined

from .community import Discussion, canonical
from .fetch_sources import Article, SourceResult, is_official
from .source_quality import quality_for

TAIPEI = ZoneInfo('Asia/Taipei')
SOCIAL = {'Hacker News', 'Reddit', 'X'}


def md(text: str) -> str:
    return re.sub(r'([\\`*_{}\[\]()<>#!|])', r'\\\1', text.replace('\n', ' '))


def words(title: str) -> set[str]:
    stop = {'the', 'and', 'for', 'with', 'that', 'from', 'this', 'its', 'has', 'are', 'new'}
    return {w for w in re.findall(r'[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}', title.lower()) if w not in stop}


def related(a: Article, b: Article) -> bool:
    if canonical(a.url) == canonical(b.url):
        return True
    left, right = words(a.title), words(b.title)
    return len(left & right) >= 3 and len(left & right) / max(1, len(left | right)) >= .55


def select_news(results: list[SourceResult], mode: str = 'radar') -> list[Article]:
    articles = [a for r in results for a in r.articles if a.source not in SOCIAL]
    if mode == 'radar':
        rank = {'Reuters': 0, 'The Verge': 1, 'DIGITIMES': 2}
        articles.sort(key=lambda a: a.published_at or '', reverse=True)
        articles.sort(key=lambda a: rank.get(a.source, 3))
    chosen = []
    for article in articles:
        if not any(related(article, other) for other in chosen):
            chosen.append(article)
        if len(chosen) == (10 if mode == 'radar' else 3):
            break
    return chosen


def reference(article: Article) -> str:
    return f'[{md(article.source)}](<{article.url.replace(">", "%3E").replace("<", "%3C")}>)'


FOCUSES = [
    (r'patient|physician|clinical|healthcare|medical|醫療', '醫療 AI 與研究驗證', '研究方法、樣本規模與臨床限制'),
    (r'simulation|omniverse|模擬', 'AI 模擬與開發工具', '模擬工具、硬體需求與部署效果'),
    (r'privacy|tracking|surveillance|隱私', 'AI 代理的隱私與資料使用', '資料流向、權限與保護措施'),
    (r'earnings|revenue|profit|quarterly|財報|營收', '營收與營運表現', '營收、獲利與業務組成'),
    (r'regulat|antitrust|lawsuit|ban\b|fine\b|監管|裁罰', '監管與法律風險', '適用地區、法律程序與生效時間'),
    (r'acquir|merger|buyout|收購|合併', '收購與整併', '交易進度、金額與監管條件'),
    (r'launch|unveil|release|introduc|推出|發布', '產品或服務發布', '上市時間、功能與適用地區'),
    (r'invest|funding|spend|build|投資|建設', '投資與建設', '支出、交期與能源需求'),
    (r'layoff|restructur|裁員|重組', '人力與組織調整', '部門、規模與調整時程'),
]
CONCEPTS = {
    'AI 代理': r'agent|代理', 'GPU 與運算': r'gpu|compute|運算', '資料中心': r'data.?cent[er]+|資料中心',
    '記憶體': r'memory|dram|nand|記憶體', '半導體製造': r'semiconductor|foundry|晶圓|半導體',
    'AI 應用': r'\bai\b|artificial intelligence|人工智慧', '資料隱私': r'privacy|隱私',
    '價格與成本': r'pric|cost|價格|成本', '供應鏈': r'supply.?chain|供應鏈',
}


def draft_story(article: Article) -> tuple[str | None, str, str]:
    """Bounded rule paraphrase of supported topics, not a fabricated narrative."""
    text = article.title + ' ' + article.short_snippet
    found = next(((focus, detail) for pattern, focus, detail in FOCUSES if re.search(pattern, text, re.I)), None)
    if not article.short_snippet or len(article.short_snippet) < 40 or not found:
        return None, '待人工補充', '公開資料不足以建立事件脈絡；請補充事件主體、具體動作與時程。'
    focus, detail = found
    entities = [name for name in ('Google', 'Microsoft', 'Apple', 'Amazon', 'Meta', 'NVIDIA', 'TSMC', 'OpenAI', 'Anthropic', 'Phison')
                if re.search(r'\b' + name + r'\b', text, re.I)]
    actor = '、'.join(entities[:2]) or article.source.removeprefix('官方：')
    concepts = [name for name, pattern in CONCEPTS.items() if re.search(pattern, text, re.I)]
    uncertainty = bool(re.search(r'\b(could|may|might|reportedly|rumor|plans?|propos\w*)\b|可能|傳聞|計畫|提案', text, re.I))
    rewrites = {
        '醫療 AI 與研究驗證': f'{actor}公開的摘要聚焦 AI 在醫療情境的研究；研究資訊不等於已全面投入臨床使用。',
        'AI 模擬與開發工具': f'{actor}的公開摘要介紹模擬與開發流程，焦點是如何驗證工具效果。',
        'AI 代理的隱私與資料使用': f'{actor}的公開摘要討論資料隱私，焦點是保護承諾如何被驗證。',
        '營收與營運表現': f'{actor}的公開摘要聚焦營收或獲利，重點是分清業務表現與未來預測。',
        '監管與法律風險': f'{actor}的公開摘要涉及監管或法律程序；不同程序階段不能視為同一結果。',
        '收購與整併': f'{actor}的公開摘要涉及企業整併，簽約、審查與交割是不同階段。',
        '產品或服務發布': f'{actor}的公開摘要涉及產品或服務發布，是否可實際使用需要區分地區與時程。',
        '投資與建設': f'{actor}的公開摘要涉及投資或建設，規畫與實際支出需要分開理解。',
        '人力與組織調整': f'{actor}的公開摘要涉及組織調整，不能據此推定整個產業的就業走向。',
    }
    claim = rewrites[focus]
    if concepts:
        claim += '主題線索包含' + '、'.join(concepts[:3]) + '。'
    if uncertainty:
        claim += '來源含有條件式或計畫語氣，不能解讀成已完成的事件。'
    # Do not invent numbers, causes, policy implications, or product specifications.
    return focus, claim, f'待人工補充：{detail}的具體內容；本版只從公開摘要整理主題，未自動核實因果與數字。'


def community_view(discussion: Discussion) -> dict:
    def counts(data, minimum=1):
        return '、'.join(f'{name}（{count} 位樣本）' for name, count in sorted(data.items(), key=lambda pair: -pair[1]) if count >= minimum)
    small = ('少量討論' if discussion.total < 10 else '討論串較大，但只做少量抽樣') if discussion.total is not None else '總留言數未知，只能判定為少量樣本'
    return {
        'title': md(discussion.title[:100]), 'url': discussion.url,
        'source': discussion.source,
        'focus': counts(discussion.themes) or '待人工補充（樣本沒有可分類的主題）',
        'concerns': counts(discussion.concerns, 2) or '待人工補充（不足兩位獨立樣本，不能稱為常見擔憂）',
        'engineers': counts(discussion.technical) or '待人工補充（沒有可分類的技術觀點）',
        'size': f'{small}；讀取 {discussion.sampled} 位不同作者，總留言 ' + (str(discussion.total) if discussion.total is not None else '未知'),
        'status': discussion.status,
    }


def build_item(article, results, discussions):
    quality = quality_for(article)
    official = article.source.startswith('官方：') and is_official(article.url)
    label = 'Confirmed' if official and article.short_snippet else 'Reported' if article.source in ('Reuters', 'The Verge', 'DIGITIMES') else 'Analysis'
    focus, story, missing = draft_story(article)
    candidates = [a for r in results for a in r.articles if a.source not in SOCIAL and a.url != article.url and related(article, a)]
    # Similarity finds references, not confirmed shared claims; no auto upgrade.
    linked = [d for d in discussions if (d.target_url and canonical(d.target_url) == canonical(article.url)) or canonical(d.url) == canonical(article.url)]
    return {'title': md(article.title[:140]), 'quality': quality, 'label': label, 'date': article.published_at or '日期未提供',
            'focus': focus, 'story': md(story), 'missing': md(missing), 'reference': reference(article),
            'others': [reference(a) for a in candidates[:3]], 'discussions': [community_view(d) for d in linked]}


TEMPLATE = '''Subject: {{ subject }}

# {{ heading }}
> 台灣時間 {{ generated }}。{{ note }}
{% if mode == 'radar' %}
## 候選清單（candidate discovery）
{% for item in items %}
### {{ loop.index }}. {{ item.title }}
- 來源：{{ item.reference }}；日期：{{ item.date }}
- source quality score：{{ item.quality.kind }} / {{ item.quality.score }}；可用資訊程度：{{ item.quality.availability }}
- 編輯狀態：待人工補充；請挑選來源連結，放入 links.txt 後產生快報。
{% else %}
待人工補充：目前沒有可用的新聞候選。
{% endfor %}
{% else %}
## 今日故事線
{% for item in items if item.focus %}- [Analysis] {{ item.focus }}（{{ item.reference }}）
{% else %}待人工補充：目前指定來源的資訊不足以整理故事線。
{% endfor %}
## 最多 3 則 Podcast 快報草稿
{% for item in items %}
### {{ loop.index }}. {{ item.title }}
- 來源與日期：{{ item.reference }}；{{ item.date }}
- source quality score：{{ item.quality.kind }} / {{ item.quality.score }}；可用資訊程度：{{ item.quality.availability }}
- 可信度：[{{ item.label }}]；官方只代表發布者說法，資料品質不等於結論已查證。
{% if item.focus %}- **5 秒版：** [Analysis] {{ item.story }}
- **60 秒版／脈絡：** {{ item.missing }}
- **Ray 可以怎麼講：** [Analysis] 從「{{ item.focus }}」切入；先用來源補足具體事件，再說明誰受到影響。
{% else %}- **待人工補充：** {{ item.missing }}
{% endif %}{% if item.others %}- 跨來源候選（相似標題不代表交叉確認）：{{ item.others|join('；') }}
{% endif %}{% if item.discussions %}- 同連結社群回響：見下方公開討論樣本（不是事實證據）。
{% endif %}
{% endfor %}
## 今天可以延伸成 Podcast 的 3 個問題
1. [Analysis] 這個事件實際改變了什麼？哪些說法有官方文件支持？
2. [Analysis] 台灣供應鏈或使用者的具體影響，有哪些可觀察指標？
3. [Analysis] 社群提出的疑慮，可以用哪些公開資料或測試驗證？
{% endif %}
## 社群回響（公開留言小樣本）
{% for discussion in community %}
### {{ discussion.source }}：[{{ discussion.title }}](<{{ discussion.url }}>)
- source quality score：community discussion / 0（討論線索，非事實證據）
{% if discussion.status and '讀取 0 ' in discussion.size %}- {{ discussion.status }}；沒有留言樣本，不生成回響。
{% else %}
- [Rumor] 討論焦點：{{ discussion.focus }}
- [Rumor] 常見擔憂：{{ discussion.concerns }}
- [Rumor] 工程師觀點／技術討論：{{ discussion.engineers }}（依文字分類，不推定作者職業）
- 樣本程度：{{ discussion.size }}。不代表全站共識；語境與反諷可能誤分類。
{% if discussion.status %}- {{ discussion.status }}
{% endif %}{% endif %}{% else %}待人工補充：沒有可用的公開討論樣本。可在 links.txt 加入對應 HN／Reddit 討論串。
{% endfor %}
## 來源狀態與指定連結索引
{% for result in results %}- {{ result.source }}：{{ result.status }}{% if mode == 'links' %}{% for article in result.articles %} — [連結](<{{ article.url }}>) / {{ article.title|escape_md }}{% endfor %}{% endif %}
{% endfor %}
## 使用原則
僅使用標題、description 與有限公開摘要，不解析文章本文、不輸出全文、不繞過付費牆。自動模式不是新聞分析；指定連結也不能補出來源沒有的內容。相似標題不會自動升級為多來源確認。[Reported] 為媒體資訊，[Confirmed] 為官方發布資訊，[Analysis] 為作者整理，[Rumor] 為未確認討論。每個主題與推論均附來源，待人工補充事項不是結論。
'''


def render_report(results: list[SourceResult], output_dir: Path, now: datetime | None = None,
                  mode: str = 'radar', discussions: list[Discussion] | None = None) -> tuple[Path, str, str]:
    if mode not in ('radar', 'links'):
        raise ValueError('Unknown report mode')
    local = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    heading = '科技新聞候選雷達' if mode == 'radar' else '還沒想到科技快報'
    subject = heading + ' - ' + local.strftime('%Y/%m/%d')
    discussions = discussions or []
    items = [build_item(a, results, discussions) for a in select_news(results, mode)]
    env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    env.filters['escape_md'] = md
    body = env.from_string(TEMPLATE).render(subject=subject, heading=heading, generated=local.strftime('%Y-%m-%d %H:%M %Z'),
        mode=mode, items=items, results=results, community=[community_view(d) for d in discussions],
        note='發現候選，不代表已完成分析。' if mode == 'radar' else '指定連結的公開資訊草稿；主稿最多三則，資訊不足直接列待人工補充。')
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f'{local:%Y-%m-%d}.md'
    # Keep a radar copy so a same-day links run does not destroy discovery output.
    if mode == 'radar':
        (output_dir / f'{local:%Y-%m-%d}-radar.md').write_text(body, encoding='utf-8')
    path.write_text(body, encoding='utf-8')
    return path, subject, body
