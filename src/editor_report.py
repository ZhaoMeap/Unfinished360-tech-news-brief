"""Editorial prioritization of accessible evidence, never full-article synthesis."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from .community import Discussion, canonical
from .fetch_sources import Article, SourceResult, is_official
from .render_report import SOCIAL, TAIPEI, md, reference, related
from .source_quality import quality_for
from .story_narrative import describe, engineering_lens
from .explain_report import explain


@dataclass(frozen=True)
class Topic:
    name: str
    pattern: str
    weight: int
    why: str
    big_tech: str
    taiwan: str
    angle: str
    followup: str


TOPICS = (
    Topic('財報與需求訊號', r'earnings|revenue|profit|quarterly|財報|營收|stock price|股價', 1,
          '營收與業務組成可用來檢查 AI 熱度是否轉成需求，不能只看產品宣傳。',
          '可對照雲端公司的資本支出與需求預測，分清已實現業績與指引。',
          '若涉及晶片或伺服器，可檢查台廠營收、毛利與交期是否同步；不能直接推定全面受惠。',
          'AI 熱潮到底進了誰的營收？用業務占比和去年同期比較切入。',
          '需要公司財報原文／月營收公告與法說會資料，核對期間、幣別、基期及 AI 業務定義。'),
    Topic('記憶體成本與裝置定價', r'memory.{0,50}(cost|price)|(cost|price).{0,50}memory|記憶體.{0,20}(成本|價格)', 7,
          '零組件成本可能傳到手機或 PC 定價，是連接供應鏈和使用者預算的具體切口。',
          '若裝置成本上升，品牌可能調整價格或規格；需要產品公告確認，不直接推定雲端影響。',
          '可追記憶體、模組與裝置代工的成本分配；AI server 的供需關聯仍需另外驗證。',
          '一顆記憶體變貴，最後是品牌、供應商還是使用者吸收？',
          '需要品牌價格／規格公告、記憶體供應商財報與公開報價，核對產品種類和期間。'),
    Topic('AI 算力與硬體供應', r'data.?cent[er]+|gpu|server|semiconductor|chip|memory|foundry|資料中心|伺服器|半導體|晶片|記憶體', 8,
          '算力擴張牽動硬體、電力與成本，是連接 AI 產品和實體產業的線索。',
          '若供應或成本變動，可能影響雲端部署與產品定價，需先核對量產和採購時程。',
          '可追晶圓、記憶體、封裝與 AI server 供應鏈；需要訂單或公司公告才可談實際受益。',
          '從一項算力需求往回追：晶片、伺服器到電力，瓶頸在哪一段？',
          '需要官方 press release、產品規格／量產時程與供應商公告，分清計畫、訂單和實際出貨。'),
    Topic('平台監管與市場權力', r'regulat|antitrust|lawsuit|fine\b|ban\b|監管|法規|反壟斷|裁罰', 7,
          '監管可能改變平台競爭規則；提案、調查與判決要分開看。',
          '可能影響預設服務、分發與資料使用權，具體影響取決於法規範圍和生效時間。',
          '若涉及出口或資料規則，台廠可能需調整合規；沒有法規文本不能推定影響特定訂單。',
          '規則一改，誰得到新的入口、誰必須改變商業模式？',
          '需要主管機關法規文件／判決原文、適用地區、生效日期與公司回應。'),
    Topic('AI 代理與信任成本', r'privacy|security|vulnerab|tracking|hallucinat|隱私|安全|幻覺', 10,
          '能做更多事的 AI，也需要更多權限；效用與信任成本值得一起追。',
          '若代理接觸帳號或資料，平台需處理權限、稽核和責任，而不只是宣傳功能。',
          '可能帶動企業部署與安全需求；不能只憑代理產品消息推論新增硬體訂單。',
          '把 AI 當助理時，你願意交出哪些權限，出錯又由誰負責？',
          '需要公司公告、權限／隱私政策、可重現測試與對應 HN 討論串，驗證保護措施。'),
    Topic('AI 模擬與開發流程', r'simulation|omniverse|模擬', 12,
          '模擬工具可能縮短開發迭代，但展示、測試環境與實際部署的差距值得追。',
          '可能影響開發工具與算力服務競爭；要確認工具相容性、費用和可重現效果。',
          '可追製造模擬、機器人與工程服務應用；不能把軟體功能發布直接視為伺服器新訂單。',
          '用模擬先試錯，哪些工程工作可能縮短，哪些仍要實體驗證？',
          '需要官方技術文件、工具版本／授權、測試案例與部署結果；若談供應鏈則另需採購公告。'),
    Topic('AI 代理與工作流程', r'agent|代理', 11,
          '代理工具將 AI 從生成內容帶向執行工作，值得確認它能完成哪些可驗證任務。',
          '可能改變 API、工具整合與開發者生態；權限或安全影響需有額外政策證據。',
          '可追企業導入與軟體整合需求，是否增加硬體支出需要部署規模和設備要求。',
          'AI 代理是在省下一個步驟，還是能可靠完成一整段工作？',
          '需要官方功能公告、支援工具／任務範圍、可重現實測與對應 HN 討論串。'),
    Topic('公司整併與投資布局', r'acquir|merger|buyout|invest|funding|收購|合併|投資', 1,
          '資金與整併透露公司押注的方向，但宣布不等於交易已完成。',
          '若交易落地，可能重排技術、人才或通路資源；先核對條件和完成時間。',
          '可觀察客戶及供應商集中度是否改變，不能把投資金額直接換算成台廠營收。',
          '這筆押注是在買技術、買時間，還是買市場入口？',
          '需要公司／投資人公告、交易條件、監管審查與交割進度。'),
    Topic('AI 應用與研究落地', r'\bai\b|artificial intelligence|clinical|simulation|人工智慧|醫療|模擬', 9,
          '研究與工具提供應用線索，值得檢查是否已有可重現效果，而非把展示當部署。',
          '若效果能被驗證，可能改變產品定位和開發流程；實驗結果不代表普遍可用。',
          '可追軟體、邊緣運算與企業導入需求；硬體關聯需另找規格或採購證據。',
          '從「能展示」到「能日常使用」，中間還差哪些驗證？',
          '需要官方技術文件、研究原文／方法、樣本與限制，或產品實測及上線公告。'),
    Topic('產品與使用者生態', r'phone|gaming|platform|app\b|launch|release|architecture|feature|sdk|compiler|database|產品|遊戲|平台|架構|功能|開發工具', 12,
          '產品變化可作為使用者入口，但要確認是否影響價格、功能或選擇權。',
          '可能改變產品分發、留存或開發者條件；不能僅憑發布消息判斷市場成敗。',
          '若涉及新硬體，可追規格與供應商；平台活動本身不構成半導體需求證據。',
          '使用者今天真正多了什麼選擇，或失去了什麼控制？',
          '需要產品官方公告、價格／地區／上市日期和實測，而非首頁或分類頁。'),
)
FALLBACK = Topic('科技產業觀察', '', 1, '目前只能辨識一個產業觀察項目，先確認它是否有具體事件。',
                 '尚無直接 Big Tech 關聯；需先確認事件主體與平台角色。',
                 '尚無直接台灣產業證據；需要公司、產品或供應鏈文件建立關聯。',
                 '先問這是具體事件、評論，還是產品宣傳？',
                 '需要具體新聞文章的公開摘要、事件日期與公司公告；首頁／分類頁不適合當事件來源。')
HONORS = Topic('科技人物與榮譽', '', 1, '人物與榮譽可觀察公共形象，但不等於產品或產業需求改變。',
               '目前只有公共形象線索，不推定產品、營運或市場變化。',
               '沒有直接訂單或技術關聯；不因人物任職科技公司就推論台廠受益。',
               '先區分科技成果、人物形象與政治象徵，避免把榮譽消息講成產業轉折。',
               '需要授獎單位公告與評選理由；若談商業影響，另需公司營運資料。')


def topic_for(article: Article) -> Topic:
    if re.search(r'medal|honou?r|science prize|頒獎|獎章', article.title, re.I):
        return HONORS
    text = article.title + ' ' + article.short_snippet
    if re.search(r'evaluations?|benchmark|可靠性|評測', text, re.I):
        return Topic('AI 評測與可靠性', '', 11, '評測條件決定結果能否重現。', '', '',
                     'AI 測試能不能偷看答案，怎麼知道測出來的是真本事？',
                     '需要官方評測方法、網路隔離範圍、資料集與失敗案例。')
    found = next((topic for topic in TOPICS if re.search(topic.pattern, text, re.I)), None)
    if found:
        return found
    tags = ' '.join(article.tags)
    return next((topic for topic in TOPICS if re.search(topic.pattern, tags, re.I)), FALLBACK)


def matched_discussions(article: Article, discussions: list[Discussion]) -> list[Discussion]:
    return [d for d in discussions if d.target_url and canonical(d.target_url) == canonical(article.url)]


def score(article: Article, now: datetime, discussions: list[Discussion]) -> float:
    quality = quality_for(article)
    value = topic_for(article).weight * 3 + quality.score
    if article.short_snippet:
        value += 2
    # Explicit technical releases outrank general AI or market stories.
    text = article.title + " " + article.short_snippet
    if topic_for(article).name not in ("財報與需求訊號", "公司整併與投資布局", "科技人物與榮譽") and re.search(r"architecture|new feature|sdk|compiler|new model|開源|新架構|新功能|發布|推出", text, re.I):
        value += 8
    if article.published_at:
        try:
            instant = datetime.fromisoformat(article.published_at).replace(tzinfo=timezone.utc) if len(article.published_at) == 10 else datetime.fromisoformat(article.published_at)
            age = (now - instant.astimezone(timezone.utc)).total_seconds() / 3600
            value += 3 if 0 <= age <= 24 else 1 if 24 < age <= 48 else -10
        except ValueError:
            value -= 3
    else:
        value -= 4
    # Financial adoption evidence is secondary and needs an explicit technical link.
    if topic_for(article).name in ('財報與需求訊號', '公司整併與投資布局'):
        text = article.title + ' ' + article.short_snippet
        if re.search(r'(?:adopt|deploy|ship|customers? using|採用|部署|出貨).{0,60}(?:GPU|server|chip|model|platform|產品|技術)|(?:GPU|server|chip|model|platform|產品|技術).{0,60}(?:adopt|deploy|ship|採用|部署|出貨)', text, re.I):
            value += 6
    if re.search(r'prizes|daily deals|play fest|giveaway|discount|抽獎|促銷', article.title, re.I):
        value -= 40  # Marketing events are not technical releases.
    if re.search(r'keynote|trade show|conference agenda|主題演講|展會預告', article.title, re.I):
        value -= 20  # An event preview alone is not a new technical capability.
    # Community is a tie-breaker for editorial interest, never proof of a claim.
    value += min(2, sum(bool(d.sampled) for d in matched_discussions(article, discussions)))
    if re.search(r'\brumou?r\b|傳聞', article.title, re.I):
        value -= 3
    return value


def rank_candidates(results, now, discussions):
    candidates = []
    for result in results:
        for article in result.articles:
            if article.source in SOCIAL:
                continue
            if any(related(article, other) for other in candidates):
                # Keep the more informative candidate, retain other references in gaps.
                index = next(i for i, other in enumerate(candidates) if related(article, other))
                if score(article, now, discussions) > score(candidates[index], now, discussions):
                    candidates[index] = article
            else:
                candidates.append(article)
    candidates.sort(key=lambda a: (-score(a, now, discussions), a.url))
    chosen = []
    while candidates and len(chosen) < 3:
        def adjusted(a):
            return score(a, now, discussions) - 6 * sum(topic_for(a).name == topic_for(c).name for c in chosen) - 8 * sum(a.source == c.source for c in chosen)
        best = max(candidates, key=adjusted)
        chosen.append(best)
        candidates.remove(best)
    return chosen, candidates[:5]


def social_summary(article, discussions):
    linked = matched_discussions(article, discussions)
    if not linked:
        return '沒有取得對應這篇文章的 Hacker News／Reddit 公開討論；X 尚未接入。不將同主題留言硬湊成此事件回響。'
    lines = []
    for discussion in linked[:2]:
        themes = '、'.join(f'{name} {count} 位' for name, count in sorted(discussion.themes.items(), key=lambda x: -x[1])[:2])
        concerns = '、'.join(name for name, count in discussion.concerns.items() if count >= 2)
        if not discussion.sampled:
            lines.append(f'{discussion.source} 無可用留言；需要可讀的公開留言 RSS／API。')
        else:
            lines.append(f'{discussion.source} 抽樣 {discussion.sampled} 位：' + (themes or '未分類主題') +
                         ('；樣本擔憂：' + concerns if concerns else '；不足以稱為共同擔憂') + '。')
    return '[Rumor] ' + ' '.join(lines) + '樣本不代表共識，留言不是事實。'


def make_story(article, discussions):
    topic = topic_for(article)
    quality = quality_for(article)
    official = article.source.startswith('官方：') and is_official(article.url)
    label = 'Confirmed' if official and article.short_snippet else 'Reported' if article.source in ('Reuters','The Verge','DIGITIMES') else 'Analysis'
    return dict(article=article, title=md(article.title[:150]), ref=reference(article), topic=topic,
                quality=quality, label=label, explanation=explain(article, topic, label), has_discussion=any(d.sampled for d in matched_discussions(article, discussions)), narrative=describe(article, topic), engineering=engineering_lens(article, topic), social=md(social_summary(article, discussions)),
                publishable=bool(article.short_snippet) and quality.score >= 2 and topic != FALLBACK)


def main_thread(chosen, results):
    if not chosen:
        return ['[Analysis] 今天沒有可用的非社群候選，無法提出有來源支撐的科技主線。',
                '[Analysis] 目前只能辨識來源取得問題，不能把資料缺失解讀成產業沒有新進展。',
                '[Analysis] 下一步先恢復公開 RSS 或加入具體文章連結，再做編輯選題。']
    counts = Counter(topic_for(a).name for r in results for a in r.articles if a.source not in SOCIAL)
    themes = list(dict.fromkeys(topic_for(a).name for a in chosen))
    links = '、'.join(reference(a) for a in chosen[:2])
    sentences = [f'[Analysis] 今日候選較值得連起來看的是「{"、".join(themes)}」，依據為 {links}。',
                 f'[Analysis] 候選裡「{themes[0]}」出現 {counts[themes[0]]} 次；這只是當次來源分布，不是全市場熱度或獨立證據數。']
    if len(themes) > 1:
        sentences.append('[Analysis] 可能主線是：從工具能做哪一步，追到權限、可重現測試與實際部署的限制；這是編輯提問，不是候選之間已有因果關係。')
    else:
        sentences.append(f'[Analysis] 可能主線是「{themes[0]}」從宣布走向可驗證結果還有哪些門檻；需以官方文件檢驗。')
    sentences.append('[Analysis] 依據僅為標題、公開短摘錄與有限樣本，來源覆蓋不完整；不能據此判定已出現普遍產業趨勢。')
    return sentences


def data_gaps(results, discussions):
    gaps = []
    for result in results:
        if not result.articles or any(word in result.status for word in ('目前無法取得','待人工補充')):
            gaps.append(f'{md(result.source)}：{md(result.status)}')
        elif all(quality_for(a).kind in ('metadata','title only') for a in result.articles) and result.source not in SOCIAL:
            gaps.append(f'{md(result.source)}：只有 metadata／標題，缺少官方文件或完整公開摘要。')
    for discussion in discussions:
        if discussion.status or not discussion.sampled:
            gaps.append(f'{discussion.source} 留言：{md(discussion.status or "沒有可用樣本")} — [討論串](<{discussion.url}>)')
    return gaps


TEMPLATE = '''Subject: {{ subject }}

# 今日科技主線
{% for sentence in thread %}{{ sentence }}

{% endfor %}# 今天最值得追的 3 則新聞
{% for story in stories %}
## {{ loop.index }}. {{ story.title }}
- **來源：** {{ story.ref }}；{{ story.article.published_at or '日期未知' }}；{{ story.quality.kind }} / {{ story.quality.score }}，資訊程度{{ story.quality.availability }}。
- **可信度標籤：** [{{ story.label }}] 僅標示來源發布資訊；metadata 不等於事件已確認，推論另標 [Analysis]。

### 1. 先講人話：這篇新聞在講什麼？
{{ story.explanation.sentences|map('escape_md')|join(' ') }}

### 2. 背景補充：工程小白需要先懂什麼？
{% for background in story.explanation.background %}- [Background] {{ background|escape_md }}
{% endfor %}
### 3. 工程師應該注意什麼？
[Analysis] {{ story.explanation.attention|escape_md }}

### 4. 目前可能的解法或業界方向
{{ story.explanation.solution|escape_md }}

### 5. 網路上的人可能會怎麼看？
{% if story.has_discussion %}{{ story.social }}
{% else %}沒有取得對應文章的可用 HN／Reddit 留言；X 尚未接入。以下是工程師可能提問，不是實際網友發言。
{% for question in story.explanation.questions %}- [Analysis] {{ question|escape_md }}
{% endfor %}{% endif %}
### 6. Ray 的 Podcast 切入角度
[Analysis] {{ story.explanation.opening|escape_md }}

### 7. 仍需查證的地方
{% for gap in story.explanation.gaps %}- {{ gap|escape_md }}
{% endfor %}
- **來源連結：** {{ story.ref }}

{% else %}
沒有可用新聞，不用社群或空位湊滿三則；先補可讀的具體文章來源。
{% endfor %}
# 其他候選新聞
{% for article in others %}- [Analysis] 觀察：{{ article.title|escape_md }} — {{ article|ref }}（{{ article|quality_name }}）
{% else %}沒有額外候選；不複製前三則充數。
{% endfor %}{% if others|length < 5 %}本次只有 {{ others|length }} 則其他候選；不足五則不編造。
{% endif %}
# 今日資料缺口
{% for gap in gaps %}- {{ gap }}
{% else %}- 未觀察到來源取得失敗；仍需依各新聞清單核對官方文件與具體數字。
{% endfor %}- 公開 metadata 與留言樣本不能替代事實查核；候選分布受 feed 範圍、日期篩選與選題規則影響。

# Ray 今天可以怎麼用
1. **Podcast：** [Analysis] {{ podcast }}
2. **IG / Threads：** [Analysis] {{ social_post }}
3. **只觀察、不公開講：** [Analysis] {{ observe }}

# 使用原則
[Background] 是一般工程知識，不是本次新聞事實；[Analysis] 是工程推論或提問。來源事實以 [Reported]／[Confirmed] 標示；官方發布不代表效果已獨立驗證。完整文章如需補查，請透過來源合法閱讀。程式不繞過付費牆、不抓全文、不輸出全文。

> Editor Mode：規則式編輯判斷，非全文分析；自動候選為最近 48 小時可取得的項目。Engineering Lens：優先技術／產品、工程挑戰與應用限制；財務消息降級。另考量時效、來源品質與多樣性；社群只作極小的興趣加分，不是查證依據。不繞過付費牆，不輸出全文。台灣時間 {{ generated }}。
'''


def render_editor_report(results: list[SourceResult], output_dir: Path, now: datetime | None = None,
                         discussions: list[Discussion] | None = None):
    local = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    discussions = discussions or []
    chosen, others = rank_candidates(results, local.astimezone(timezone.utc), discussions)
    stories = [make_story(a, discussions) for a in chosen]
    usable = sorted([s for s in stories if s['publishable']], key=lambda s: score(s["article"], local.astimezone(timezone.utc), discussions), reverse=True)
    podcast = (f'優先 {usable[0]["title"]}：{md(usable[0]["engineering"]["opening"])} 先核對官方文件再錄音。' if usable
               else '目前沒有足夠公開資訊可作新聞解說；先補具體公司公告，可用選題問題準備訪談。')
    social_post = (f'可用 {usable[-1]["title"]} 做一個來源連結加一個問題的短貼文；用條件式說明影響，不寫成已證實結論。' if usable
                   else '先分享編輯提問與來源限制，不發布事件斷言。')
    weak = next((a for a in chosen + others if quality_for(a).availability == '低' or re.search(r'rumou?r|傳聞',a.title,re.I)), None)
    observe = (f'{md(weak.title[:150])}：只有有限資訊或含傳聞訊號，需要公司公告／可信媒體交叉核對後才講。' if weak
               else '所有未經驗證的功能、效能和自動化能力推論，只留作觀察，不當事實公開講。')
    env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    env.filters.update(escape_md=md, ref=reference, quality_name=lambda a: quality_for(a).kind)
    subject = '還沒想到科技編輯簡報 - ' + local.strftime('%Y/%m/%d')
    body = env.from_string(TEMPLATE).render(subject=subject, thread=main_thread(chosen,results), stories=stories,
        others=others, gaps=data_gaps(results,discussions), podcast=podcast, social_post=social_post, observe=observe,
        generated=local.strftime('%Y-%m-%d %H:%M %Z'))
    daily_dir = output_dir / 'daily'
    daily_dir.mkdir(parents=True,exist_ok=True)
    path = daily_dir / f'{local:%Y-%m-%d_%H%M}_editor.md'
    path.write_text(body,encoding='utf-8')
    return path,subject,body
