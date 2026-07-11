"""Deterministic policy engine. Deliberately model-free: the LLM decides WHAT the
user wants; this module alone decides whether they MAY have it. Rules live in the
policies table as data, so changing a limit is a row update, not a code change.
"""

import json
from dataclasses import dataclass

from .db import get_conn, loads_field


@dataclass
class PolicyResult:
    decision: str          # allow | deny | approval_required
    reason_code: str
    rule_matched: dict | None = None


def evaluate(policy_id: str | None, user_role: str, tool_args: dict) -> PolicyResult:
    """Match user_role (and optional numeric limits) against the policy's rules.
    No policy_id on the capability = default deny — capabilities must opt INTO
    being executable, never fall through to allowed."""
    if not policy_id:
        return PolicyResult("deny", "NO_POLICY_BOUND")

    with get_conn() as conn:
        policy = conn.execute("SELECT * FROM policies WHERE id = ?", (policy_id,)).fetchone()
    if not policy:
        return PolicyResult("deny", "POLICY_NOT_FOUND")

    loads_field(policy, "rules")
    for rule in policy["rules"]:
        if rule.get("role") != user_role:
            continue
        limit = rule.get("limit")
        if limit is not None:
            amount = _numeric_arg(tool_args)
            if amount is not None and amount > limit:
                return PolicyResult("approval_required", "AMOUNT_EXCEEDS_LIMIT", rule)
        return PolicyResult(rule["decision"], "RULE_MATCHED", rule)

    return PolicyResult(policy["default_decision"], "DEFAULT_DECISION")


def _numeric_arg(tool_args: dict) -> float | None:
    """First numeric arg named like a quantity/amount, for limit checks."""
    for key in ("amount", "quantity", "total", "value", "count"):
        v = tool_args.get(key)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def record_pending_approval(request_id: str, capability_id: str, tool_args: dict, user_id: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pending_approvals (request_id, capability_id, tool_args, user_id)
               VALUES (?,?,?,?)""",
            (request_id, capability_id, json.dumps(tool_args), user_id),
        )
        return cur.lastrowid
