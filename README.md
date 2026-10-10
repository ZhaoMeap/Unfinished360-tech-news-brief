# 還沒想到科技快報 V3：Editor Mode

為 Ray 的《還沒想到》Podcast 準備科技新聞。預設 **dry-run、不寄信**。V2 把找新聞與編輯快報分成兩個階段，避免把標題雷達誤認為已完成的新聞分析。

## V1 / V2 / V3 差異

| 版本 | 定位 | 輸出 |
| --- | --- | --- |
| V1 | 自動 metadata 草稿，缺少編輯判斷 | 原始快報模板 |
| V2 | 找候選與指定連結分流，加入品質／社群樣本 | 候選雷達、指定連結快報 |
| V3 | 在 V2 之上加入規則式編輯選題與主線 | 每日編輯簡報、前三則、次要候選、具體補查與使用建議 |

V2 的兩種模式仍保留：

| | V1 | V2 |
| --- | --- | --- |
| 自動來源 | metadata-only 內容包裝成快報 | **科技新聞候選雷達**：candidate discovery，供挑選，不是完整新聞稿 |
| 指定連結 | 沒有 | `--links links.txt`：編輯指定來源後產出 **還沒想到科技快報** 草稿 |
| 資訊不足 | 重複泛用分析與缺資料提示 | 直接列 **待人工補充**，不產生公司對策或虛構脈絡 |
| 品質 | 只有來源與可信度 | source quality score + 可用資訊程度，與可信度分開 |
| 社群 | 只列項目數／連結 | 有上限的公開留言抽樣，整理焦點、擔憂、技術觀點與樣本程度 |
| 時區 | 仰賴系統資料 | requirements 加入 `tzdata`，Windows 也能使用 `Asia/Taipei` |

**指定連結模式才適合準備 Podcast 快報**，但公開摘要不等於完整查證：資訊不足就補資料，不會用模板假裝已理解故事。V2 沒有使用 LLM 或翻譯服務，不需要 API key；以可驗證的主題詞與事件類型做保守重寫，無法可靠重寫的新主題直接待人工補充。無法自動形成完整因果故事、解析數字關係或判定多篇文章支持同一結論；這些仍需編輯補充。

## Editor Mode：每日五分鐘選題

```bash
python -m src.main --dry-run --editor
```

V3 根據自動候選的 title、source、published_at、tags／主題、description（保留在 short_snippet）、source quality 與實際取得的社群樣本，產生 `reports/YYYY-MM-DD_editor.md`，主旨為 `還沒想到科技編輯簡報 - YYYY/MM/DD`。不覆蓋候選雷達或指定連結報告，不寄信。

內容包含 3–5 句今日主線、三則重點及其值得追蹤的理由、Big Tech／台灣產業可能關聯、其他候選、資料缺口，以及 Podcast／IG／Threads／只觀察的使用建議。為控制閱讀長度，其他候選預設五則（資料不足時不湊數）；主線仍可提出有來源支撐的「可能主線」，一律標 `[Analysis]`，不宣稱存在因果關係或全市場共識。

選題規則可在 `src/editor_report.py` 檢視：優先財報／需求、AI 算力與硬體、監管、代理信任成本，再考量產品與應用；時效、來源品質加分，重複主題／來源減分以增加多樣性。社群只作有限的編輯興趣加分，不提升可信度。相似標題只做候選去重，不代表交叉查證。來源排名不依賴 Reuters 成功，401 直接列資料缺口。

「目前知道」只描述已取得的標題／短摘錄提供哪些線索；metadata 不會寫成已確認事件。官方的 `[Confirmed]` 也僅代表發布者提供資訊。影響、主線、值得看的理由與使用建議均為 `[Analysis]`。沒有對應原始 URL 的社群討論，就明確要求 HN／Reddit 討論串，不把其他話題的留言套用過來。

V3 不用空泛的「待人工補充」填版面，而是依選題要求公司公告／press release、財報原文與法說資料、規格與量產時間、法規文本或研究方法。僅有標題的新聞可追蹤，但不推薦拿來做未查證的事件解說；公開短貼文也應以來源連結與提問呈現。首頁／分類頁不會因套用 Editor Mode 就變成完整事件，需換成具體文章或官方公告。`--editor` 與 `--links` 不能同時使用。Editor Mode 一律只產生報告，即使同時指定 `--send-email` 且 SMTP 設定齊全，也會忽略寄信要求並顯示提示。預設無參數仍為 V2 候選雷達，Actions 排程也維持 dry-run 雷達，不啟用寄信。

## 安裝

Python **3.11+**；Codex Cloud 驗證 **3.12.14**，GitHub Actions 使用穩定的 **3.12**。本機 3.14.6 可使用相同指令，但此環境尚未驗證該版本；遇到相容性問題請改用 3.12。Windows 需要 IANA 時區資料 `tzdata`，已列入 requirements，無需另外猜測時區設定。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell 改用 `.venv\Scripts\Activate.ps1`，複製設定用 `Copy-Item .env.example .env`。在專案根目錄執行；不需資料庫或常駐服務。

## 自動候選雷達

```bash
python -m src.main --dry-run
# 無參數也只 dry-run
python -m src.main
```

Subject 與報告標題為 **科技新聞候選雷達**。擷取近 48 小時、有日期的科技項目，最多列 10 個非社群候選，不編造三則完整新聞。Hacker News／Reddit 是獨立的討論方向，不能佔用事實新聞槽位。來源缺失集中放在來源狀態，避免每則候選塞滿重複缺資料欄位。

來源包含 Reuters 公開科技索引、Google／Microsoft／NVIDIA blog、Apple Newsroom（含財報公告）、FTC 公告、The Verge、DIGITIMES、Hacker News RSS 與 Reddit r/technology RSS。**Reuters 可能回傳 HTTP 401，不保證可用，不是穩定必備來源**。不可用時繼續其他來源，不切換非授權鏡像或繞過付費牆。可選擇以 `.env` 的 `REUTERS_FEED_URL`／`DIGITIMES_FEED_URL` 指定有權使用的 HTTPS feed。X 僅保留介面，尚未接 API。

## 使用者指定連結／Podcast 快報

```bash
cp links.example.txt links.txt
# 用編輯器更換 links.txt 的來源
python -m src.main --dry-run --links links.txt
```

每行一個 HTTPS URL，空白行及 `#` 註解忽略，重複 URL 去除；上限 20 個連結、檔案 64 KB。相對檔案路徑以執行目錄為準。可放同事件的官方公告、媒體報導與對應 HN／Reddit 討論串。指定模式不再抓所有自動來源，僅擷取這些連結與所指定討論串的有限公開留言。

讀取公開可見的 title、description、published_at、來源主機與公開摘要。只串流讀取 HTML **head**（最多 96 KB，讀到 `</head>`／`<body>` 即停止）；不解析正文、不下載 PDF／全文，不使用 reader-mode、付費帳號或存取限制的替代路徑。網站忽略 Range 時也會在上限或 head 結束處關閉串流，最後一個小區塊可能含有正文起始位元組，但不解析、保存或輸出正文。

公開摘要限 `abstract`／`summary` meta 與 HTML head 中 JSON-LD 的 `description`。JSON-LD 的 `articleBody`／`text` 不使用，標明 `isAccessibleForFree=false` 的結構資料摘要不取；一般公開 meta description 仍可作為 metadata。head 超過上限時只解析已讀到的部分。沒有日期就保留未知，不用今天代替。只接受 HTTPS 標準埠，拒絕帳密 URL、本機、私有 IP 與降級 HTTP redirect。直接連線會驗證解析出的 IP；雲端 HTTPS proxy 模式由代理解析 DNS 並執行目的地限制，不要求本機能解析外部網域。

報告主稿最多三個不重複的非社群主題，依指定順序；所有指定連結與狀態都列在附錄。相似標題只列跨來源候選，不等於交叉確認。不足以形成故事線的項目只列「待人工補充」。V2 不再為未支持的公司對策或媒體觀點生成泛用段落。

## 品質與可信度

| source quality score | 分數 | 可用資訊程度 | 意義 |
| --- | --- | --- | --- |
| title only | 1 | 低 | 只有標題；即使官方標題也不自動評高 |
| metadata | 2 | 中 | 有公開 description／短摘錄 |
| public summary | 3 | 中 | 有 head 中明示的公開摘要 |
| official source | 4 | 高 | 已知官方網域且有公開 description／摘要 |
| community discussion | 0 | 有摘要為中，否則低 | 有討論線索，但不是事實證據；0 不代表留言無價值 |

品質評估的是**可取得資料程度**，不是新聞真偽。官方網域使用明確名單，不因網站自稱官方就相信。多來源的相似標題不會自動評高／Confirmed；只有真正完成交叉核對才能由編輯作此判斷。未取得頁面也保留原始 URL 與待人工補充狀態。

- `[Confirmed]`：有公開摘要的已知官方來源，僅指發布者的說法，預測不等於已實現。
- `[Reported]`：Reuters／The Verge／DIGITIMES 提供的資訊，沒有自動官方確認。
- `[Rumor]`：社群討論線索，不是事實或共識。
- `[Analysis]`：作者主題整理或提問。未列入可信來源名單的指定連結也保持保守標記。

## 社群回響

每次最多讀 HN、Reddit 各兩個討論串，每串最多六則頂層／公開 RSS 留言。HN 用官方 Firebase API，略過刪除／dead 留言；Reddit 用公開留言 RSS，不需 API key。社群分析只針對實際取得的留言，不從發文標題編造「網友認為」。

用規則分類隱私、成本、安全、效能、整合、工作與體驗等主題；同一作者只計一次。「常見擔憂」需至少兩位不同樣本作者同時出現擔憂語氣與主題詞，否則待人工補充。技術觀點依 API／部署／benchmark 等字詞分類，**不推定發言者就是工程師**。不輸出留言全文、不保存原始留言，只保留聚合計數；語境、反諷、否定句與多語言會造成誤分類，這只是供訪談提問的分類線索。

報告列討論焦點、常見擔憂、工程師觀點／技術討論、是否少量討論。HN 可列 API 提供的總留言數；Reddit RSS 無法可靠提供總數，明示未知，不把小樣本推成全站共識。新聞與討論串只有在原始文章 URL 相符時才關聯；沒有證據就不宣稱是該新聞的反應。

## 報告輸出與測試

日期依台灣時間：

- `reports/YYYY-MM-DD.md`：最近一次執行的報告，同日重跑更新。
- `reports/YYYY-MM-DD-radar.md`：另保留自動雷達，避免指定連結執行覆蓋發現結果。
- `reports/YYYY-MM-DD_editor.md`：V3 編輯簡報，獨立保存。

報告、`.env`、`.venv` 均排除於 Git。退出碼 0 表示報告產生成功，不代表來源全可用或故事線已查證。連結檔錯誤回傳 1，提示錯誤但不顯示可能敏感的網址。

```bash
python -m unittest discover -s tests -v
python -m src.main --dry-run
python -m src.main --dry-run --links links.example.txt
python -m src.main --dry-run --editor
```

測試使用 mock，不會寄信；驗證串流停止、付費資料排除、品質分級、模式分流、社群抽樣與 SMTP 保護。實際 dry-run 驗證上游服務當時可用性。

## .env、SMTP 與 GitHub Actions

Dry-run 不需要 SMTP 設定。未來明確要求寄信時才使用：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-account
SMTP_PASS=your-app-password
MAIL_FROM=your-account@example.com
MAIL_TO=unfinished360.podcast@gmail.com
```

都是範例，請填實際設定；不要把密碼提交 Git 或貼到聊天。環境變數優先於 `.env`。

```bash
# 只有明確指定 --send-email 才會寄信
python -m src.main --send-email --links links.txt
```

465 使用 SMTP over TLS，其他埠強制 STARTTLS 並驗證憑證。缺少設定或寄信失敗時保留報告、印出不含密碼的錯誤並回傳 1，不自動重寄。

Actions 使用 Python 3.12，UTC `0 1 * * *`（台灣每日 **09:00**），**預設執行 dry-run 候選雷達**，不是完整 Podcast 新聞稿；排程可能延遲，需推到預設分支才會運作。報告以 artifact 保存 7 天，不自動 commit。手動 workflow 的 `send_email` 預設 false，只有明確勾選才執行寄信步驟。

要測試寄信，先到 GitHub Settings → Secrets and variables → Actions 設定 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASS`、`MAIL_FROM`、`MAIL_TO` 六個 Secrets。設定 Secrets 本身不會啟用每日寄信；本次 V2 不啟用或測試真實寄信。

Codex Cloud 的來源網路需要 `www.reuters.com`、`blog.google`、`blogs.microsoft.com`、`blogs.nvidia.com`、`www.apple.com`、`www.ftc.gov`、`www.theverge.com`、`www.digitimes.com`、`hnrss.org`、`www.reddit.com`。HN 公開討論需 `news.ycombinator.com`、`hacker-news.firebaseio.com`；指定模式另需每個 URL 的主機與合法 redirect 主機。允許網域不保證上游開放存取；拒絕時直接待人工補充，不繞過代理或網站限制。

## 版權與資料使用

文章 metadata 只保存 `title`、`url`、`source`、`published_at`、`short_snippet`、`tags` 六欄；品質是執行時評估，不建立全文資料庫。自動來源摘錄最多 160 字元，指定連結最多 400 字元，不直接輸出原文摘要；草稿用自己的話整理主題，不能可靠重寫時待人工補充。原文標題／來源連結供辨識與閱讀，權利屬各來源。公開 feed 可能內含全文欄位，程式不保存或解析 `content`／全文欄位，只使用有限 title／summary metadata。遵守各站條款，不大量複製、不繞過付費牆、不抓取或輸出文章全文，也不把社群留言當作事實。
