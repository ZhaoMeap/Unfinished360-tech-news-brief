"""Bounded public comment sampling; retain theme counts, never comment text."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

from .fetch_sources import Article, SourceResult, download, plain, safe_url

MAX_COMMENTS = 6
THEMES = {
    "隱私與資料使用": r"privacy|private data|tracking|surveillance|隱私|個資",
    "成本與定價": r"pricing|cost|expensive|subscription|成本|定價|昂貴",
    "可靠性與安全": r"hallucinat|reliab|security|vulnerab|unsafe|安全|幻覺|可靠",
    "效能與硬體需求": r"latency|benchmark|performance|gpu|memory|效能|延遲|記憶體",
    "整合與可攜性": r"api\b|deploy|lock.in|open.source|compatib|整合|部署|開源",
    "工作與使用體驗": r"jobs|layoff|usability|workflow|工作|裁員|使用體驗",
}
CONCERNS = r"concern|worr|risk|expensive|unsafe|problem|fail|bug|lock.in|擔憂|風險|問題|昂貴"
TECHNICAL = r"\b(api|deploy\w*|benchmark\w*|latency|gpu|memory|open.source|test\w*)\b|部署|測試|效能|開源"


@dataclass
class Discussion:
    source: str
    url: str
    title: str
    target_url: str = ""
    sampled: int = 0
    total: int | None = None
    themes: dict[str, int] = field(default_factory=dict)
    concerns: dict[str, int] = field(default_factory=dict)
    technical: dict[str, int] = field(default_factory=dict)
    status: str = ""


def canonical(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in ("fbclid", "gclid")]
    return urlunsplit((parts.scheme, (parts.hostname or "").lower().removeprefix("www."), parts.path.rstrip("/"), urlencode(sorted(query)), ""))


def summarize_comments(discussion: Discussion, comments: list[tuple[str, str]]) -> Discussion:
    themes, concerns, technical = Counter(), Counter(), Counter()
    seen = set()
    for author, raw in comments[:MAX_COMMENTS]:
        if not author or author in seen:
            continue
        text = plain(raw, 600).lower()
        if not text:
            continue
        seen.add(author)
        for theme, pattern in THEMES.items():
            if re.search(pattern, text, re.I):
                themes[theme] += 1
                if re.search(CONCERNS, text, re.I):
                    concerns[theme] += 1
                if re.search(TECHNICAL, text, re.I):
                    technical[theme] += 1
    discussion.sampled = len(seen)
    discussion.themes = dict(themes)
    discussion.concerns = dict(concerns)
    discussion.technical = dict(technical)
    return discussion


def json_get(session, url):
    value = json.loads(download(session, url))
    if value is not None and not isinstance(value, dict):
        raise ValueError("公開 API 回應格式不符")
    return value


def hn_discussion(session, article: Article) -> Discussion:
    discussion = Discussion("Hacker News", article.url, article.title)
    try:
        match = re.search(r"(?:\?|&)id=(\d+)", article.url)
        if not match or urlsplit(article.url).hostname != "news.ycombinator.com":
            discussion.status = "待人工補充（RSS 未提供 HN 討論串 ID）"
            return discussion
        story = json_get(session, f"https://hacker-news.firebaseio.com/v0/item/{match.group(1)}.json") or {}
        if story.get("type") != "story":
            discussion.status = "待人工補充（非新聞討論串）"
            return discussion
        discussion.target_url = safe_url(story.get("url", "")) or ""
        total = story.get("descendants")
        discussion.total = total if isinstance(total, int) else None
        comments = []
        for identifier in story.get("kids", [])[:MAX_COMMENTS]:
            if not isinstance(identifier, int):
                continue
            item = json_get(session, f"https://hacker-news.firebaseio.com/v0/item/{identifier}.json") or {}
            if not item.get("deleted") and not item.get("dead") and item.get("type") == "comment":
                comments.append((item.get("by", ""), item.get("text", "")))
        return summarize_comments(discussion, comments)
    except (requests.RequestException, ValueError, TypeError):
        discussion.status = "待人工補充（公開討論 API 不可用）"
        return discussion


def reddit_discussion(session, article: Article) -> Discussion:
    discussion = Discussion("Reddit", article.url, article.title)
    parts = urlsplit(article.url)
    if parts.hostname not in ("www.reddit.com", "reddit.com") or not re.match(r"^/r/[\w]+/comments/[\w]+", parts.path):
        discussion.status = "待人工補充（RSS 未提供 Reddit 討論串）"
        return discussion
    try:
        url = urlunsplit(("https", parts.netloc, parts.path.rstrip("/") + "/.rss", "", ""))
        feed = feedparser.parse(download(session, url))
        comments = []
        for entry in feed.entries[:MAX_COMMENTS + 1]:
            # The first entry is the submission, not a comment.
            if not re.search(r"/comments/[^/]+/[^/]+/[^/]+", urlsplit(entry.get("link", "")).path):
                for anchor in BeautifulSoup(entry.get("summary", ""), "html.parser").select("a[href]"):
                    target = safe_url(anchor.get("href", ""))
                    if target and anchor.get_text(strip=True).lower() == "[link]" and urlsplit(target).hostname not in ("reddit.com", "www.reddit.com"):
                        discussion.target_url = target
                continue
            comments.append((entry.get("author", ""), entry.get("summary", "")))
        if not comments:
            discussion.status = "待人工補充（沒有可解析的公開留言）"
        return summarize_comments(discussion, comments)
    except (requests.RequestException, ValueError):
        discussion.status = "待人工補充（公開留言 RSS 不可用）"
        return discussion


def collect_community(results: list[SourceResult]) -> list[Discussion]:
    discussions = []
    # At most two threads per service, six top-level comments per thread.
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Unfinished360Brief/0.2 (bounded public discussion sample)"})
        for source, adapter in (("Hacker News", hn_discussion), ("Reddit", reddit_discussion)):
            candidates = [a for r in results for a in r.articles if a.source == source]
            candidates.sort(key=lambda a: -len(set(a.tags) & {"AI", "半導體", "資料中心"}))
            candidates = candidates[:2]
            for article in candidates:
                discussions.append(adapter(session, article))
    return discussions
