# 還沒想到科技快報

每天整理一份約 3–5 分鐘可讀完的科技新聞 **dry-run 簡報草稿**，供 Ray 準備 Podcast。使用台灣時間命名 `reports/YYYY-MM-DD.md`，主旨為 `還沒想到科技快報 - YYYY/MM/DD`。預設不寄信；未來內容穩定後，可寄到 `unfinished360.podcast@gmail.com`。

## 第一版範圍與限制

這一版是保守的 **metadata-only、規則式整理**，不需要 LLM API key。使用標題與短摘錄判斷主題，提供自己的閱讀方向、核對提示與 Podcast 提問；**尚不提供經全文驗證的語意摘要、精確事件翻譯或完整跨來源分析**。原文標題保留在標題／來源欄，其他敘述用自己的話撰寫並標記可信度。錄音、公開發布或啟用每天寄信前，請人工核對事件脈絡。沒有足夠資料就保留空位，不為湊滿三則而編造新聞。

採用 Python **3.11+**；目前 Codex Cloud 實測 **3.12.14**，GitHub Actions 使用穩定可用的 **3.12**，不依賴 3.14.6。你的本機 3.14.6 可嘗試相同安裝指令，但此環境未驗證該版本；若有套件相容性問題請改用 3.12。Windows 若缺少 IANA 時區資料，可另安裝 `tzdata`。

## 安裝

在專案根目錄執行：

```bash
python --version
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell 啟用指令為 `.venv\Scripts\Activate.ps1`，複製設定可用 `Copy-Item .env.example .env`。`.env`、虛擬環境與產出的報告均已排除於 Git；不需資料庫或常駐服務。

## 執行 dry-run

```bash
python -m src.main --dry-run
# 不帶參數也只產出報告
python -m src.main
```

產生 `reports/YYYY-MM-DD.md`；同一天重跑會更新該日報告。日期依 `Asia/Taipei`，候選新聞限近 48 小時且必須有日期。優先 Reuters，再取 The Verge／DIGITIMES 與官方資訊，先分散來源再補足空位。報告包含一句話總結、最多三則重點新聞與指定視角、三個 Podcast 問題，以及每個來源的取得狀態。來源無法取得不使整份報告失敗；即使全部失敗，也會產生明確標示缺資料的報告。**退出碼 0 表示報告生成成功，不表示全部來源可用**。

## 來源分層

| 層級 | 實作 | 限制 |
| --- | --- | --- |
| Reuters | 優先選取公開科技索引的標題與連結；可用 `REUTERS_FEED_URL` 指定有權使用的 HTTPS RSS/Atom | 公開索引可能拒絕自動存取；不繞過限制。索引日期由 URL 推得，並非精確發稿時間。自訂 feed 的真實性需自行確認 |
| 官方 | Google、Microsoft、NVIDIA blog、Apple Newsroom（含財報公告）、FTC 公告 RSS；另辨識 RSS 摘錄中的官方文件連結 | 只涵蓋這些公開端點，尚未全面接入所有公司財報／法規。候選官方連結不等於核對完成，媒體報導不會自動升級 Confirmed |
| The Verge | 公開 RSS | 補產品與文化線索；無同事件項目時標示目前無法取得，不虛構該媒體觀點 |
| DIGITIMES | 公開 RSS，可用 `DIGITIMES_FEED_URL` 覆寫合法來源 | 不抓付費全文；RSS 不可用或沒有近期符合項目時明示缺資料 |
| Hacker News / Reddit | HN RSS 與 r/technology RSS | 只列相關討論串，不抓留言、不推定共識、不當作事實；Reddit 可能限制存取 |
| X | `fetch_x()` 保留介面 | 尚未接入 API，不做非授權抓取 |

每個來源最多保留 30 筆候選，下載上限 1 MB；HTTP timeout、失敗處理及日期篩選均有設限。只在記憶體保留 `title`、`url`、`source`、`published_at`、`short_snippet`、`tags` 六個文章欄位，不建立全文資料庫或保存原始回應。短摘錄上限 160 字元，可保留一個摘要中明示的官方 URL；摘錄原文不在報告直接輸出。報告是衍生稿，含來源標題、URL、日期與自己的分析文字。跨來源標題比對僅為保守的候選關聯，可能漏配或誤配，請人工檢查。

Codex Cloud 若出現代理 HTTP 403，請在環境設定中允許 `www.reuters.com`、`blog.google`、`blogs.microsoft.com`、`blogs.nvidia.com`、`www.apple.com`、`www.ftc.gov`、`www.theverge.com`、`www.digitimes.com`、`hnrss.org`、`www.reddit.com`。網路允許不保證上游站點開放存取；遇到拒絕時仍不繞過限制。這是雲端網路設定，與 GitHub Actions Secrets 無關。

可信度規則：

- `[Confirmed]`：官方發布的資訊；不代表官方預測必然實現。未來可供人工核對多來源結論，本版不自動宣稱多來源確認。
- `[Reported]`：可信媒體提供的資訊，尚無官方確認。
- `[Rumor]`：未確認社群線索；不是事實、調查結果或網友共識。
- `[Analysis]`：作者的閱讀建議、條件式推論與 Podcast 提問。

## 設定 .env 與啟用寄信

只要 dry-run 就不需要 SMTP 值。正式寄信需設定全部六個欄位：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-account
SMTP_PASS=your-app-password
MAIL_FROM=your-account@example.com
MAIL_TO=unfinished360.podcast@gmail.com
```

以上只是範例，請填實際 SMTP 服務設定。不要把密碼提交至 Git 或貼到聊天。Gmail 通常需啟用兩步驟驗證並使用應用程式密碼（依帳號政策而定）。環境變數優先於 `.env`。

```bash
python -m src.main --send-email
```

先產生報告，再寄送純文字 Markdown。465 使用 SMTP over TLS；其他埠要求 STARTTLS 並驗證憑證，不支援明文寄信。缺少設定、埠無效、認證或傳送失敗時會印出不含密碼的錯誤訊息，保留報告並回傳退出碼 1，沒有未處理的 SMTP traceback。兩個執行旗標不能同時使用。寄送後是否到達收件匣仍取決於郵件服務；本版不做重寄，以免重複寄送。

## GitHub Actions

`.github/workflows/daily-brief.yml` 使用 UTC `0 1 * * *`，相當於每天台灣時間 **09:00**；GitHub 排程可能延遲，並非準點保證。推送到預設分支後，schedule 才會運作；空閒的公開儲存庫排程可能被 GitHub 停用。

排程與一般手動執行都只 dry-run，報告以 artifact 保存 7 天，不自動 commit 到儲存庫。可在 Actions 頁面下載報告。

若要手動測試寄信，在 GitHub **Settings → Secrets and variables → Actions → New repository secret** 設定：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `MAIL_FROM`
- `MAIL_TO`（例如你的 Podcast 信箱）

再到 Actions → Daily technology brief → Run workflow，明確勾選 `send_email`。SMTP Secrets 只傳給這個明確選擇寄信的步驟。**設定 Secrets 本身不會啟用每日寄信**。未來確認品質後，另行修改 workflow 的 schedule 執行模式為 `--send-email`，並讓該步驟取得同樣六個 Secrets；目前範本刻意保持每日 dry-run。

## 驗證

```bash
python -m unittest discover -s tests -v
python -m src.main --dry-run
```

離線測試覆蓋日期／來源失敗、社群隔離、可信度、報告格式、預設不寄信及 SMTP TLS／錯誤處理，不會真的寄信。實際 dry-run 用來檢查當下來源狀態；上游服務的可用性可能變動。

## 版權與資料使用原則

只使用允許公開取得的標題、URL、來源、日期、有限短摘錄與分類；不繞過付費牆、登入限制或反自動化限制，不大量複製原文、不輸出完整文章。文章內容與標題的權利屬各來源，請遵守各站使用條款並透過來源連結閱讀。社群只用來辨識討論方向。不要將自動產生的草稿誤認為已查證報導；來源不可取得時保留「目前無法取得」。
