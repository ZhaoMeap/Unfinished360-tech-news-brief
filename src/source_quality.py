"""Quality measures accessible evidence, not truth or independent confirmation."""
from dataclasses import dataclass

from .fetch_sources import Article, is_official


@dataclass(frozen=True)
class Quality:
    kind: str
    score: int
    availability: str


def quality_for(article: Article) -> Quality:
    if article.source in ("Hacker News", "Reddit", "X"):
        return Quality("community discussion", 0, "中" if article.short_snippet else "低")
    if not article.short_snippet.strip():
        return Quality("title only", 1, "低")
    if article.source.startswith("官方：") and is_official(article.url):
        return Quality("official source", 4, "高")
    if article.quality_hint == "public summary":
        return Quality("public summary", 3, "中")
    return Quality("metadata", 2, "中")
