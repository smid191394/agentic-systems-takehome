"""submit_to_erp (optional/bonus) — the approval gate lives in ToolRegistry, not here."""


def submit_to_erp(run_id: str) -> dict:
    return {"erp_reference": f"erp-{run_id}", "status": "submitted"}
