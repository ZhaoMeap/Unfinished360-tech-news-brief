# Reliability v2 運作與驗證

## 根因與修正

- 舊版把 metadata 填成九段與通用 deployment 分析；現在 C 只出候選，公開摘要有主體／動作／細節才可 A/B。A 只代表官方摘要主張，不代表獨立 benchmark。RSS 太長或事件不明仍 C。
- 舊版把官方 blog 發布者當成新聞公司；現在公司從 title/snippet 偵測，發布者分開保存。未辨識不猜公司。
- 舊版公司／大主題群組會合併獨立故事；現在嚴格事件去重、保留 provenance，主題摘要不能當成同一事件。Podcast 分數六面向，每項 0–2，共 12；C 一律觀察，財務最多 4。
- 舊版週報取目前日期與滾動七天；現在以最近到期的台灣週日 20:00 決定 ISO week，週一遲到仍是原週。範圍 Monday 00:00 至下個 Monday 00:00（不含終點）。
- 舊版 `continue-on-error` 蓋住還原失敗；現在保存 restore_status，週報明示 Partial，致命還原錯誤使 workflow 失敗，但仍可上傳可安全生成的部分報告。
- 舊版只剩 7 天 artifact、沒有持久 slot 狀態；現在同 repo 的 brief-history 分支保存 ledger、metadata、日報，artifact 只當短期下載與過渡 fallback。

## Scheduled slots 與持久狀態

台灣 daily 09:17 / 15:17 / 21:17，weekly 週日 20:00。Watchdog 每小時 UTC xx:43 檢查最近 48 小時；同樣依賴 GitHub cron，不能保證 GitHub 平台故障期間仍會執行。

Daily 與 watchdog 共用 `technology-brief-history` concurrency group。GitHub concurrency 的 pending run 可能被更新的 pending run 取代；補跑計算讀 ledger，因此不依賴每個觸發都排隊保留。寫入使用 fast-forward push、不 force；競爭失敗直接 fail，不覆蓋遠端。Claim 先持久化才抓資料，running lease 30 分鐘後可回收，每個 slot 最多三次嘗試；逾期或三次失敗須管理員檢閱後處理，程式不無限重試。

`brief-history` 是同一 repo 的資料分支，首次 run 自動建立；不另建 GitHub repo、不新增資料庫。保留：

- state/slots.json：scheduled_slot_id、scheduled_at_utc、actual_started_at_utc、completed_at_utc、status、catch_up、run_id、output_file、checksum、attempts 與前次嘗試。
- state/events.json：穩定事件 ID 與 URL/metadata aliases，不是全文資料庫。
- data/daily/*.json：六欄文章 metadata、證據 provenance、來源診斷、實際 collection time。
- reports/daily/*.md：素材報告。

一次補跑多個 slots 共用一次「現在」抓取，各報告都有 Collected at、Scheduled slot、Catch-up。catch_up 定義為遲超過 30 分鐘，不會說內容在過去抓到。週報以實際 collection time 收新聞，同批的 MD/JSON 與多個 slot 複本只算一次。週範圍外的 recovery 可以計為 slot 完成，但必須標記不能還原歷史內容，週報仍 Partial。

本機 `--editor` 是無寄信的預覽，不 claim production slots；保存本機 metadata 供週報讀。Actions 的無寄信 scheduled/manual recovery 路徑則使用 `python -m scripts.run_daily_slots` 包住同一個 editor renderer。現有 CLI 均保留。

## Token、runner 與權限

Daily/watchdog 需要 `contents: write`，weekly 需要 `contents: read`、`actions: read`。僅使用 GitHub runner 內建 github.token 作為 GH_TOKEN，透過 `gh auth setup-git` 的 credential helper 支援獨立 history checkout；不把 token 放在 URL、Git config 明文或 repo 檔案。若 repo／組織限制 token write、brief-history 分支保護阻擋 push，job 必須失敗，不能假稱資料持久化。

checkout/setup-python/upload-artifact 更新為 v7；已查官方 tag 與 action.yml 的 node24 runtime。checkout/setup-python 官方 README 要求 runner >= 2.327.1；採 GitHub-hosted ubuntu-latest/Python 3.12。沒有在本次雲端機器執行 Node action runtime；第一個 Actions run 仍需確認。

## 手動復原與指定週

- GitHub → Actions → Daily slot watchdog → Run workflow，lookback_hours 可填 1–168，預設 48。請勿勾 daily 的 send_email。
- GitHub → Actions → Weekly technology curator → Run workflow → week 填 `2026-W41`；空白代表最近到期週。
- 本機先放入 daily 素材，再執行：

```bash
python -m src.main --dry-run --editor
python -m src.main --weekly --dry-run --week 2026-W41
python -m unittest discover -s tests -v
```

無素材／ledger／完整來源時仍可產生明示 Partial 的週報；若狀態不可信或無法產生安全輸出，CLI/restore step 非零退出。新 workflow 不使用 continue-on-error 隱藏失敗；restore 失敗仍可執行週報的診斷步驟並上傳 artifact，但整個 job 維持失敗。

## 首次 Actions 驗收

1. 合併 PR 後確認 Actions 未停用、預設分支為 main，排程記錄 event 為 schedule。第一個 daily 會補近 48 小時，這是延遲恢復，不是歷史資料。
2. 查看 brief-history 的 state/slots.json，確認 claim/results commits、run ID、實際時間、checksum；無歷史分支成功 commit/push 就沒有持久化。
3. 再手動執行 watchdog：已完成 slots 應不抓取、不重複寫報告；新 runner 能讀舊 ledger。
4. 查看 source_diagnostics：HTTP 401/403、ProxyError、空 feed 是失敗／缺口，不嘗試繞過。
5. 執行指定週，對照 Expected 21、Completed、Recovered、Missing、Failed、Pending、Unique events。週日 20:00 出報告時 Sunday 21:17 尚未到期，因此有 Pending，不能說完整一週；週一重新整理可納入晚間素材。
6. 下載 daily artifact（7 天）或 weekly artifact（14 天）；永久 provenance 以 brief-history 為準。

Git 分支會累積歷史，建議定期匯出季度備份並檢閱儲存用量。現在不自動刪除、重寫 history 或引入付費服務；將來若要轉外部儲存需另行確認。JSON/API 格式損毀、過期 artifact 或 branch 還原失敗都不能當成完整資料。

## 來源與雲端限制

加入 NVIDIA Developer、Ollama/ROCm/OpenBMC 官方 releases、Hugging Face、arXiv AI、ServeTheHome、TechNews 台灣。分類補 AI agents、GPU/CPU/accelerator/memory、BMC/firmware/networking/cooling/power/energy efficiency。僅讀合法公開 feed 的有限摘要／metadata，不抓文章全文。GitHub official 判定限制在指定 org，不把任何 GitHub repo 都標官方。

這些是 adapter，不保證 feed 在每個環境都可用；目前雲端新增域名的設定草稿已保存，尚須 Review/Save/Publish 才可套用。受阻項目照實寫來源診斷。GitHub API 目前仍受限，因此不能宣稱已驗證遠端 workflow 狀態或已建立 PR。

## 本次真實 dry-run 比較

隔離測試使用合成 fixture；以下樣本則來自實際公開 feed 與既有日報，沒有加入虛構新聞。

- 舊 `2026-10-11_1224_editor.md`：8,978 字元，三則都展開九段（27 個詳細段落）。
- 新 [daily sample](samples/2026-10-12_0157_editor.md)：3,736 字元；三則證據 C 都只保留候選，零個詳細段落。字元減少約 58%，不是宣稱相同事件的資訊量提升；兩次抓取時點與來源不同。
- [weekly sample](samples/2026-W41_weekly.md)：正確對應 Monday 延遲時的 W41；40 次素材去重為 12 個獨立事件；expected 21、completed 0、missing 21，明示 Partial。這些舊本機素材沒有 production slot ledger，不能補造完成紀錄。
- 77 個單元測試，包括跨獨立 checkout 持久化、競爭 push 拒絕、重跑不抓資料、週界線、來源拒絕及損壞 artifact；兩個 CLI dry-run 都未寄信。三份 workflow YAML 可解析，v7 官方 tag/runtime 已核對，尚未執行遠端 Actions。

樣本不是高品質完整週報的示範：公開摘要仍有限，現階段規則式中文改寫與公司辨識覆蓋不足，寧可保留 C，也不把 metadata 包裝成事實。Reuters 401；本次 TechNews 成功取得 24 項，其餘新增 feed 的空項目／解析失敗均記入 diagnostics。不得將沒有近期項目解讀成來源永久無法使用。
