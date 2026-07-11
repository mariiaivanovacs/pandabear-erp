"""Capability/tool registry. Turns SQLite rows into OpenAI-format tool schemas so
the model chooses capabilities by real function-calling — the model only ever sees
capability ids, descriptions, and business-level argument schemas. Never file
paths, entrypoints, or credential scopes.
"""

from .db import get_conn, loads_field


def active_capabilities() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, t.input_schema, t.status AS tool_status, t.human_approved
               FROM capabilities c LEFT JOIN tools t ON t.id = c.tool_id
               WHERE c.status = 'active'"""
        ).fetchall()
    return [
        loads_field(r, "example_utterances", "required_entities", "input_schema")
        for r in rows
        if r["tool_status"] == "active" and r["human_approved"]
    ]


def get_capability(capability_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM capabilities WHERE id = ?", (capability_id,)
        ).fetchone()
    return loads_field(row, "example_utterances", "required_entities") if row else None


def get_tool(tool_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tools WHERE id = ?", (tool_id,)).fetchone()
    return loads_field(row, "input_schema", "output_schema") if row else None


def as_openai_tools() -> list[dict]:
    """The function-calling surface the agent node binds. One function per active,
    approved capability."""
    tools = []
    for cap in active_capabilities():
        schema = cap.get("input_schema") or {"type": "object", "properties": {}}
        desc = cap["description"]
        if cap.get("example_utterances"):
            examples = "; ".join(cap["example_utterances"][:3])
            desc = f"{desc} Example requests: {examples}"
        tools.append(
            {
                "type": "function",
                "function": {"name": cap["id"], "description": desc, "parameters": schema},
            }
        )
    return tools
