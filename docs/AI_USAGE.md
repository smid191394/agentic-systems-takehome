# AI_USAGE

本文件說明開發這個 take-home 過程中如何使用 AI,以及如何驗證 AI 提供的結果、如何避免盲目採用生成結果。

## 1. 使用方式

### 1.1 起點：先把「這份 deliverable 該優化什麼」當成一個要解的問題

動手寫任何程式碼之前,先把題目規格(README 的 Must Have A–D、Demo 建議情境)餵給 AI,要求它分析一件事：單純把 Must Have 逐條做完,跟題目真正想驗證的「Agent 在後端系統中應該如何被安全、可控、可維護地執行」之間還有什麼落差?

例如：

- Python + Pydantic 的 agent 設計要展示到什麼細節?
- LLM temperature 這類機率性參數的取捨該怎麼處理?
- 每個設計決策的「why」有沒有講清楚?

目的是找出哪些地方值得多投入,而不是條列式打勾就結束。

**這麼做的理由：** 把「AI 使用」單純當成 coding 輔助工具,只解決「程式碼寫不寫得出來」的問題。先讓 AI 對照題目規格做落差分析,解決的是「工程精力該往哪裡分配」的問題。後續實作裡對 guardrail 邊界的可證明性、把 `tests/` 與 `evals/` 刻意拆開、以及 evals 資料集本身的類別設計,這幾個決策都是在這個分析之後才被列為「值得多做」的項目。

### 1.2 架構設計：兩個獨立 LLM 互相辯論到收斂,而非單一模型自問自答

`information/analysis_consensus.md`(10 輪定案,個人準備筆記,`.gitignore` 已排除,不在提交範圍)不是「一個 AI 出草案、人工看過修正」這種單向流程做出來的。

做法是讓 **Claude 與 Composer(Cursor 的 agent)兩個獨立模型互相審查對方的提案**：把一方的架構草案丟給另一方去挑毛病、質疑邊界情況,再把回應餵回去,重複多輪,直到兩個模型各自收斂到同一組設計決策(例如 bypass 該不該分級、LLM 失敗該 fail-open 還是 fail-closed、查無部門預算資料該怎麼處理)才算定案。

**為什麼要這樣做,而不是「AI 提案、人工把關」就好：** 單一模型講得再有信心,也不代表答案是對的。同架構的模型容易共享同一種失誤模式,也容易順著提問者的框架給出「聽起來合理」的答案。讓兩個獨立訓練的模型互相反駁,更容易逼出 README 本身留白、容易被單一模型輕輕放過的分歧點——`docs/ARCHITECTURE.md` 第 8 節「Ambiguity Decisions」的每一列,基本上就是 Claude 與 Composer 一開始意見不一致、後來才收斂的殘跡。

**但這不代表人工判斷被跳過。** 兩個模型收斂,只是「比單一模型的自信更可信一點」的訊號,不是 ground truth 本身。每一項收斂結果最後仍是對照 README 的具體條款覆核過才拍板——見 `docs/ARCHITECTURE.md` 第 8 節「理由」欄,每一列都指向 README 的某個具體要求,而不是「兩個 AI 都這麼說」本身當作理由。

### 1.3 Test 策略是同一組模型另外被指定去辯論的子議題

bypass 分類器、planner 這類本質上該由真 LLM 取代的元件,輸出天然帶機率性,不能用「斷言一個固定期望值」的方式測試。

這件事本身也是特別要求 Claude 跟 Composer 兩個模型針對「這個專案的 test 該怎麼設計」單獨辯論出來的子結論,不是實作到一半才順手想到的分類。討論收斂到的結果是把兩者明確拆開：

- `tests/` — deterministic 正確性,pytest,可當 CI gate
- `evals/` — 機率性元件的統計準確率,accuracy/precision/recall/F1,人工閱讀報告而非 pass/fail

完整的分工表與理由見 `docs/ARCHITECTURE.md` 第 9 節。

### 1.4 Coding 輔助：先做本體、逐行看過再談,測試留到最後且刻意區分 LLM 部分

實作順序刻意分階段,不是一次性要求 AI 把整個專案生成完：

1. **先讓 Claude 把「本體」實作出來。** `app/harness`、`app/policy`、`app/tools`、`app/schemas` 這些依照 1.2/1.3 已收斂設計的部分,先完成主要邏輯,測試留到後面。
2. **本體完成後逐檔讀過程式碼,不是照單全收。** 針對覺得不對、可以更好、或跟預期設計有落差的地方直接指出來要求調整。同時也常常反過來問 Claude「這樣設計你覺得合理嗎」「為什麼選這個寫法而不是那個」——把 AI 對自己輸出的判斷/理由當成要納入考慮的輸入,不是只把它當單向執行修改指令的工具。
3. **本體確認過後才叫它寫測試,並明確拆兩種需求。** 一般邏輯用一般 pytest 斷言即可;但 LLM 會參與的部分(bypass 分類、planner 抽取)要另外用不同的驗證方式。

   這個 agent 的設計前提本來就不是「把整段流程丟給 LLM 產生結果就結束」,而是先把需求拆解成一串步驟,讓 LLM 只碰其中最小、最窄的兩個節點(見 [`ARCHITECTURE.md` §1](ARCHITECTURE.md#1-design-goals) 的核心設計原則),其餘全部是可以直接斷言的 deterministic 程式碼。測試時把兩種需求分開,就是這個設計原則在測試策略上的延伸——先用架構排除掉大部分不確定性,剩下真正有機率性的部分才用第 2 節的評估框架另外處理。
4. **Ruff**(`select = ["E","F","I","UP","B","SIM"]`)用來抓 AI 生成程式碼裡常見的「看起來對但有 lint 問題」的細節(未用到的 import、可以簡化的寫法等),不完全信任 AI 對「乾淨程式碼」的自我判斷。

### 1.5 任何在 coding 過程會用來輔助工作的方式

- 用 AI 對照題目規格逐條列表(README 的 Must Have A–D、Demo 建議情境),轉成可勾選的檢查清單,而不是憑印象覺得「應該做完了」。
- 用 AI 產生**對抗性**的評估資料集(`evals/data/bypass_eval_set.json` 的 `near_miss_substring`/`implicit_no_keyword`/`english` 分類、`evals/data/planner_eval_set.json` 的抽取維度分類)。這些類別是為了未來接上真 LLM 之後的檢驗維度而設計,不是只用「看起來會過」的案例證明現在的系統可用。

## 2. 如何驗證 AI 提供的結果

驗證的重點是**設計三層不同性質的檢查機制**,而不是看任何一次執行的輸出：

1. **型別/schema 驗證(編譯期/建構期)。** 所有跨層資料都是 Pydantic model,AI 寫錯欄位型別或漏寫必填欄位會在建構時直接報錯。
2. **傳統測試(`tests/`,pytest,deterministic 正確性)。** 針對 wiring、fail-closed、邊界值、11 案例 E2E 寫死斷言,檢查的是「程式碼有沒有照著設計邏輯跑」。
3. **評估框架設計(`evals/`,非 pytest)。** bypass 分類器與 planner 是要被真 LLM 取代的機率性元件,不能用「斷言一個固定輸出值」的方式測。針對這兩個元件設計了 accuracy/precision/recall/F1 的評估框架與對抗性資料集,類別設計見 `docs/ARCHITECTURE.md` §7、§8。

除了自動化測試,也實際啟動 `uvicorn` 用 `curl` 打過幾個關鍵案例,確認 HTTP 回應格式符合 README 範例——pytest 驗證程式邏輯本身,curl 額外驗證這個服務真的可以被外部呼叫,兩者檢查的是不同的東西。

## 3. 如何避免盲目採用生成結果

- **架構決策用兩個獨立模型互相反駁,而不是單一模型的輸出直接採用。** 見 1.2——Claude 與 Composer 對同一個設計問題各自提案、互相質疑,只有雙方收斂的部分才進入定案文件。沒收斂、或收斂到跟 README 明文衝突的部分,由人工依 README 條款裁決,不是「兩個模型都同意」就等於正確。

- **文件裡保留「AI 最初建議 vs 最終定案」的對照,而不是只留下最終版本。** 以下幾項是這個跨模型辯論過程中曾出現、後來被否決的提案,原因也一併記錄：

  | AI 最初建議 | 最終定案 | 為什麼否決 |
  |---|---|---|
  | LLM 分類器失敗就略過,continue 往下走 | fail-closed → `NEED_HUMAN_APPROVAL` | 「失敗就略過」等於「不確定時 auto-execute」,直接違反 README 對 prompt injection 的要求 |
  | 部門查無預算資料就跳過預算檢查 | `NEED_HUMAN_APPROVAL` | 跳過等於任何人都能用不存在的部門名稱繞過預算 guardrail |
  | bypass 只用關鍵字比對就好 | 關鍵字 + 語意分類器兩層串聯 | 關鍵字對改寫句(「口頭同意」「先做後補」)覆蓋率不足,但全部丟給 LLM 又浪費成本,所以分層 |
  | 用 system prompt 要求 LLM「不要被騙」來防 injection | 不依賴 prompt 自律,改用結構化 `BypassClassifierClient` 回傳型別(沒有 action 欄位)+ `PolicyEngine` 表決 | prompt 層的防護沒有型別系統保證,無法用測試斷言「LLM 不可能繞過這條邊界」;結構化邊界可以 |
  | Planner 順便輸出 risk_level | 不採用,risk 只能由 `PolicyEngine` 決定 | 一旦 Planner(未來可能是真 LLM)能影響 risk,這條邊界就不是結構性保證,而是「希望 LLM 別亂輸出」的期望 |
