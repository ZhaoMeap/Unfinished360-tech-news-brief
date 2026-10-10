"""Conservative brief: source metadata and explicitly labelled editorial questions."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, StrictUndefined

from .fetch_sources import Article, SourceResult, is_official, official_links

TAIPEI = ZoneInfo("Asia/Taipei")
SOCIAL = {"Hacker News", "Reddit", "X"}


def md(text: str) -> str:
    # Feed titles cannot inject Markdown headings, images, or arbitrary links.
    return re.sub(r"([\\`*_{}\[\]()<>#!|])", r"\\\1", text.replace("\n", " "))


def words(title: str) -> set[str]:
    stop = {"the", "and", "for", "with", "that", "from", "this", "its", "has", "are", "new"}
    return {w for w in re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", title.lower()) if w not in stop}


def related(a: Article, b: Article) -> bool:
    if a.url == b.url:
        return True
    left, right = words(a.title), words(b.title)
    shared = left & right
    return len(shared) >= 3 and len(shared) / max(1, len(left | right)) >= 0.55


def select_news(results: list[SourceResult]) -> list[Article]:
    articles = [a for r in results for a in r.articles if a.source not in SOCIAL]
    # Reuters leads; community threads never occupy a factual news slot.
    rank = {"Reuters": 0, "The Verge": 1, "DIGITIMES": 2}
    articles.sort(key=lambda a: a.published_at or "", reverse=True)
    articles.sort(key=lambda a: rank.get(a.source, 3 if a.source.startswith("官方：") else 4))
    chosen = []
    # Prefer source diversity before filling remaining slots from one outlet.
    for diverse in (True, False):
        for article in articles:
            if diverse and any(article.source == existing.source for existing in chosen):
                continue
            if not any(related(article, existing) for existing in chosen):
                chosen.append(article)
            if len(chosen) == 3:
                return chosen
    return chosen


def reference(article: Article) -> str:
    return f"[{md(article.source)}](<{article.url.replace('>', '%3E').replace('<', '%3C')}>)"


def headline_focus(article: Article) -> tuple[str, str]:
    """Describe the headline's topic, without treating speculative wording as fact."""
    title = article.title.lower()
    names = [name for name in ("Microsoft", "Google", "Apple", "Amazon", "Meta", "NVIDIA", "TSMC", "OpenAI", "Anthropic")
             if re.search(r"\b" + re.escape(name.lower()) + r"\b", title)]
    actor = "、".join(names[:2]) or (article.source.removeprefix("官方：") if article.source.startswith("官方：") else "科技產業")
    events = [
        (r"\b(patient\w*|physician\w*|clinical|healthcare|medical)\b|醫療", "醫療 AI 與研究驗證"),
        (r"\b(simulation\w*|omniverse)\b|模擬", "AI 模擬與開發工具"),
        (r"\b(gaming|games|play fest)\b|遊戲", "遊戲活動與平台生態"),
        (r"\b(acquir\w*|merger|buyout)\b|收購|合併", "收購與整併"),
        (r"\b(earnings|revenue|profit|quarterly)\b|財報|營收", "財報與營運表現"),
        (r"\b(regulat\w*|antitrust|lawsuit|ban\w*|fine\w*)\b|監管|裁罰", "監管與法律風險"),
        (r"\b(launch\w*|unveil\w*|release\w*|introduc\w*)\b|推出|發布", "產品或服務發布"),
        (r"\b(invest\w*|funding|spend\w*|build\w*)\b|投資|建設", "投資與建設"),
        (r"\b(layoff\w*|cuts|restructur\w*)\b|裁員|重組", "人力與組織調整"),
    ]
    focus = next((description for pattern, description in events if re.search(pattern, title)),
                 "、".join(article.tags[:2]) or "科技動態")
    return actor, focus


def context_question(focus: str) -> str:
    return {
        "醫療 AI 與研究驗證": "先核對研究方法、樣本與臨床限制；研究結果不等於全面可用。",
        "AI 模擬與開發工具": "先確認可用工具、硬體需求與實測效果；示範不等於部署成果。",
        "遊戲活動與平台生態": "先核對活動日期、地區與參與門檻，再看使用者與開發者受益程度。",
        "財報與營運表現": "先分清已實現營收、獲利與未來指引，避免把預測當業績。",
        "監管與法律風險": "先核對司法管轄、法律程序與生效時間，避免把提案當成已生效規範。",
        "收購與整併": "先區分傳聞、已簽約與已完成交易，再確認監管條件。",
        "產品或服務發布": "先核對上市時間、價格、適用地區與功能限制。",
        "投資與建設": "先區分投資計畫與實際支出，並確認交期與能源需求。",
        "人力與組織調整": "先核對調整規模、部門與時程，不把個別消息推成全產業趨勢。",
    }.get(focus, "先核對時程、適用範圍與可驗證指標，避免把預測當成果。")


def perspective(article: Article, source: str, results: list[SourceResult]) -> str:
    candidates = [a for r in results if r.source == source for a in r.articles if related(article, a)]
    if not candidates:
        return "目前無法取得（沒有可核對的同事件項目）。"
    return "[Reported] 同事件候選，觀點待核對：" + reference(candidates[0])


def build_item(article: Article, results: list[SourceResult]) -> dict:
    official = article.source.startswith("官方：") and is_official(article.url)
    label = "Confirmed" if official else "Reported"
    topic = "、".join(article.tags[:2]) or "科技動態"
    actor, focus = headline_focus(article)
    candidates = [a for r in results if r.source.startswith("官方：") for a in r.articles
                  if a.url != article.url and related(article, a)]
    socials = [a for r in results if r.source in SOCIAL for a in r.articles if related(article, a)]
    links = [reference(article)]
    links += [reference(a) for a in candidates[:2]]
    links += [reference(a) for a in socials[:2]]
    links += [f"官方連結候選（尚未核對）：<{u}>" for u in official_links(article)[:2]]
    official_note = ("官方說法不代表預測已實現。" if official else "尚未完成官方確認。")
    if candidates and not official:
        official_note += "有官方候選連結，但不自動升級為 Confirmed。"
    return {
        "title": md(article.title[:120]), "label": label,
        "focus": focus,
        "five": f"[Analysis] 標題關注{actor}的{focus}；進展與影響待核對。",
        "sixty": f"[{label}] {md(article.source)} 的項目日期為 {md((article.published_at or '日期未知')[:10])}。"
                 f" [Analysis] {context_question(focus)}未讀全文，{official_note}",
        "reuters": perspective(article, "Reuters", results),
        "verge": perspective(article, "The Verge", results),
        "digitimes": perspective(article, "DIGITIMES", results),
        "strategy": f"[Analysis] 若{topic}影響業務，可評估產品、採購或合規調整；不是已宣布的對策。",
        "social": ("[Rumor] 相關討論串供提問；未取留言，不代表共識或事實。 "
                   + "；".join(reference(a) for a in socials[:2])) if socials
                  else "目前無法取得（沒有可核對的同事件討論串）。",
        "podcast": f"[Analysis] 從{focus}切入：『誰的成本或使用體驗會改變？』錄音前先核對來源。",
        "links": links,
    }


TEMPLATE = """Subject: {{ subject }}

# 今日一句話總結
{% if items %}[Analysis] 今日線索：{{ items|map(attribute='focus')|join('、') }}；進展與影響仍需核對。{% else %}目前無法取得足夠的近期科技新聞；今天不產生虛構摘要。{% endif %}

> 台灣時間 {{ generated }}；最近 48 小時的 metadata-only 草稿。未讀全文，脈絡待人工核對。目標閱讀時間 3–5 分鐘。

## 3 則重點新聞
{% for item in items %}
### {{ loop.index }}. {{ item.title }}
- **5 秒版：** {{ item.five }}
- **60 秒版／事件脈絡：** {{ item.sixty }}
- **Reuters / 國際視角：** {{ item.reuters }}
- **The Verge / Big Tech 與產品文化視角：** {{ item.verge }}
- **DIGITIMES / 台灣供應鏈視角：** {{ item.digitimes }}
- **公司可能對策：** {{ item.strategy }}
- **網友或工程師圈回響：** {{ item.social }}
- **Ray 可以在 Podcast 裡怎麼講：** {{ item.podcast }}
- **可信度標籤：** [{{ item.label }}] 來源發布資訊；推論與社群另標。
- **來源連結：**
{% for link in item.links %}  - {{ link }}
{% endfor %}
{% endfor %}{% for slot in empty_slots %}
### {{ slot }}. 目前無法取得
沒有足夠的近期可信來源，保留空位；不以社群傳言或舊聞補足。
{% endfor %}
## 今天可以延伸成 Podcast 的 3 個問題
1. [Analysis] 哪些資訊已有官方文件支持，哪些仍只是媒體報導或社群猜測？
2. [Analysis] 如果趨勢持續，台灣供應鏈的成本、交期與議價能力可能如何改變？
3. [Analysis] 產品使用者與工程師最需要核對的實際限制是什麼？

## 來源取得狀態
{% for result in results %}- {{ result.source }}：{{ result.status }}
{% endfor %}
## 可信度與使用原則
- [Confirmed] 官方發布資訊，或經人工核對、多個可信來源支持的結論。本版不憑相似標題自動判定交叉確認。
- [Reported] 可信媒體報導，尚未完成官方確認。
- [Rumor] 未確認的社群討論線索；不能當事實或代表全體網友。
- [Analysis] 作者的閱讀方向、條件式推論或提問，不是來源已證實的結論。
- 僅使用公開標題與有限 metadata；不繞過付費牆、不輸出全文，請透過來源連結閱讀原文。
"""


def render_report(results: list[SourceResult], output_dir: Path, now: datetime | None = None) -> tuple[Path, str, str]:
    local = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    subject = "還沒想到科技快報 - " + local.strftime("%Y/%m/%d")
    items = [build_item(a, results) for a in select_news(results)]
    env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    body = env.from_string(TEMPLATE).render(subject=subject, generated=local.strftime("%Y-%m-%d %H:%M %Z"),
                                          items=items, empty_slots=range(len(items) + 1, 4), results=results)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{local:%Y-%m-%d}.md"
    path.write_text(body, encoding="utf-8")
    return path, subject, body
