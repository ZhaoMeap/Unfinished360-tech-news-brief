"""Conservative evidence levels: accessibility and event detail, not popularity."""
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .community import canonical
from .fetch_sources import is_official
from .story_narrative import COMPANIES, product_names

ACTIONS = r'launch|releas|announc|introduc|unveil|patch|isolat|evaluat|cutting off|tamper|theft|vulnerab|study|benchmark|deploy|manufactur|發布|推出|評測|修補|竄改|測試|研究'
EXTRA = {'Ollama':['Ollama'], 'Hugging Face':['Hugging Face','HuggingFace'], 'Ledger':['Ledger'], 'AMD':['AMD'], 'Intel':['Intel'], 'TSMC':['TSMC','台積電'],
         'Linux Foundation':['Linux Foundation'], 'OpenBMC':['OpenBMC'], 'Kubernetes':['Kubernetes']}


def subjects(article):
    """Article subjects never fall back to the publishing outlet or blog owner."""
    text = article.title + ' ' + article.short_snippet
    names = dict((value,[key,value]) for key,value in COMPANIES.items())
    names.update(EXTRA)
    return [name for name,aliases in names.items() if any(re.search(r'(?<![A-Za-z0-9])'+re.escape(a)+r'(?![A-Za-z0-9])',text,re.I) for a in aliases)]


@dataclass(frozen=True)
class Evidence:
    level: str
    label: str
    reason: str


def assess(article):
    if article.source in ('Hacker News','Reddit','X'):
        return Evidence('C','Rumor','社群是討論樣本，不是新聞事實')
    if re.search(r'what to expect|\brumou?rs?\b|we (?:are )?expect|預測|傳聞|展會預告', article.title+' '+article.short_snippet,re.I):
        return Evidence('C','Reported','內容是預告／傳聞或預期，尚不是已發生且可核對的產品事件')
    snippet = re.sub(r'https://\S+','',article.short_snippet).strip()
    if article.quality_hint not in ('public summary','official summary'):
        return Evidence('C','Reported','只有標題／metadata；未取得足以支持事件解說的公開摘要')
    if len(snippet) < 70 or not re.search(ACTIONS,article.title+' '+snippet,re.I) or not (subjects(article) or product_names(article.title+' '+snippet)):
        return Evidence('C','Reported','公開線索仍缺少可辨識主體、動作或事件細節')
    if is_official(article.url) and article.source.startswith('官方：'):
        return Evidence('A','Confirmed','官方公開摘要有主體、動作與事件細節；只確認來源主張，不表示獨立實測')
    return Evidence('B','Reported','公開摘要有可辨識事件細節，尚未核對一手文件')


def event_id(article):
    return 'evt-'+hashlib.sha256(canonical(article.url).encode('utf-8')).hexdigest()[:20]


def coverage(articles):
    # Domains, not arbitrary source labels, approximate independent coverage.
    return len({(urlsplit(a.url).hostname or '').lower().removeprefix('www.') for a in articles})
