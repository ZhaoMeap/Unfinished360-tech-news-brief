"""Read only bounded HTML head metadata, never article-body extraction."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .fetch_sources import Article, SourceResult, is_official, plain, safe_url, tags_for

MAX_LINKS = 20
HEAD_LIMIT = 96_000


def validate_public_url(url: str) -> str:
    valid = safe_url(url)
    if not valid:
        raise ValueError("只接受無帳密的 HTTPS URL")
    parts = urlsplit(valid)
    if parts.port not in (None, 443):
        raise ValueError("只接受 HTTPS 標準埠")
    host = parts.hostname
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("不接受本機或內部網址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("不接受私有或保留 IP")
    # Cloud resolves destination DNS inside its HTTPS egress proxy. Local DNS
    # can be unavailable even when HTTPS works. Preserve that supported route;
    # the proxy owns hostname resolution and destination policy enforcement.
    proxies = requests.utils.get_environ_proxies(valid)
    if proxies.get("https") or proxies.get("all"):
        return valid
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("來源 DNS 無法解析") from exc
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("不接受私有或保留 IP")
    return valid


def read_links(path: Path) -> list[str]:
    if path.stat().st_size > 64_000:
        raise ValueError("連結檔過大（上限 64 KB）")
    urls = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not safe_url(line):
            raise ValueError(f"第 {number} 行不是有效 HTTPS URL（不得含帳密）")
        if line not in urls:
            urls.append(line)
    if not urls or len(urls) > MAX_LINKS:
        raise ValueError(f"請提供 1–{MAX_LINKS} 個不同 HTTPS URL")
    return urls


def download_head(session: requests.Session, url: str) -> tuple[bytes, str]:
    for _ in range(4):
        url = validate_public_url(url)
        with session.get(url, timeout=(5, 12), stream=True, allow_redirects=False,
                         headers={"Range": f"bytes=0-{HEAD_LIMIT - 1}"}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                raise ValueError("僅支援 HTML head metadata；不下載 PDF 或其他全文文件")
            data = bytearray()
            for chunk in response.iter_content(2048):
                data.extend(chunk[:HEAD_LIMIT - len(data)])
                match = re.search(br"</head\s*>|<body(?:\s|>)", data, re.I)
                if match:
                    return bytes(data[:match.start()]), url
                if len(data) >= HEAD_LIMIT:
                    break
            if re.search(br"<head(?:\s|>)", data, re.I):
                # Large heads are parsed partially, never followed into the body.
                return bytes(data), url
            raise ValueError("沒有可用的 HTML head，或超過讀取上限")
    raise ValueError("重新導向過多")


def normalize_date(value: str) -> str | None:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # A date with no timezone is not assigned a fabricated precise timezone.
        return instant.isoformat() if instant.tzinfo else instant.date().isoformat()
    except (ValueError, TypeError):
        return None


def parse_head(head: bytes, url: str) -> Article:
    soup = BeautifulSoup(head, "html.parser")

    def meta(*names):
        for name in names:
            node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if node and node.get("content"):
                return plain(node["content"], 500)
        return ""

    title = meta("og:title", "twitter:title") or plain(soup.title.get_text() if soup.title else "", 220)
    description = meta("description", "og:description", "twitter:description")
    summary = meta("abstract", "summary")
    date = meta("article:published_time", "datePublished", "date")
    # Read description/date only: articleBody, text and paywall data are ignored.
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.string or node.get_text())
        except (ValueError, TypeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            for candidate in [item] + (item.get("@graph", []) if isinstance(item.get("@graph"), list) else []):
                if not isinstance(candidate, dict):
                    continue
                kind = candidate.get("@type", "")
                if not any(k in str(kind) for k in ("Article", "NewsArticle", "BlogPosting")):
                    continue
                if candidate.get("isAccessibleForFree") in (False, "False", "false"):
                    continue
                value = candidate.get("description")
                if isinstance(value, str):
                    summary = summary or plain(value, 500)
                published = candidate.get("datePublished")
                if isinstance(published, str):
                    date = date or published
    host = urlsplit(url).hostname
    source_names = {"reuters.com": "Reuters", "theverge.com": "The Verge", "digitimes.com": "DIGITIMES",
                    "reddit.com": "Reddit", "news.ycombinator.com": "Hacker News"}
    source = next((name for domain, name in source_names.items() if host == domain or host.endswith("." + domain)), host)
    if is_official(url):
        source = "官方：" + host
    snippet = plain(summary or description, 400)
    hint = "public summary" if summary else "metadata" if snippet else "title only"
    return Article(title or "待人工補充（頁面未提供標題）", url, source, normalize_date(date), snippet,
                   tags_for(title + " " + snippet), hint)


def fetch_links(urls: list[str]) -> list[SourceResult]:
    results = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Unfinished360Brief/0.2 (head metadata only)"})
        for url in urls:
            try:
                head, final_url = download_head(session, url)
                article = parse_head(head, final_url)
                results.append(SourceResult(article.source, [article], "已取得指定連結公開資訊"))
            except (requests.RequestException, ValueError) as exc:
                code = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else type(exc).__name__
                # Preserve the requested link even when unavailable; no invented title/date.
                results.append(SourceResult(urlsplit(url).hostname, [Article("待人工補充", url, urlsplit(url).hostname,
                                             None, "", [], "title only")], f"待人工補充（{code}）"))
    return results
