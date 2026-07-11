"""Demo stock-check tool — local fixture data, no external system.

Exists so the full graph (agent → policy → executor → respond) can be exercised
and audited before Firebase credentials are wired in. The Firebase version keeps
the same input/output contract and replaces this row in the tools table.

Contract: argv[1] = JSON args, stdout = JSON result, exit 0 on success.
"""

import json
import sys

FIXTURE = {
    ("oat milk", "5"): {"stock": 4, "threshold": 20, "supplier_lead_days": 3, "daily_usage": 15},
    ("espresso beans", "5"): {"stock": 40, "threshold": 25, "supplier_lead_days": 2, "daily_usage": 6},
    ("oat milk", "2"): {"stock": 30, "threshold": 20, "supplier_lead_days": 3, "daily_usage": 10},
}


def run(args: dict) -> dict:
    product = str(args.get("product", "")).strip().lower()
    branch = str(args.get("branch", "")).strip().lower().removeprefix("branch").strip()
    row = FIXTURE.get((product, branch))
    if row is None:
        return {
            "found": False,
            "product": product,
            "branch": branch,
            "message": "no inventory record for this product/branch",
        }
    reorder_needed = row["stock"] < row["threshold"]
    days_left = round(row["stock"] / row["daily_usage"], 1) if row["daily_usage"] else None
    return {
        "found": True,
        "product": product,
        "branch": branch,
        **row,
        "reorder_needed": reorder_needed,
        "estimated_days_of_stock_left": days_left,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}"))))
    except Exception as e:  # tool contract: errors to stderr, non-zero exit
        print(str(e), file=sys.stderr)
        sys.exit(1)
