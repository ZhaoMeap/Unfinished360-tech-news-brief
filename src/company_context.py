"""Local, reviewable company background cache; never scrape company pages."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from .fetch_sources import is_official
from .story_narrative import COMPANIES

CACHE = Path(__file__).resolve().parents[1] / 'data/company_profiles'
REQUIRED = ('name','company_type','core_business','main_products','customer_segments',
            'industry_position','why_it_matters','sources','last_updated')
RANKING = r'世界第一|全球最大|市場龍頭|全球第一|市佔|市場份額|market leader|largest|number one|#1'


def mentioned(alias, text):
    return bool(re.search(r'(?<![A-Za-z0-9])'+re.escape(alias)+r'(?![A-Za-z0-9])',text,re.I))


def load_profiles(folder: Path = CACHE):
    profiles = []
    for path in sorted(folder.glob('*.json')):
        try:
            if path.stat().st_size > 50_000:
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or any(k not in data for k in REQUIRED):
                continue
            if not all(isinstance(data[k],str) and data[k].strip() for k in
                       ('name','company_type','core_business','industry_position','why_it_matters','last_updated')):
                continue
            if not all(isinstance(data[k],list) and all(isinstance(v,str) for v in data[k])
                       for k in ('aliases','main_products','customer_segments','sources')):
                continue
            date.fromisoformat(data['last_updated'])
            data['sources'] = [u for u in data['sources'] if urlsplit(u).scheme=='https' and not urlsplit(u).username]
            # This V1 never renders rankings, even if manually entered in cache.
            for key in ('industry_position','core_business','why_it_matters'):
                if re.search(RANKING,data[key],re.I):
                    data[key] = '目前僅能確認其公開定位，缺少可驗證排名資料。'
            profiles.append(data)
        except (OSError,UnicodeError,ValueError,TypeError,KeyError):
            continue
    return profiles


def company_cards(article, folder: Path = CACHE):
    profiles = load_profiles(folder)
    text = article.title + ' ' + article.short_snippet
    publisher = ''  # Publication owner is not evidence of the event subject.
    cards = []
    for profile in profiles:
        aliases = [profile['name']] + profile['aliases']
        in_story = any(mentioned(alias,text) for alias in aliases)
        by_publisher = any(mentioned(alias,publisher) for alias in aliases)
        if not (in_story or by_publisher):
            continue
        data = dict(profile)
        # Cache facts are curated background, not freshly verified official claims.
        data['relevance'] = ('[Reported] 本次取得的標題／摘要點名這家公司；這次具體動作見下一段。' if in_story else
                             '[Confirmed] 本次資訊由這家公司的官方來源發布；發布者不一定是事件唯一主體。')
        data['fallback'] = False
        cards.append(data)
    covered = {alias.lower() for p in cards for alias in [p['name']]+p['aliases']}
    for alias,name in COMPANIES.items():
        if (mentioned(alias,text) or mentioned(name,text) or mentioned(alias,publisher)) and alias.lower() not in covered and name.lower() not in covered:
            cards.append(dict(name=name,fallback=True))
            covered.update((alias.lower(),name.lower()))
    if not cards:
        cards.append(dict(name='本次來源尚未辨識出可核對的公司主體',fallback=True))
    return cards[:3]
