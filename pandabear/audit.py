"""Append-only audit logger. Every graph node writes here, success or failure.

detail payloads must already be sanitized by the caller — this module refuses
anything that looks like a credential as a last line of defense.
"""

import json
import re

from .db import get_conn

# crude but effective last-resort screens; the real protection is that
# credentials never enter the graph state in the first place
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'"private_key"\s*:'),
    re.compile(r"\b\d{9,10}:[A-Za-z0-9_-]{35}\b"),  # telegram bot token shape
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),        # openai key shape
]


def _scrub(detail: dict) -> dict:
    text = json.dumps(detail, default=str)
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            return {"scrubbed": True, "reason": "credential-shaped content blocked from audit log"}
    return detail


def log(
    request_id: str,
    node: str,
    *,
    user_id: str | None = None,
    user_role: str | None = None,
    capability_id: str | None = None,
    tool_id: str | None = None,
    policy_decision: str | None = None,
    model_used: str | None = None,
    remote_model_used: bool = False,
    credential_exposed_to_model: bool = False,
    detail: dict | None = None,
    latency_ms: int | None = None,
    status: str = "ok",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO audit_logs
               (request_id, node, user_id, user_role, capability_id, tool_id,
                policy_decision, model_used, remote_model_used,
                credential_exposed_to_model, detail, latency_ms, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request_id, node, user_id, user_role, capability_id, tool_id,
                policy_decision, model_used, int(remote_model_used),
                int(credential_exposed_to_model),
                json.dumps(_scrub(detail or {}), default=str), latency_ms, status,
            ),
        )


def trace(request_id: str) -> list[dict]:
    """Full ordered trace for one request — what the demo shows after each run."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM audit_logs WHERE request_id = ? ORDER BY id",
            (request_id,),
        ).fetchall()
