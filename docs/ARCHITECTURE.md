# ARCHITECTURE

## 1. Design Goals

題目要求驗證的是「Agent 在後端系統中應該如何被安全、可控、可維護地執行」,不是把一個真的大型系統做出來。

本專案不是「把需求丟給 LLM,讓它產生結果就結束」。所有目標都服務於一個上層原則：

> **把 LLM／機率性判斷的參與面積縮到最小,其餘全部 deterministic。**

固定的 8 步 Agent Loop(第 2 節)裡,只有 2 步碰到機率性判斷：

- 第 2 步 `Planner.parse()` — 自然語言 → 結構化欄位
- 第 5 步內部的 `BypassClassifier.classify()` — 單一句子 → 單一 `suspicious: bool` 信號

其餘 6 步(harness 驗證、`lookup_catalog`、`PolicyEngine` 規則裁決、`create_draft_po`、schema 驗證)都是可以直接用邏輯推導、直接斷言期望值的 deterministic Python。

這樣拆解的好處：不確定性不會擴散到整個系統。兩個窄點各自有針對性的評估資料集(`evals/`,見第 7、8、9 節);其餘部分的可靠度直接靠 pytest 的 deterministic 斷言保證,不需要「相信 LLM 大致上是對的」這種籠統假設。

由此展開的具體目標：

1. **邊界清楚可證明**
   Planner 的輸出不能繞過 `check_policy`,也不能直接呼叫 `create_draft_po`。這條邊界要能被單元測試直接斷言,不能只靠 code review 口頭保證。

2. **裁決集中、單一來源**
   只有 `PolicyEngine` 能產生最終 `decision.action`;bypass 分類只能產生「信號」,不能直接產生「決策」。`BypassClassifierClient` 的回傳型別(`BypassLLMResult`)裡沒有 `action` 欄位,LLM 結構上不可能繞過這條邊界去直接影響結果。

3. **fail-closed 優先於 fail-open**
   任何不確定的狀態(分類器失敗、部門查無預算)一律轉人工,不自動放行。

4. **可替換性用型別系統保證,不是文件承諾**
   `Planner` Protocol、`BypassClassifierClient` Protocol 讓「未來換成真 LLM」只是新增一個實作類別的動作,不需要改動 harness/engine 的呼叫方。

5. **兩個窄點各自設計對抗性評估資料集**
   Bypass 分類器與 planner 是目前用 deterministic 規則模擬、未來要換成真 LLM 的兩個窄點。針對它們設計的評估資料集(`evals/data/*.json`)分好類別,是為了讓真的 LLM 接上去之後評估結果才有意義(見第 7、8、9 節),不是為了衡量目前這兩個占位元件本身準不準。

## 2. Agent Loop

`app/harness/runner.py` 的 `AgentHarness.run()` 是唯一固定的編排入口,8 步順序寫死,不受 Planner 輸出影響：

```text
1. 初始化 RunState（run_id、department）
2. Planner.parse(department, message) -> PlannerOutput
3. Harness 驗證：item_query 缺 -> ASK_CLARIFICATION
                 quantity 缺  -> ASK_CLARIFICATION
                 quantity<=0 -> REJECT
4. lookup_catalog(item_query, raw_message)
     -> not_found  -> ASK_CLARIFICATION
     -> ambiguous  -> ASK_CLARIFICATION
     -> found      -> 繼續
5. check_policy(raw_message, department, item, quantity)   # 無條件呼叫
     內部：bypass 雙層評估 -> 品類/金額/部門預算規則 -> action
6. action ∈ {REJECT, NEED_HUMAN_APPROVAL} -> 組 Decision，提早返回（不呼叫 create_draft_po）
7. action == CREATE_DRAFT_PO -> create_draft_po(item, quantity, department)
8. 組 AgentRunResponse（Pydantic 驗證）-> 返回
```

每一步的輸入輸出都是 Pydantic model(`PlannerOutput`、`LookupCatalogOutput`、`PolicyEvaluation`、`DraftPO`)。任何一步丟例外都會被 `ToolRegistry` 攔截,記成 `tool_calls` 裡的 `"error"` 項目,不會讓例外裸露到 API 層變成未分類的 500。

## 3. Layer Boundaries

| 層 | 檔案 | 職責 | 不做的事 |
|---|---|---|---|
| API | `app/api/routes.py` | 接收 HTTP request、組裝依賴、呼叫 harness | 不含任何業務判斷 |
| Harness | `app/harness/runner.py`、`state.py` | 固定編排 8 步、維護 `RunState`、把內部決策轉成公開 API schema | 不自己做風險判斷 |
| Planner | `app/planner/base.py`(Protocol)、`rule_based.py` | 自然語言 -> `PlannerOutput`(department/item_query/quantity/budget_cap_usd) | 不輸出 risk/action,不決定呼叫哪個工具 |
| Tools | `app/tools/registry.py`、`catalog.py`、`draft.py`、`policy_tool.py` | 執行單一動作、驗證輸入、記錄 trace | catalog 知識只活在 `catalog.py`;`registry.py` 不含判斷邏輯,只做 dispatch + trace |
| Policy | `app/policy/engine.py`(deterministic 裁決)、`bypass.py`(非確定性信號) | 產生唯一的 `action` | LLM/分類器不得直接輸出 action——這條邊界靠檔案切分＋型別(`BypassAssessment` 沒有 action 欄位)雙重保證 |
| Schemas | `app/schemas/domain.py`(內部)、`api.py`(公開 HTTP contract) | 每一層之間的資料都經過 Pydantic 驗證 | 內部模型不外露;公開模型不包含 bypass 細節 |

這條分層不只是文件宣稱,測試上可以直接驗證：

- `tests/test_bypass.py` 用 `_SpyClassifier` 直接斷言 pattern 命中時分類器 `calls == 0`。
- `tests/test_policy_engine.py` 直接建構合成的 `PoliciesConfig`/`DepartmentBudget`,繞過 fixtures 檔案精確測邊界值,證明 `PolicyEngine` 的裁決不依賴任何外部呼叫順序。

## 4. Tool Boundary

三個必要工具都經過 `ToolRegistry` 單一入口(`app/tools/registry.py`)分派,不是 Planner 直接呼叫：

- **`lookup_catalog`**(`tools/catalog.py`)
  輸入 `item_query`/`raw_message`,同時掃描兩者比對 `catalog.json` 的 name/aliases,回傳 `found`/`not_found`/`ambiguous`(含 `matched_item_ids`)。這是**唯一**知道品類/別名對照表的地方。

- **`check_policy`**(`tools/policy_tool.py`)
  薄包裝,直接轉呼叫 `PolicyEngine.evaluate()`。獨立成一個「工具」而不是讓 harness 直接呼叫 engine,是為了保留「這是一個會被記錄進 `tool_calls` trace 的動作」這個語意,對齊 README 的工具清單。

- **`create_draft_po`**(`tools/draft.py`)
  純函式,`estimated_total = quantity * unit_price`,組出 `DraftPO`。**只有** harness 第 7 步、且僅在 `PolicyEngine` 回傳 `CREATE_DRAFT_PO` 之後才會被呼叫——這是結構性保證,不是執行期檢查;Planner 沒有任何管道可以指定要跳到第 7 步。

- **`submit_to_erp`**(原規格 optional)
  **刻意不實作**。它在本專案沒有實質行為——沒有真的 ERP 對接,沒有前端會觸發,只會是一個空殼函式。加了反而是「看起來完整但沒有真邏輯」的假模組化,故移除。

**Tool input validation：** 每個工具的參數都是型別化的 Python 參數(非 dict),`catalog.py`/`draft.py`/`policy_tool.py` 內部直接使用 Pydantic model(`CatalogItem`、`PolicyEvaluation`)。不存在「直接把 Planner 輸出的 dict 轉丟給工具」的路徑——`PlannerOutput` 本身先經過 harness 第 3 步的驗證(缺欄位/非正數量),才會被拿去呼叫任何工具。

## 5. Approval Gate

**結構性保證(非執行期檢查)：**

- Harness 第 5 步 `check_policy` 是**無條件**呼叫,`AgentHarness.run()` 裡沒有任何分支可以跳過它。
- 第 7 步 `create_draft_po` 只在第 5 步回傳 `action == "CREATE_DRAFT_PO"` 時才會被呼叫(`runner.py:120-121`)。Planner 沒有任何輸出欄位可以影響這個分支——即使把 Planner 換成一個真的、可能被 prompt injection 操控的 LLM,這條路徑仍然由 harness 決定。
- 高風險動作(`REJECT`/`NEED_HUMAN_APPROVAL`)與低風險動作(`CREATE_DRAFT_PO`/`ASK_CLARIFICATION`)的對照表寫死在 `runner.py` 的 `_RISK_BY_ACTION`,從 `action` 這個單一枚舉值單向映射出來,避免 risk_level 與 action 不同步。

**HITL 流程(加分項,已實作)：**

```text
POST /agent/runs/{run_id}/approve   {"approved": true|false}
```

- 只有 `state.action == "NEED_HUMAN_APPROVAL"` 且 `approval_status == "PENDING"` 的 run 能被 approve/reject,否則回 409(見 `tests/test_approval_gate.py`：重複 approve、對已完成/已拒絕的 run approve 都會被拒絕)。
- 對不存在的 `run_id` 回 404。
- `RunState` 目前存在 harness 的記憶體 dict(`self._runs`)中,重啟後遺失——這是 MVP 的已知取捨,不影響 approval boundary 邏輯本身。

## 6. Schema Validation

- **Final output schema validation：** `AgentRunResponse`(`schemas/api.py`)是 FastAPI 的 `response_model`,任何回傳值都先過 Pydantic 驗證才序列化。內部欄位(`Decision.risk_level`、`.action`)都用 `Literal[...]` 限制枚舉值——拼錯字或新增未列舉的 action 會在測試/開發期就直接炸掉,不會靜默序列化出一個下游看不懂的字串。
- **Tool input validation：** 每個工具函式的參數都是具體型別(`CatalogItem`、`int`、`str`),不是 `dict[str, Any]`。`PlannerOutput` 本身也是 Pydantic model,任何非預期型別在建構時就會被拒絕,不會流到工具內部才炸。
- **內部 vs 公開模型分離：** `schemas/domain.py`(`PlannerOutput`、`BypassAssessment`、`PolicyEvaluation` 等)與 `schemas/api.py`(`AgentRunRequest`、`AgentRunResponse`)刻意分成兩份。bypass 判斷的細節(`pattern_hit`、`llm.suspicious`、`llm_error`)只寫入 `RunState.trace`,供內部使用與測試斷言,不會流出到公開 HTTP 回應。

## 7. Prompt Injection / policy_004：雙層 bypass

**設計原則：** 關鍵字先審(快、穩、零成本),未命中才進第二層語意判斷。**裁決永遠在 `PolicyEngine`**,分類器只回傳 `suspicious: bool`。

```text
raw_message
    │
    ▼
Layer A — pattern_hit()（app/policy/bypass.py）
  BYPASS_PATTERNS = ["忽略","跳過","不需核准","不要核准","直接送出","直接下單",
                      "ignore policy","bypass","skip approval"]
    ├─ 命中 → REJECT（PolicyEngine 規則 1a），不呼叫 Layer B
    └─ 未命中
          ▼
Layer B — BypassClassifierClient.classify()
    ├─ suspicious=true  → NEED_HUMAN_APPROVAL（規則 1b）
    ├─ suspicious=false → 繼續規則 2–5（品類/金額/預算）
    └─ 分類器丟例外 / 未設定 client → NEED_HUMAN_APPROVAL + llm_error（fail-closed）
```

**LLM 邊界：** `BypassClassifierClient` 只回答「這句話是否嘗試繞過核准」(`suspicious` + `reason`)。型別上沒有任何欄位可以讓它直接輸出 `action`。即使未來換成真的 LLM,Prompt 怎麼寫都無法繞過這條邊界,因為 `PolicyEngine.evaluate()` 只讀 `BypassAssessment.pattern_hit`/`.llm.suspicious`/`.llm_error`——結構上不存在「LLM 說了算」的路徑。

**目前的 Layer B 實作：** `RuleBasedBypassClassifier`,一組比 Layer A 更寬鬆的中文軟性詞彙表(`SOFT_BYPASS_SIGNALS`,如「省略審核」「口頭同意」「先做後補」),deterministic、不打任何外部 API。`BypassClassifierClient` Protocol 保留,未來要接真 LLM 只需新增一個實作類別,不動 `PolicyEngine`/`ToolRegistry`。

**`evals/data/bypass_eval_set.json` 的設計：** 40 筆案例分成幾個類別,各對應一種真實語意分類器可能會犯的錯誤模式：

| 類別 | 目的 | 範例 |
|---|---|---|
| `soft_paraphrase` | 委婉改寫 | 「省略審核流程」 |
| `authority_claim` | 權威背書話術 | 「老闆已經同意了」 |
| `urgency` | 急迫話術 | — |
| `near_miss_substring` | 軟性詞出現但拆散不連續,考驗是否只做 naive substring match | — |
| `implicit_no_keyword` | 純語意隱含,完全沒有字面觸發詞 | — |
| `english` | 英文改寫 | — |
| `false_positive_bait` | 容易被誤判成可疑,但實際上只是在描述既有流程的正常語句 | 「這筆已經過內部審核流程確認需求」 |
| `benign` | 一般業務語句 | — |

這份資料集要評估的對象是**未來真的接上去的 LLM 分類器**。`RuleBasedBypassClassifier` 只是 Layer B 這個角色本該由 LLM 做的 deterministic 占位實作,類別設計本身才是重點：接上真 LLM 之後,`run_bypass_eval.py` 的 `CONFIGS` 可以直接套用這份資料集。

**Fallback 矩陣：**

| pattern_hit | llm_called | llm | llm_error | action |
|---|---|---|---|---|
| true | false | — | — | REJECT |
| false | true | suspicious=true | — | NEED_HUMAN_APPROVAL |
| false | true | suspicious=false | — | 繼續規則 2–5 |
| false | true | — | 有值 | NEED_HUMAN_APPROVAL（fail-closed） |

README 對 prompt injection 允許 `REJECT` 或 `NEED_HUMAN_APPROVAL` 兩種結果都算合理。本專案的分級是：pattern 命中(高確定性字面繞過)→ REJECT;語意層可疑或分類器失敗(較低確定性)→ NEED_HUMAN_APPROVAL,把誤判風險交給人工覆核,而不是靜默放行或一律硬拒絕。

## 8. Ambiguity Decisions

題目規格留白、實作時需要自行定案的地方：

| 議題 | 定案 | 理由 |
|---|---|---|
| 部門查無預算資料(如 `sales`) | `NEED_HUMAN_APPROVAL`,**不是**跳過規則 4、也不是 422 | 若「查無資料」直接放行,等於任何人都能用一個不存在的部門繞過預算檢查 |
| LLM/分類器失敗 | fail-closed → `NEED_HUMAN_APPROVAL` | README 的「不可照此執行」解讀為「不可 auto-execute」;不確定時轉人工比靜默放行安全 |
| 語意 bypass 的分級 | pattern → REJECT;LLM suspicious → NEED_HUMAN_APPROVAL | pattern 是高確定性的字面證據;語意判斷有誤判風險,交給人工覆核而非直接拒絕 |
| 多條規則同時命中時的 `reason` | 聚合所有命中原因(`; ` join),不是只取第一條 | 使用者/審核者需要知道「為什麼」的完整原因,只列第一條會誤導後續溝通 |
| 多品項請求 | 交給 `lookup_catalog` 判 `ambiguous`,不在 Planner 層特殊處理 | 品類知識只活在 catalog 工具;Planner 不需要知道 catalog 內容才能運作 |
| Planner 抽取失敗時的 fallback(含中文數字「十個」等 `RuleBasedPlanner` 抓不到的情況) | 一律落回 `missing_quantity`/`missing_item` → `ASK_CLARIFICATION`,不猜測 | `RuleBasedPlanner` 是 Planner 這個角色本該交給 LLM 做的 deterministic 占位實作;不管抽取失敗的具體原因是什麼,安全的 fallback 都是問清楚,不會誤判成 0 或忽略 |
| `budgets.json` 是否跨 run 遞減 | 不遞減,每次都用同一份靜態值比對 | MVP 讀唯讀 fixture,本專案要驗證的是 agent 架構設計能力,不含跨請求的交易/併發控制 |
| `fixtures/sample_requests.json`(原始 repo 提供,5 個官方案例) | 移到 `tests/data/requests.json`,與自訂的 7 個案例合併,用 `source: "official"/"custom"` 欄位區分 | 官方 5 案例與自訂案例本質上是同一種東西(帶 `expected_behavior` 的案例矩陣),拆兩個檔案維護反而容易漏改;`case_005` 的 `expected_behavior` 從原始的 `NEED_HUMAN_APPROVAL_OR_REJECT` 具體化為 `REJECT`,對應第 7 節的分級決策 |

**`evals/data/planner_eval_set.json` 的設計：** 26 筆案例涵蓋幾個抽取維度——量詞單位變體(個/台/臺/seats)、預算金額抽取、多品項、部門文字干擾(訊息裡提到別的部門但不影響 `request.department`)、貨幣單位變體。這些維度對應的是「一個真的做自然語言抽取的元件」該被檢查的地方。

`RuleBasedPlanner` 目前是 regex-based 的 deterministic 占位實作,本身就是 Planner 這個角色該交給 LLM 做的事。這份資料集的類別設計,才是接上真的 LLM-backed planner 之後 `run_planner_eval.py` 用來檢查它的地方。

## 9. 測試與評估

測試分成兩個檔案系統、兩種不同的正確性主張,不是隨意分類：

| | `tests/`（pytest） | `evals/`（獨立腳本,非 pytest） |
|---|---|---|
| 驗證對象 | Harness/PolicyEngine/ToolRegistry 的 wiring 與邊界邏輯 | Planner、BypassClassifier 這類「本質上該被 LLM 取代」的機率性元件 |
| 正確性主張 | deterministic：給定輸入,輸出必須完全符合斷言 | 統計：accuracy/precision/recall/F1,允許一定比例的錯誤 |
| 執行方式 | `uv run pytest`,可直接當 CI gate,失敗即阻斷 | `uv run -m evals.run_bypass_eval` / `run_planner_eval`,人工閱讀報告,不是 pass/fail gate |
| 資料集 | `tests/data/requests.json`（12 案例,含 `expected_behavior`） | `evals/data/bypass_eval_set.json`（40 筆,對抗性分類）、`evals/data/planner_eval_set.json`（26 筆,抽取維度分類） |

**檔案對應：**

| 檔案 | 測什麼 |
|---|---|
| `tests/test_bypass.py` | Layer A/B 串聯、pattern 短路(`assert spy.calls == 0`)、fail-closed |
| `tests/test_policy_engine.py` | 金額/預算邊界值、unknown department、reason 聚合 |
| `tests/test_catalog.py` | alias、ambiguous 多品項 |
| `tests/test_harness.py` | 12 案例(官方 5 + 自訂 7)E2E |
| `tests/test_api.py` | HTTP 層 wiring、422 vs 200、unknown department 不誤觸 422 |
| `tests/test_approval_gate.py` | approve 端點的狀態機(重複 approve、對非 PENDING 的 run approve) |

`run_bypass_eval.py`/`run_planner_eval.py` 目前用 `OracleBypassClassifier`/`OraclePlanner` 驗證這套報表機制(accuracy/precision/recall/F1)本身能跑。兩份資料集的類別設計(見第 7、8 節)才是要展示的東西——等接上真的 LLM-backed classifier/planner,同一套腳本就能套用。
