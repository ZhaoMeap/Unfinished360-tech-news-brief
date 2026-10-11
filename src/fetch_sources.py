"""Only retain permitted metadata; never fetch article bodies or bypass access controls."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

MAX_BYTES = 1_000_000
MAX_ITEMS = 30
TOPICS = {
    "AI": ("artificial intelligence", " ai ", "llm", "agent", "openai", "chatgpt", "anthropic", "人工智慧"),
    "半導體": ("semiconductor", "chip", "cpu", "gpu", "memory", "accelerator", "nvidia", "tsmc", "晶片", "半導體", "台積電"),
    "資料中心": ("data center", "datacenter", "server", "bmc", "firmware", "network", "cooling", "power system", "energy efficiency", "資料中心", "伺服器"),
    "Big Tech": ("google", "microsoft", "apple", "amazon", "meta", "alphabet"),
    "監管": ("regulat", "antitrust", "government", "law", "監管", "法規"),
    "產品與平台": ("phone", "software", "platform", "app ", "科技", "technology", "hardware"),
}
OFFICIAL_HOSTS = ("blog.google", "blogs.microsoft.com", "blogs.nvidia.com", "nvidianews.nvidia.com",
                  "apple.com", "about.fb.com", "aboutamazon.com", "openai.com", "tsmc.com",
                  "investor.tsmc.com", "developer.nvidia.com", "huggingface.co", "github.com", "ec.europa.eu", "digital-strategy.ec.europa.eu", "ftc.gov")


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published_at: str | None
    short_snippet: str
    tags: list[str]
    quality_hint: str = ""

    def metadata(self) -> dict:
        return {key: value for key, value in asdict(self).items() if key != "quality_hint"}


@dataclass
class SourceResult:
    source: str
    articles: list[Article]
    status: str


def plain(value: str, limit: int = 180) -> str:
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def safe_url(value: str) -> str | None:
    try:
        if any(ord(char) <= 32 or char in '<>"' for char in value):
            return None
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return None
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return None


def is_official(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host == "github.com":
        return urlsplit(url).path.split("/")[1].lower() in ("nvidia","rocm","openbmc","kubernetes","ollama")
    return any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS)


def tags_for(text: str) -> list[str]:
    lowered = " " + text.lower() + " "
    return [tag for tag, words in TOPICS.items() if any(word in lowered for word in words)]


def published(entry: dict) -> str | None:
    # Missing dates stay missing, rather than being represented as today's news.
    for key in ("published_parsed", "updated_parsed"):
        parts = entry.get(key)
        if parts:
            try:
                return datetime(*parts[:6], tzinfo=timezone.utc).isoformat()
            except (ValueError, TypeError):
                pass
    try:
        date = parsedate_to_datetime(entry.get("published", ""))
        return date.replace(tzinfo=date.tzinfo or timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def recent(date: str | None, now: datetime) -> bool:
    if date is None:
        return False
    try:
        instant = datetime.fromisoformat(date)
        return now - timedelta(hours=48) <= instant <= now + timedelta(minutes=10)
    except ValueError:
        return False


def download(session: requests.Session, url: str) -> bytes:
    if not safe_url(url):
        raise ValueError("來源必須使用 HTTPS，且不得包含帳密")
    with session.get(url, timeout=(5, 12), stream=True) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(16384):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError("來源超過大小限制")
        return bytes(data)


def fetch_feed(session: requests.Session, source: str, url: str, now: datetime,
               official: bool = False) -> SourceResult:
    try:
        parsed = feedparser.parse(download(session, url))
        if not parsed.entries:
            return SourceResult(source, [], "目前無法取得（沒有可解析的 RSS/Atom 項目）")
        articles = []
        seen = set()
        for entry in parsed.entries[:150]:
            link = safe_url(urljoin(url, entry.get("link", "")))
            title = plain(entry.get("title", ""), 220)
            date = published(entry)
            raw_summary = entry.get("summary", "")
            if source == "Hacker News":
                # RSS link points to the external article; comments points to HN.
                discussion_url = safe_url(entry.get("comments", ""))
                if discussion_url and urlsplit(discussion_url).hostname == "news.ycombinator.com":
                    link = discussion_url
            snippet = plain(raw_summary, 160)
            tags = tags_for(title + " " + snippet)
            # Preserve one explicit primary-source link within the same bounded
            # metadata field; do not assume its claims have been verified.
            for anchor in BeautifulSoup(raw_summary, "html.parser").select("a[href]"):
                candidate = safe_url(urljoin(url, anchor.get("href", "")))
                if candidate and is_official(candidate) and len(candidate) <= 150:
                    snippet = plain(raw_summary, 159 - len(candidate)) + " " + candidate
                    break
            if not link or not title or link in seen or not recent(date, now):
                continue
            if official and not is_official(link):
                continue
            if not tags:
                continue
            seen.add(link)
            articles.append(Article(title, link, source, date, snippet, tags, "public summary" if raw_summary and len(plain(raw_summary, 500)) <= 400 else ""))
            if len(articles) >= MAX_ITEMS:
                break
        return SourceResult(source, articles, f"已取得 {len(articles)} 則近 48 小時科技項目" if articles
                            else "目前無法取得（近 48 小時沒有符合主題且有日期的項目）")
    except (requests.RequestException, ValueError) as exc:
        # Do not log response bodies, credentials, or URLs supplied through configuration.
        detail = f"HTTP {exc.response.status_code}" if isinstance(exc, requests.HTTPError) and exc.response is not None else type(exc).__name__
        return SourceResult(source, [], f"目前無法取得（{detail}）")


def fetch_reuters(session: requests.Session, now: datetime) -> SourceResult:
    feed = os.getenv("REUTERS_FEED_URL", "").strip()
    if feed:
        return fetch_feed(session, "Reuters", feed, now)
    url = "https://www.reuters.com/technology/"
    try:
        soup = BeautifulSoup(download(session, url), "html.parser")
        articles = []
        seen = set()
        for anchor in soup.select('a[href*="/technology/"]'):
            link = safe_url(urljoin(url, anchor.get("href", "")))
            title = plain(anchor.get_text(" ", strip=True), 220)
            if not link or urlsplit(link).hostname != "www.reuters.com" or link in seen or len(title) < 25:
                continue
            match = re.search(r"-(\d{4}-\d{2}-\d{2})/", urlsplit(link).path)
            date = match.group(1) + "T00:00:00+00:00" if match else None
            if not recent(date, now):
                continue
            seen.add(link)
            articles.append(Article(title, link, "Reuters", None, "", tags_for(title) or ["科技"]))
            if len(articles) >= MAX_ITEMS:
                break
        return SourceResult("Reuters", articles, f"已取得 {len(articles)} 則公開索引標題（URL 日期僅供候選篩選，published_at 保持未知）" if articles
                            else "目前無法取得（公開索引沒有可用的近期新聞）")
    except (requests.RequestException, ValueError) as exc:
        detail = f"HTTP {exc.response.status_code}" if isinstance(exc, requests.HTTPError) and exc.response is not None else type(exc).__name__
        return SourceResult("Reuters", [], f"目前無法取得（{detail}；不繞過存取限制）")


def fetch_sources(now: datetime | None = None) -> list[SourceResult]:
    now = now or datetime.now(timezone.utc)
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Unfinished360Brief/0.1 (public metadata; personal research)"})
        results = [fetch_reuters(session, now)]
        specs = [
            ("官方：Google", "https://blog.google/rss/", True),
            ("官方：Microsoft", "https://blogs.microsoft.com/feed/", True),
            ("官方：NVIDIA", "https://blogs.nvidia.com/feed/", True),
            ("官方：Apple Newsroom", "https://www.apple.com/newsroom/rss-feed.rss", True),
            ("官方：FTC", "https://www.ftc.gov/feeds/press-release.xml", True),
            ("The Verge", "https://www.theverge.com/rss/index.xml", False),
            ("DIGITIMES", os.getenv("DIGITIMES_FEED_URL", "https://www.digitimes.com/rss/daily.xml"), False),
            ("Hacker News", "https://hnrss.org/frontpage", False),
            ("Reddit", "https://www.reddit.com/r/technology/.rss", False),
        ]
        specs.extend([
            ("官方：NVIDIA Developer", "https://developer.nvidia.com/blog/feed/", True),
            ("官方：Ollama releases", "https://github.com/ollama/ollama/releases.atom", True),
            ("官方：ROCm releases", "https://github.com/ROCm/ROCm/releases.atom", True),
            ("官方：OpenBMC releases", "https://github.com/openbmc/openbmc/releases.atom", True),
            ("官方：Hugging Face", "https://huggingface.co/blog/feed.xml", True),
            ("研究：arXiv AI", "https://rss.arxiv.org/rss/cs.AI", False),
            ("ServeTheHome", "https://www.servethehome.com/feed/", False),
            ("TechNews 台灣", "https://technews.tw/feed/", False),
        ])
        for source, url, official in specs:
            results.append(fetch_feed(session, source, url, now, official))
        results.append(fetch_x())
        return results


def fetch_x() -> SourceResult:
    """Reserved adapter: no scraping, API calls, or fabricated reactions."""
    return SourceResult("X", [], "目前無法取得（介面保留，尚未接入 API）")


def official_links(article: Article) -> list[str]:
    """Only links explicitly exposed in feed metadata; existence is not confirmation."""
    return [url for url in re.findall(r"https://[^\s<>]+", article.short_snippet)
            if safe_url(url) and is_official(url)]
