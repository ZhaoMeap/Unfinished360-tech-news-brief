"""Separate source claims, engineering background, hypotheses, and verification."""
import re

from .story_narrative import describe, engineering_lens, entities, product_names


def explain(article, topic, label):
    label = 'Confirmed' if label == 'Confirmed' else 'Reported'
    text = article.title + ' ' + article.short_snippet
    old = describe(article, topic)
    lens = engineering_lens(article, topic)
    background = [
        'API 是程式彼此溝通的介面，好比服務的櫃台：能辦哪些事、要帶什麼資料，都有約定。',
        '工具版本決定支援的功能與相容性；授權則規定能如何使用或散布，兩者不是同一回事。',
    ]
    if not re.search(r'omniverse|simulation|agents?|API|sdk|模擬|代理', text,re.I):
        background = []
    focus = '把一個功能接入工作流程時，要用相同輸入重跑測試，檢查錯誤、延遲與相容性；上線後也要留下可追查的紀錄。'
    direction = '常見方向是先做小範圍試用、建立回歸測試與監測，再逐步擴大部署；這是一般工程建議，不是來源已證實的實作。'
    questions = ['新功能究竟省掉哪個操作步驟？', '用什麼測試確認結果可重現？', '出錯時能否回復，維運成本由誰承擔？']
    gaps = ['官方功能／版本文件與適用範圍。', '可重現測試、失敗案例及實際部署結果。']
    sentences = [s.replace('[Reported]', f'[{label}]') for s in old['sentences']
                 if s.startswith('[Reported]') and not any(w in s for w in ('沒有', '不足', '未提供', '不能', '未明示', '尚未', '未取得'))]
    # Date is a publication fact, never a launch date.
    if not any('發布日期' in s for s in sentences) and article.published_at:
        sentences.append(f'[{label}] 這份來源發布於{article.published_at[:10]}，這是刊登日期。')
    if topic.name == 'AI 評測與可靠性':
        background += ['評測資料集是一組測試題目與評分規則，用來比較模型在固定條件下的表現。',
                       '資料污染是模型事先接觸測試答案或近似內容，讓分數看起來比真正能力更好。',
                       '隔開網際網路能限制測試時查找外部答案，但離線與連網任務測到的能力也不同，不能直接互換。']
        focus = '這涉及上線前的評測 workflow：固定工具權限、資料集和執行環境，再比較離線與連網表現；自動評分難涵蓋所有真實任務，邊界案例仍可能需要人工審查。'
        direction = '常見工程方向包括網路隔離、保留未公開測試集、記錄工具呼叫、重跑相同案例，再用人工審查核對異常高分；這些不是來源已證實採用的全部措施。'
        questions = ['評測時哪些工具還能連網？', '測試題目是否可能出現在訓練資料裡？', '離線高分是否代表能可靠完成真實連網工作？']
        gaps = ['隔離哪些網路與工具、是否仍允許特定服務。', '資料集來源、污染檢查方法與重現設定。', '離線／連網對照結果與人工審查流程。']
    elif re.search(r'omniverse|simulation|模擬', text, re.I):
        background += ['Omniverse 是 NVIDIA 用於建立與連接 3D 工作流程的工具與技術平台，可用於模擬和協作；這是平台背景，不代表本文發布了所有這些功能。',
                       '物理模擬是在電腦裡用規則近似重力、碰撞或材料行為；算得像不像，需要拿測試或真實量測來比對。',
                       '渲染是把場景、材質與光線算成畫面；畫面逼真不等於物理結果正確。'] if re.search(r'omniverse', text,re.I) else [
                       '物理模擬用數學規則近似真實系統，渲染則把場景算成畫面；看起來逼真不等於物理正確。']
        focus = '工程 workflow 是把素材、物理、渲染與場景檢查串起來；若交給代理，需測素材格式、腳本可重跑性及物理參數。用於設備或機器人時，模擬與真實世界的差距還需要實體測試，不能只自動檢查畫面。'
        direction = '常見方向是把任務拆成可驗證的小步驟，保留場景版本與測試基準，再以實體量測校準模擬；這是一般工程方向，不是來源已證實的功能。'
        questions = ['代理能完成哪些步驟，哪些仍要工程師介入？', '物理結果與實體量測差多少？', '換素材或工具版本後，場景還能重跑嗎？']
        gaps = ['支援的工具版本、API、素材格式與授權。', '代理可自動完成的步驟及人工介入點。', '物理誤差、失敗案例、實體比對與硬體需求。']
    elif re.search(r'clinical|patient|AMIE|醫療',text,re.I):
        # Paraphrase only explicitly present title claims.
        if re.search(r'study.*suggests.*AI.*patient', article.title,re.I):
            sentences.insert(0, f'[{label}] 標題說一項研究認為 AI 可能改善病人與醫師的互動，這是研究提出的可能性。')
        if re.search(r'Lancet',text,re.I):
            sentences.insert(1, f'[{label}] 來源提到 The Lancet，事件屬於醫療研究與 AI 應用。')
        background += ['臨床研究要比較特定條件下的結果；樣本、對照組和評分方法會決定能把結論推到多遠。',
                       '醫療 AI 的回答即使流暢，也可能遺漏重要病史或給出錯誤建議，因此需要醫療人員審查與隱私保護。']
        focus = '可能的 workflow 是協助整理病人描述或準備溝通內容；工程師需測資訊遺漏、錯誤建議與敏感資料流向。臨床判斷與例外情況仍需專業審查，研究結果不能直接等同日常部署能力。'
        direction = '常見方向是限制任務範圍、以專家審查對照模型輸出、分群評估錯誤，再記錄資料存取；這是一般工程方向，不是這項研究已證實的方案。'
        questions = ['研究用了哪些樣本與對照組？', '改善的是溝通評分，還是實際醫療結果？', '錯誤建議與病人資料要如何處理？']
        gaps = ['研究原文的樣本、對照組、評分方法與限制。', 'AI 的實際任務、人工審查及資料處理政策。', '臨床結果與日常部署的差異。']
    elif re.search(r'agent|privacy|security|代理|隱私|安全',text,re.I):
        background += ['AI 代理是把模型輸出接到工具或服務，以嘗試完成多步任務；能回答問題不等於能可靠執行所有操作。',
                       '權限控制限定誰能讀取或修改哪些資料；最小權限是只給完成任務所需的存取範圍。',
                       '操作紀錄留下何時、由誰、對什麼做了什麼，方便追查錯誤與撤銷存取，但不能單靠紀錄防止所有資料外洩。']
        focus = '若 workflow 涉及代操作服務，就要測權限撤銷、重試、重複執行與失敗復原；刪檔或寄信等操作可能需要人工確認。安全測試也要檢查外部內容是否能誘使代理越權。'
        direction = '常見方向是最小權限、隔離工具執行、敏感操作先確認、保留稽核紀錄與回復機制；這是一般工程方向，不是來源已證實部署的保護措施。'
        questions = ['它能操作哪些工具與資料？', '能否撤銷權限、回復錯誤操作？', '外部內容能否誘使它越權或洩漏資料？']
        gaps = ['具體工具／功能、帳號權限與資料保存政策。', '敏感操作審批、失敗復原與安全測試。']
    if re.search(r'gpu|server|memory|chip|packaging|晶片|伺服器|記憶體', text, re.I) and not re.search(r'agent|simulation|評測', text,re.I):
        background += ['GPU 擅長平行運算，記憶體容量與頻寬則影響能放多少資料、能多快送給運算單元；算力高不代表每個工作都更快。',
                       '部署硬體還要考慮驅動、散熱、供電與工作負載，相同規格在不同任務下可能有不同效能。']
        focus = '硬體採用的 workflow 是先對照工作負載測試，再檢查驅動相容性、功耗、散熱與維運；實體壓力測試不能只用規格表取代。'
        direction = '常見方向是用代表性工作負載做基準測試，監測瓶頸並調整記憶體、批次大小與散熱；這是一般工程方向，不是來源已證實的成效。'
    actors = entities(text + (' ' + article.source if article.source.startswith('官方：') else ''))
    if not sentences or all('發布日期' in s or '刊登日期' in s for s in sentences):
        sentences = [f'[Analysis] 這則候選的可辨識主體是{"、".join(actors) or article.source}，主題是「{topic.name}」。',
                     '[Analysis] 標題提供了討論入口，本文先用工程背景解釋這個主題，不把背景當成本次事件已發生的事實。'] + sentences
    # Context is labeled as analysis rather than padding source claims with inventions.
    contexts = ['[Analysis] 從工程師角度，接下來要拆開它想改變的工作步驟，以及如何驗證結果。',
                '[Analysis] 工具能展示一個案例，和能在不同輸入下穩定工作，是兩個不同層次的問題。',
                '[Analysis] 因此這則的切入點是用途、測試與落地條件，而不是從新聞熱度推定效果。',
                '[Analysis] 下一段先解釋技術名詞，再把來源主張與工程上的可能方向分開。',
                '[Analysis] 驗證清單集中在最後，作為後續追這則消息的依據。']
    sentences = sentences[:5]
    sentences += contexts[:max(0,5-len(sentences))]
    if topic.name == 'AI 評測與可靠性':
        context = ['[Analysis] 這類改動關係到測試是否在固定條件下進行，避免把取得外部資訊的能力誤當成模型本身的能力。',
                   '[Analysis] 工程上也要比較離線與連網任務，因為正式產品可能仍需要使用網路工具。',
                   '[Analysis] 這則重點是測試規則如何影響分數的解讀，而不是模型突然多了一項消費者功能。']
    elif re.search(r'omniverse|simulation|模擬', text,re.I):
        context = ['[Analysis] 若代理協助串接這些步驟，工程師就能把注意力放在場景是否正確，而不是只看它能不能產生畫面。',
                   '[Analysis] 一個場景在電腦裡能運作，還要經過重跑與實體比對，才適合用來指導設備或機器人。',
                   '[Analysis] 這則值得追的是開發流程可能怎麼改，而不是把軟體演示直接換算成硬體需求。']
    elif re.search(r'clinical|patient|AMIE|醫療', text,re.I):
        context = ['[Analysis] 工程上的切入點是 AI 如何協助整理與溝通資訊，以及如何避免遺漏重要病情。',
                   '[Analysis] 改善互動和改善醫療結果需要不同證據，不能把兩者當成同一個研究結論。',
                   '[Analysis] 這也是把 AI 放進有專業審查的流程，和讓 AI 自己作決定之間的差別。']
        lens['opening'] = '如果 AI 能幫病人把話說清楚，也讓醫師更容易理解，它會是個好幫手嗎？我們想弄懂的是溝通到底改善在哪裡，以及哪些判斷仍要留給醫師。'
    else:
        context = contexts
    # Replace generic padding with topic-specific, explicitly labeled interpretation.
    source_sentences = [s for s in sentences if s not in contexts]
    sentences = source_sentences + context[:max(0,5-len(source_sentences))]
    # Source-proposed direction precedes general engineering alternatives.
    proposal = lens['solution'].split('[Analysis]')[0].strip() if lens['solution'].startswith('[Reported]') else ''
    proposal = proposal.replace('[Reported]',f'[{label}]')
    return dict(sentences=sentences, background=background, attention=focus,
                solution=(proposal + ' ' if proposal else '') + '[Analysis] ' + direction,
                questions=questions, opening=lens['opening'], gaps=gaps)
