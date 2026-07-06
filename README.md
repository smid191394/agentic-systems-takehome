# Procurement Approval Agent

一個示範「Agent 應該如何在後端系統中被安全、可控、可維護地執行」的 MVP 採購簽呈 Agent。使用者以自然語言描述採購需求,系統透過一個明確分層的 Agent Harness（Planner → Tool Registry → Policy Engine → Approval Gate）判斷應該建立草稿、轉人工簽核、拒絕,還是要求補件。

原始題目規格見 [`docs/README.md`](docs/README.md)（中文）/ [`docs/README.en.md`](docs/README.en.md)（英文）,來自 [stark-tech-space/agentic-systems-takehome](https://github.com/stark-tech-space/agentic-systems-takehome)。本檔案是專案本身的使用說明。

## 交付文件

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Agent Loop、Layer Boundaries、Tool/Approval Boundary、Schema Validation、policy_004 雙層 bypass 設計、evals 資料集設計
- [`docs/AI_USAGE.md`](docs/AI_USAGE.md) — 開發過程中 AI 工具的使用與驗證方式

## 快速開始

```bash
uv sync
uv run uvicorn main:app --reload
```

啟動後呼叫：

```bash
curl -X POST localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "u_001",
    "department": "marketing",
    "message": "請幫行銷部採購 3 個 Figma Enterprise seat，總預算控在 3000 美金以內。"
  }'
```

範例回應：

```json
{
  "run_id": "83003939-...",
  "status": "COMPLETED",
  "decision": {
    "action": "CREATE_DRAFT_PO",
    "risk_level": "LOW",
    "requires_human_approval": false,
    "reason": "Request complies with policy."
  },
  "draft_po": {
    "item": "Figma Enterprise Seat",
    "quantity": 3,
    "estimated_total": 2400.0,
    "department": "marketing"
  },
  "tool_calls": [
    {"tool": "lookup_catalog", "status": "success"},
    {"tool": "check_policy", "status": "success"},
    {"tool": "create_draft_po", "status": "success"}
  ]
}
```

若 `decision.action == "NEED_HUMAN_APPROVAL"`,可另外呼叫（加分項）：

```bash
curl -X POST localhost:8000/agent/runs/{run_id}/approve \
  -H "Content-Type: application/json" -d '{"approved": true}'
```

## 測試與評估

```bash
# 傳統 pytest：deterministic 正確性（wiring、fail-closed、邊界值、11 案例 E2E）
uv run pytest

# Demo：跑過 tests/data/requests.json 的 11 個案例，印出每筆的 decision/reason/draft_po
uv run scripts/demo.py

# LLM-step 準確率報告：bypass 分類器 / planner 抽取的 accuracy/precision/recall/F1
uv run -m evals.run_bypass_eval
uv run -m evals.run_planner_eval
```

為什麼分成 `tests/` 與 `evals/` 兩套、各自測什麼、量化結果如何,見 [`docs/ARCHITECTURE.md` 第 9 節](docs/ARCHITECTURE.md#9-測試與評估)。

## 專案結構

```text
app/            # harness / planner / policy / tools / schemas（見 ARCHITECTURE.md §3）
fixtures/       # catalog.json / policies.json / budgets.json（題目提供)
tests/          # pytest：正確性測試
evals/          # LLM-step 準確率評估（非 pytest）
scripts/        # demo.py — 跑 11 個案例並印出結果
docs/           # ARCHITECTURE.md、AI_USAGE.md、原始題目規格
```
