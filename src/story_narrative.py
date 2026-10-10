"""Paraphrase explicit metadata claims; keep explanations and gaps separate."""
from __future__ import annotations

import re
from decimal import Decimal

from .fetch_sources import Article

COMPANIES = {'Zhen Ding': '臻鼎', 'Phison': '群聯', 'NVIDIA': 'NVIDIA', 'OpenAI': 'OpenAI',
             'Google': 'Google', 'Microsoft': 'Microsoft', 'Amazon': 'Amazon', 'Apple': 'Apple',
             'Meta': 'Meta', 'Huawei': '華為', 'Intel': 'Intel', 'Samsung': 'Samsung', 'AMD': 'AMD',
             'Advantech': '研華', 'Innodisk': '宜鼎', 'Apacer': '宇瞻', 'FTC': '美國 FTC'}
MONTHS = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,'July':7,'August':8,
          'September':9,'October':10,'November':11,'December':12}
PRODUCTS = ('Omniverse', 'Dots', 'AMIE', 'ChatGPT', 'Claude', 'Gemini', 'Foveros', 'HBM4E', 'RTX 5090')


def entities(text):
    found = [(match.start(), value) for name, value in COMPANIES.items()
             if (match := re.search(r'\b' + re.escape(name) + r'\b', text, re.I))]
    return [value for _, value in sorted(found)]


def product_names(text):
    names = [name for name in PRODUCTS if re.search(r'\b' + re.escape(name) + r'\b', text, re.I)]
    names += re.findall(r'\b(?:GPT-\d[\w.-]*|RTX\s?\d{4})\b', text)
    # Accept an unfamiliar product only when the source explicitly names it.
    names += re.findall(r'\b(?:called|named)\s+([A-Z][\w-]{1,24})', text)
    return list(dict.fromkeys(names))[:3]


def financial_numbers(text):
    claims = []
    # Preserve the metric/number relationship, not a bag of detached numbers.
    money = re.search(r'\brevenue\s+(?:reached|of|was|totaled)\s+(NT\$|US\$|USD\s*)(\d+(?:\.\d+)?)\s+(billion|million)', text, re.I)
    if money:
        currency, amount, scale = money.groups()
        factor = Decimal('10') if scale.lower() == 'billion' else Decimal('0.01')
        converted = format(Decimal(amount) * factor, 'f').rstrip('0').rstrip('.') if '.' in format(Decimal(amount) * factor, 'f') else format(Decimal(amount) * factor, 'f')
        claims.append('營收達' + ('新台幣' if currency.upper() == 'NT$' else '美元') + converted + '億元')
    annual = re.search(r'\bup\s+(\d+(?:\.\d+)?)%\s+year[ -]over[ -]year', text, re.I)
    if annual:
        claims.append('較去年同期增加' + annual.group(1) + '%')
    monthly = re.search(r'(\d+(?:\.\d+)?)%\s+from\s+(' + '|'.join(MONTHS) + r')\b', text, re.I)
    if monthly:
        month = next(v for k,v in MONTHS.items() if k.lower() == monthly.group(2).lower())
        prefix = text[:monthly.start()]
        direction = '增加' if re.search(r'\bup\s*$',prefix,re.I) else '減少' if re.search(r'\bdown\s*$',prefix,re.I) else None
        if not direction and annual and re.fullmatch(r'\s*(?:,\s*)?and\s*',text[annual.end():monthly.start()],re.I):
            direction = '增加'
        claims.append(f'較{month}月{direction or "變動"}{monthly.group(1)}%' + ('（摘錄未明示方向）' if not direction else ''))
    if re.search(r'\bAI\s+tops\s+half\s+of\s+sales\b', text, re.I):
        claims.append('AI 相關銷售占比超過一半')
    return claims


def event_period(text):
    match = re.search(r'\b(' + '|'.join(MONTHS) + r')\s+(20\d{2})\b', text, re.I)
    if match:
        month = next(v for k,v in MONTHS.items() if k.lower() == match.group(1).lower())
        return f'{match.group(2)}年{month}月'
    match = re.search(r'\b(' + '|'.join(MONTHS) + r')\b', text, re.I)
    if match:
        month = next(v for k,v in MONTHS.items() if k.lower() == match.group(1).lower())
        return f'{month}月（來源未明示年份）'
    return None


def describe(article: Article, topic):
    # URLs and their numeric IDs are not evidence about an event.
    text = re.sub(r'https://\S+', '', article.title + ' ' + article.short_snippet)
    actors = entities(text + (' ' + article.source if article.source.startswith('官方：') else ''))
    actor = '、'.join(actors[:2]) or '來源未具名的公司或主體'
    products = product_names(text)
    period = event_period(text)
    date = (article.published_at or '')[:10]
    financial = topic.name == '財報與需求訊號'
    simulation = bool(re.search(r'omniverse|simulation|模擬', text, re.I))
    agent = bool(re.search(r'\bagents?\b|代理', text, re.I))
    privacy = bool(re.search(r'privacy|隱私', text, re.I))
    sentences = []

    if financial:
        action = '公布營收／銷售新高的消息' if re.search(r'record.*(?:sales|revenue)|(?:sales|revenue).*record|營收.*新高', text,re.I) else '被報導營收或銷售表現'
        sentences.append(f'[Reported] 這篇報導在說{actor}{action}，不是單純介紹一個新產品。')
        segments = []
        if re.search(r'mobile|smartphone|手機',text,re.I): segments.append('行動裝置需求')
        if re.search(r'\bAI\b|人工智慧',text,re.I): segments.append('AI 相關應用')
        sentences.append('[Reported] 標題把這項營收消息連到' + '、'.join(segments) + '，但沒有提供各類產品的完整收入拆分。' if segments
                         else '[Reported] 目前摘要沒有交代哪些產品或客戶構成這項營收，需要對照產品組合。')
    elif simulation:
        sentences.append(f'[Reported] {actor}的這篇資訊在談如何把模擬構想做成能運作的應用' + ('，標題把 AI 代理列為其中的工具。' if agent else '。'))
        steps = []
        for pattern, label in ((r'assembl\w* assets','準備場景素材'),(r'physics','接上物理模擬'),(r'rendering','接上畫面渲染'),(r'checking.*scene|scene behaves','檢查場景是否按預期運作')):
            if re.search(pattern,text,re.I): steps.append(label)
        sentences.append('[Reported] 公開摘要具體提到的工作有' + '、'.join(steps) + '，它描述的是開發流程。' if steps
                         else '[Reported] 來源沒有列出工具能完成哪些模擬步驟，不能直接說它已替代工程師。')
    elif agent and privacy:
        launched = re.search(r'\b(unveiled|introduced|launched)\b', text,re.I)
        subject_product = '、'.join(products) if products else '未具名的 AI 代理'
        if launched:
            sentences.append(f'[Reported] 公開摘要說{actor}對外發表了{subject_product}，報導把焦點放在這類代理的隱私承諾。')
        else:
            sentences.append('[Reported] 這篇報導檢查 AI 代理製作者的隱私承諾能否兌現，標題本身不是已驗證保護措施有效的結果。')
        speakers = []
        if re.search(r'Sam Altman',text,re.I): speakers.append('Sam Altman')
        if re.search(r'DevDay',text,re.I): speakers.append('DevDay 發表場合')
        sentences.append('[Reported] 摘錄提到' + '與'.join(speakers) + '，但沒有交代資料保存、第三方傳輸或刪除規則。' if speakers
                         else '[Reported] 目前沒有完整的公司承諾或實測內容，不能判定哪些資料真的受到保護。')
    elif topic.name == '記憶體成本與裝置定價':
        sentences.append(f'[Reported] 報導把{actor}的裝置價格調整與記憶體成本連在一起。')
        sentences.append('[Reported] 這是零組件成本與售價的消息，摘要不足以說明哪些機型、容量或市場會調價。')
    elif topic.name == '平台監管與市場權力':
        sentences.append(f'[Reported] 標題涉及{actor}的監管或法律案件，是否只是調查、提案或判決要分開確認。')
        sentences.append('[Reported] 目前沒有法規原文與程序細節，不能把案件消息直接當成已生效的禁令。')
    else:
        sentences.append(f'[Analysis] 目前可以辨識的主體是{actor}，來源指向「{topic.name}」，但不足以可靠重寫具體動作。')
        sentences.append('[Analysis] 需要補上具體文章的公開摘要或公司公告，才能區分這是已發生的事件、計畫還是評論。')

    sentences.append(f'[Reported] 可辨識的事件期間是{period}；這份來源的發布日期為{date or "未提供"}。' if period
                     else f'[Reported] 來源發布日期為{date or "未提供"}，這不等於產品上市、部署或事件完成的日期。')
    numbers = financial_numbers(text) if financial else []
    if numbers:
        sentences.append('[Reported] 公開摘要的數字主張是' + '、'.join(numbers) + '，目前仍是來源說法，尚未核對公司原始文件。')
    elif products:
        sentences.append('[Reported] 可辨識的產品／技術名稱是' + '、'.join(products) + '，摘要沒有足夠數字可比較價格、效能或使用規模。')
    else:
        sentences.append('[Reported] 目前沒有可可靠對應指標的關鍵數字，不能由標題推算金額、成長幅度或部署規模。')
    explanation = ('[Analysis] 白話說，這則要看的是已實現收入有多少來自哪些產品；營收增加不等於毛利或獲利也增加。' if financial
                   else '[Analysis] 白話說，模擬是在電腦裡先組出可試驗的場景；AI 代理是否能獨立完成每一步，來源尚未證明。' if simulation
                   else '[Analysis] 白話說，代理若能替人操作服務，就要先弄清它拿到哪些權限，哪些操作仍須使用者同意。' if agent
                   else '[Analysis] 這裡的背景說明不代表上述事件已查證，時間、範圍與條件仍以原始文件為準。')
    sentences.append(explanation)
    if re.search(r'\b(could|may|might|reportedly|plans?|propos\w*)\b|可能|計畫|傳聞',text,re.I):
        sentences.append('[Reported] 來源含有可能、計畫或未確認的語氣，上述來源主張不能寫成已完成或確定會發生。')
    if not article.short_snippet:
        sentences.append('[Analysis] 目前只有標題，沒有公開摘要；因此不能確認上述主題背後的實際動作與原因。')
    else:
        sentences.append('[Analysis] 目前掌握的是標題與有限公開摘要，缺少完整條件、適用範圍與獨立驗證；摘錄也可能在句子中間截斷。')
    sentences.append('[Analysis] ' + topic.followup.rstrip('。') + '；完整文章如需補查，請由讀者透過來源連結合法閱讀，程式不抓全文。')

    if financial:
        important = '如果 AI 需求確實轉成收入，就應能在月營收、產品組合、毛利率或法說指引中看到對應數字；也要排除季節性、價格變動和低基期造成的成長。'
    elif simulation:
        important = '開發模擬應用要把素材、物理與渲染串起來；若代理能協助其中的步驟，工程師要檢查生成的場景是否正確、腳本是否可重跑，而不能只看示範畫面。'
    elif agent:
        important = '如果這類代理可以操作服務，企業就需要逐項管理它能碰哪些帳號、檔案、email、行事曆與內部系統，並留下操作紀錄、撤銷權限及追蹤錯誤；這是條件式影響，不是本文已證明的功能。'
    elif topic.name == '記憶體成本與裝置定價':
        important = '如果零件成本上升，品牌可能提高售價、降低記憶體容量或吸收成本；使用者要比較同規格價格，不能只看「起售價」有沒有變。'
    elif topic.name == '平台監管與市場權力':
        important = '只有在規則或判決適用於具體服務時，平台才可能必須改預設服務、資料使用或開發者條款；要先看適用地區與生效日期。'
    else:
        important = '目前資訊不足以指出具體營運或產品影響；先補事件動作、產品規格、客戶或法律條件，不能用產業名詞代替證據。'

    big_names = [name for name in actors if name in ('NVIDIA','OpenAI','Google','Microsoft','Amazon','Apple','Meta')]
    if not big_names:
        big = '目前資料不足，不能判斷。來源沒有提供可核對的 Big Tech 公司、產品角色或合約關係，不能自行指定某家雲端公司或產品。'
    elif simulation:
        big = '對' + '、'.join(big_names) + '，可能影響 Omniverse 等開發工具的使用方式與軟體策略；還需要官方文件確認哪些工具支援代理、是否需要特定 GPU 與授權，不能推算 GPU 銷量。'
    elif agent:
        big = '對' + '、'.join(big_names) + '的代理產品，需確認帳號登入、工具/API 接入與第三方資料傳輸政策；若能代操作服務，才進一步涉及操作紀錄、資料外洩責任與錯誤追蹤，不能假設它已取得 email 或行事曆權限。'
    else:
        big = '目前資料不足，不能判斷。雖提到' + '、'.join(big_names) + '，但還需要具體產品公告或合約才能談策略改變。'

    areas = []
    for pattern,label in ((r'\bAI servers?\b','AI server'),(r'\bPCB\b|printed circuit board|substrate|載板','PCB／載板'),
                          (r'\bmemory\b|\bDRAM\b|\bHBM\w*\b|記憶體','記憶體'),(r'\bNAND\b|\bSSD\b|storage|儲存','儲存'),
                          (r'advanced packaging|Foveros|CoWoS|先進封裝','先進封裝'),(r'\bODM\b|\bOEM\b','ODM／OEM'),
                          (r'data.?cent[er]+|資料中心','資料中心')):
        if re.search(pattern,text,re.I): areas.append(label)
    taiwan = ('來源提到' + '、'.join(areas) + '，可沿這些產品追公司公告、出貨量與客戶組合；目前沒有直接證據證明特定台廠新增訂單或受益。' if areas
              else '目前沒有直接證據。只有 AI 應用或代理字樣，不能推定 AI server、PCB／載板、記憶體、儲存、先進封裝、ODM／OEM或資料中心的需求改變；需補產品拆分或採購公告。')
    opening = (f'今天想聊{actor}這則營收消息：AI 很熱，但錢到底進了哪一類產品？我們先看報導給的數字，再回到月營收和毛利率，不急著喊誰受惠。' if financial
               else '今天有個很好玩的問題：讓 AI 幫我們組一個能動的模擬世界，到底省掉哪一步？畫面看起來很厲害，但場景能不能重跑、物理有沒有做對，才是想一起弄懂的地方。' if simulation
               else '如果把 AI 代理當成助理，你會把信箱和行事曆的鑰匙交給它嗎？這篇報導談隱私承諾，我們先拆開權限、操作紀錄和出錯後誰負責，別急著相信一句「很安全」。' if agent and privacy
               else f'今天看到{actor}這則消息，想先問：它究竟改變了哪個產品或哪個人的日常？我們從來源說了什麼開始，再把沒交代的條件補上。')
    return dict(sentences=sentences, important=important, big=big, taiwan=taiwan, opening=opening)
