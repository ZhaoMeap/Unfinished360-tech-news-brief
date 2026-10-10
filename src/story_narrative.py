"""Paraphrase explicit metadata claims; keep explanations and gaps separate."""
from __future__ import annotations

import re
from decimal import Decimal

from .fetch_sources import Article

COMPANIES = {'Zhen Ding': '臻鼎', 'Phison': '群聯', 'Anthropic': 'Anthropic', 'NVIDIA': 'NVIDIA', 'OpenAI': 'OpenAI',
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
    elif topic.name == 'AI 評測與可靠性':
        if re.search(r'cutting off.*evaluations.*internet', article.title, re.I):
            sentences.append(f'[Reported] 標題說{actor}正在把內部評測與網際網路隔開，這是在改測試環境，不是發布新模型功能。')
        else:
            sentences.append(f'[Reported] 來源涉及{actor}的 AI 評測，但摘要未完整交代測試方法與結果。')
        sentences.append('[Analysis] 要分清模型能力與測試時能取得的外部資訊；目前未取得隔離範圍、測試資料集與可重現設定。')
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
    explanation = ('[Analysis] 白話說，這則要看的是已實現收入有多少來自哪些產品；這些數字不等於產品效能或實際部署已獲驗證。' if financial
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
    sentences.append('[Analysis] ' + ('需要產品公告、具體採用／部署案例與技術規格，核對收入是否真的連到某項產品用途' if financial else topic.followup.rstrip('。')) + '；完整文章如需補查，請由讀者透過來源連結合法閱讀，程式不抓全文。')

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


def engineering_lens(article: Article, topic):
    """Engineering questions are analysis; tool proposals require source evidence."""
    text = article.title + ' ' + article.short_snippet
    products = product_names(text)
    named = '、'.join(products) or '來源未具名的工具'
    solution = '[Analysis] 目前只看到問題，還沒有看到明確解法。需要官方技術文件或可重現範例，不能把工程建議當成公司已實作的功能。'
    limits = '來源未提供具體技術瓶頸、不能自動化的步驟或測試結果；需要支援範圍、失敗案例與實測資料，不能自行判定已解決。'
    attention = '目前未能辨識具體新技術、新產品、功能或架構，工程師關聯尚不明確，選題應降級；需補規格、操作流程或技術公告。'
    application = '來源未提供可確認的應用場景；需要具體產品功能與使用案例，不能只由 AI 標籤推定用途。'
    opening = '這則消息讓我想問：到底多了哪個我們真的能用的功能？先看它能做什麼、哪一步會失敗，再決定要不要放進自己的工作流程。'
    if topic.name in ('財報與需求訊號', '公司整併與投資布局'):
        attention = '這不是新技術發布，不能由營收或投資金額判定效能、可靠性或產品已被採用；只有來源提供具體產品採用、出貨或部署證據時，才值得追工程需求，因此目前降低優先級。'
        application = '來源未提供可驗證的產品用途或部署案例；不能把營收成長直接換算成 AI server 或資料中心需求。'
        opening = '數字變大了，但工程師真正想知道的是：大家到底在用哪個產品？如果看不到用途和部署案例，我們先把這則留在觀察清單。'
    elif topic.name == 'AI 評測與可靠性':
        attention = '這不是消費者新功能，而是評測流程的改變，直接關係到工程師能否相信測試結果；需核對網路存取、工具權限、資料集污染與可重現設定。'
        limits = '來源未提供完整隔離範圍、哪些工具仍可連網或哪些步驟需要人工審查；需測試外部資訊是否影響成績，也要比較離線評測和真實連網任務的差距。'
        application = '模型測試與開發工具：用於上線前評估代理能力，並區分測試環境結果與企業自動化的實際可靠性。'
        if re.search(r'cutting off.*evaluations.*internet', article.title, re.I):
            solution = '[Reported] 標題提出將內部評測與網際網路隔開。[Analysis] 這是測試環境的限制措施，還需官方方法與重現資料才能判斷效果，不能說已解決所有作弊或資料污染。'
        opening = '考試時把網路關掉，是在測 AI 的真本事，還是讓它失去平常會用的工具？工程師要先弄懂考場規則，才知道分數能不能代表真實工作。'
    elif re.search(r'simulation|omniverse|模擬', text, re.I):
        attention = f'來源指向{named}的模擬開發流程；若用 AI 代理串接素材、物理與渲染，工程師需檢查素材格式相容性、腳本可重跑性和場景測試，不能把示範當成全自動能力。'
        limits = '來源未提供哪些步驟還不能自動化，也未提供誤差或失敗率。工程上需檢查物理參數與測試場景；若要用於工業設備或機器人，仍需實體測試比對，這是驗證建議，不是來源已完成的結果。'
        application = '可探索工業模擬與開發工具：先在電腦裡組場景、重跑測試，再決定是否用於設備或機器人；來源尚未證明實體部署效果。'
        if products and re.search(r'agent|代理', text, re.I):
            solution = f'[Reported] 標題把{named}與 AI 代理放進模擬開發流程。[Analysis] 這是來源提出的方向，尚缺工具版本、API 範例、授權與測試結果，不能宣稱已解決驗證或全自動化問題。'
        opening = '讓 AI 幫我們組一個模擬世界，是省掉哪一步，還是只讓畫面更漂亮？工程師會先問場景能不能重跑、物理有沒有做對，最後還得回到真實設備驗證。'
    elif re.search(r'\bagents?\b|代理', text, re.I):
        attention = f'可辨識的代理產品／工具是{named}，但來源未完整列出新增功能或架構。若代理替人操作服務，就需逐項確認帳號、檔案、email、行事曆與內部系統權限，並測試撤銷權限、重試與操作紀錄；這些不是已確認的產品能力。'
        limits = '來源未提供哪些任務不能自動化、錯誤率或資料流向；刪檔、寄信等不可逆操作應先設人工審查並測試失敗復原，還需更多測試與權限文件才能評估可靠性。'
        application = '可探索企業自動化與開發工具，例如在授權範圍內串接服務；是否能碰 email 或行事曆須看實際權限文件。涉及敏感資料時也要評估資安與權限控管。'
        if products and re.search(r'unveiled|introduced|launched|推出|發布', text, re.I):
            solution = f'[Reported] 公開摘要提到發布{named}。[Analysis] 尚未看到權限模型、審批流程與失敗復原的明確解法；產品發布或隱私承諾不能替代可核對的政策和測試。'
        opening = '如果 AI 助理能代你做事，你會把哪些鑰匙交給它？我們從它能碰什麼、出錯怎麼停下來、哪些事要先問你開始聊。'
    elif re.search(r'privacy|security|vulnerab|隱私|安全|漏洞', text, re.I):
        attention = '這類新聞與工程師的資料安全和維運有關；需核對受影響版本、攻擊條件、權限範圍與補丁相容性，來源未提供時不能自行指定漏洞或修復方式。'
        application = '資安與權限控管：先對照自己使用的版本和暴露介面，才能決定是否需修補、隔離或調整存取政策。'
    elif topic.name == '平台監管與市場權力':
        attention = '這不是新技術發布，但若規則涉及資料處理、API 或產品分發，工程師可能需調整資料流和介面；先核對適用服務、地區與生效日期，沒有技術關聯時降低優先級。'
    elif re.search(r'gpu|server|chip|memory|packaging|半導體|記憶體|晶片', text, re.I):
        attention = f'來源涉及硬體／架構，辨識到的技術名稱為{named}；需核對效能測試的工作負載、功耗、記憶體容量及軟硬體相容性，不能由供應或價格消息推定效能提升。'
        limits = '來源未提供效能瓶頸、不能自動化的部分或實測方法；需要實體硬體測試、驅動／韌體版本及工作負載資料，才能評估部署與維運成本。'
        application = '先依來源提到的設備判斷用途：server／資料中心才追 AI server 與散熱供電，PC／手機則追消費者產品；沒有部署資訊時不能跨場景推論。'
    elif topic.name in ('產品與使用者生態', 'AI 應用與研究落地'):
        attention = f'目前辨識的產品／技術名稱是{named}；來源未完整列出新功能或架構，需要版本差異、操作範例和規格才能判斷。工程評估先看測試、相容性、部署與維運，不能把發布等同可穩定使用。'
        application = '依產品文件確認是開發工具、企業自動化或消費者產品；研究展示則先看實驗條件，不推定已能日常部署。'
    # Extract only explicitly named tools; do not convert suggestions into implemented fixes.
    if re.search(r'patch|修補|補丁', text, re.I):
        solution = '[Reported] 來源提到修補／補丁方向。[Analysis] 仍需官方安全公告、受影響版本、補丁版本與回歸測試，不能說所有部署都已修復。'
    return dict(attention=attention, limits=limits, solution=solution, application=application, opening=opening)
