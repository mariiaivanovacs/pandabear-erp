"""Seed the metadata DB with the demo domain/capability/policy/tool rows.
Idempotent — safe to re-run. Run: uv run python scripts/seed_demo.py"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pandabear.db import get_conn, init_db  # noqa: E402


def upsert(conn, table: str, row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
        tuple(row.values()),
    )


def main() -> None:
    init_db()
    with get_conn() as conn:
        upsert(conn, "domains", {
            "id": "inventory",
            "name": "Inventory",
            "description": "Stock levels, reorder checks, supplier info",
            "aliases": json.dumps(["stock", "supplies", "warehouse"]),
        })

        upsert(conn, "policies", {
            "id": "inventory_read_policy",
            "action": "inventory.read",
            "rules": json.dumps([
                {"role": "branch_manager", "decision": "allow"},
                {"role": "barista", "decision": "deny"},
                {"role": "ops_manager", "decision": "allow"},
            ]),
            "default_decision": "deny",
        })

        upsert(conn, "tools", {
            "id": "check_stock",
            "type": "read_connector",
            "entrypoint": "tools.demo.check_stock.run",
            "file_path": "tools/demo/check_stock.py",
            "input_schema": json.dumps({
                "type": "object",
                "properties": {
                    "product": {"type": "string", "description": "Product name, e.g. 'oat milk'"},
                    "branch": {"type": "string", "description": "Branch number or name, e.g. '5'"},
                },
                "required": ["product", "branch"],
            }),
            "credential_scope": None,      # demo tool: no credential; Firebase version binds one
            "generated_by": "human",
            "human_approved": 1,
            "status": "active",
        })

        upsert(conn, "capabilities", {
            "id": "inventory_check_stock",
            "domain_id": "inventory",
            "intent": "inventory.stock.check",
            "description": "Check current stock level, reorder threshold, and days of stock "
                           "left for a product at a specific branch.",
            "example_utterances": json.dumps([
                "can we reorder oat milk for branch 5",
                "how much espresso is left at branch 2",
                "is branch 5 low on oat milk",
            ]),
            "required_entities": json.dumps(["product", "branch"]),
            "tool_id": "check_stock",
            "policy_id": "inventory_read_policy",
            "risk_level": 1,
            "requires_approval": 0,
            "remote_model_allowed": 0,
            "status": "active",
        })
    print("seeded: 1 domain, 1 policy, 1 tool, 1 capability")


if __name__ == "__main__":
    main()
