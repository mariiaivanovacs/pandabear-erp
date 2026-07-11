"""New-source onboarding — the ideal_arhc.md bootstrap pipeline, one source at a time.

A SEPARATE model session (nothing shared with the chat graph) walks these steps:

  1. plan      — model reads the admin's source description and produces the list
                 of credential fields it NEEDS (names/shapes only).
  2. bind      — admin supplies the actual values via UI/API; they go STRAIGHT
                 into the vault + a credential_binding. The session model never
                 sees them — it asked for names, it gets back "bound".
  3. probe     — connection test + structure discovery through the human-authored
                 platform probe tool (vault-scoped subprocess). The model receives
                 field NAMES and TYPES only, never values. This is the only way
                 any model ever touches the source.
  4. generate  — admin states goals; the model maps goals -> capability specs;
                 each spec goes through toolgen (airgap AST gate + contract check)
                 and is sandbox-verified against the live source via the executor.
  5. finalize  — capabilities/policies are registered (tools stay unapproved for
                 the admin's explicit Approve step in the panel), and the session
                 transcript is WIPED (ideal_arhc.md phase 4: context destroy).
"""

import json
import re
import uuid

from . import audit, models, toolgen, vault
from .db import get_conn
from .executor import ToolExecutionError, execute
from .registry import get_tool

_sessions: dict[str, dict] = {}

PLAN_SYSTEM = """You are PandaBear's source-onboarding planner. The admin describes a
data source they want to connect. Respond ONLY with JSON:
{
  "source_kind": "firestore|rtdb|postgres|mysql|rest_api|unknown",
  "sdk": "python package name to use",
  "credential_fields": [{"name": "...", "description": "...", "secret": true|false}],
  "notes": "one short sentence of guidance for the admin"
}
You are planning credential REQUIREMENTS only. You will never receive the values."""

# source_kind -> the human-authored platform probe tool that knows how to connect
# to it (schema/structure discovery only, never values). The plan step above can
# suggest ANY source_kind — the model doesn't know what's actually implemented —
# so probe() checks this table and fails honestly for kinds with no connector yet,
# instead of running a mismatched probe tool against the wrong credential shape.
_PROBE_TOOLS: dict[str, dict] = {
    "firestore": {
        "id": "fb_probe",
        "entrypoint": "tools.platform.fb_probe.main",
        "file_path": "tools/platform/fb_probe.py",
    },
    "postgres": {
        "id": "pg_probe",
        "entrypoint": "tools.platform.pg_probe.main",
        "file_path": "tools/platform/pg_probe.py",
    },
}

GOALS_SYSTEM = """You design capability specs for approved deterministic tools.
Input: a source structure (collection/field names and types ONLY) and the admin's goals.
Respond ONLY with JSON:
{"capabilities": [{
  "id": "snake_case_id",
  "description": "what it checks/does, one sentence",
  "example_utterances": ["...", "...", "..."],
  "input_schema": {"type": "object", "properties": {...}, "required": [...]},
  "output_fields": {"field": "what it means"},
  "collection": "which collection it reads",
  "allowed_roles": ["branch_manager", "ops_manager"]
}]}
Rules: read-only capabilities only; inputs are business-level arguments (never SQL,
never raw queries); output_fields is the STRICT contract — nothing else will pass."""


def start(source_description: str) -> dict:
    """Step 1: model plans what credentials this source needs."""
    session_id = uuid.uuid4().hex[:10]
    msg, model_used, _ = models.chat(
        [{"role": "system", "content": PLAN_SYSTEM},
         {"role": "user", "content": source_description}],
        force_cloud=True,
    )
    plan = _parse_json(msg.content or "{}")
    _sessions[session_id] = {
        "source_description": source_description,
        "plan": plan,
        "transcript": [f"planned via {model_used}"],
        "vault_ref": None,
        "credential_scope": None,
        "structure": None,
        "generated": [],
    }
    audit.log(session_id, "onboarding_plan", model_used=model_used, remote_model_used=True,
              detail={"credential_fields_requested": [f.get("name") for f in plan.get("credential_fields", [])]})
    return {"session_id": session_id, **plan}


def bind_credentials(session_id: str, source_name: str, secret: dict | str) -> dict:
    """Step 2: actual values go UI -> vault, bypassing every model context."""
    s = _session(session_id)
    ref = f"vault://{source_name}/onboarded"
    scope = f"{source_name}.access"
    vault.seed_secret(ref, secret)

    source_kind = (s.get("plan") or {}).get("source_kind", "")
    probe_tool_id = _PROBE_TOOLS.get(source_kind, {}).get("id")
    allowed_tools = [probe_tool_id] if probe_tool_id else []

    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO credential_bindings
               (id, credential_scope, vault_ref, allowed_tools, model_visible)
               VALUES (?,?,?,?,0)""",
            (f"{source_name}_binding", scope, ref, json.dumps(allowed_tools)),
        )
    s["vault_ref"], s["credential_scope"], s["source_name"] = ref, scope, source_name
    s["transcript"].append("credentials bound (values never entered a model context)")
    audit.log(session_id, "onboarding_bind", credential_exposed_to_model=False,
              detail={"vault_ref": ref, "scope": scope})
    return {"bound": True, "vault_ref": ref}


def probe(session_id: str) -> dict:
    """Step 3: connection test + structure discovery THROUGH the probe tool."""
    s = _session(session_id)
    if not s["credential_scope"]:
        raise ValueError("bind credentials first")

    source_kind = (s.get("plan") or {}).get("source_kind", "unknown")
    probe_tool = _PROBE_TOOLS.get(source_kind)
    if not probe_tool:
        supported = ", ".join(sorted(_PROBE_TOOLS)) or "(none yet)"
        error = (f"PandaBear doesn't have a connector for '{source_kind}' yet — today it "
                 f"ships: {supported}. Adding one is a new platform probe tool "
                 f"(same pattern as tools/platform/fb_probe.py), not a credential problem.")
        audit.log(session_id, "onboarding_probe", status="error",
                  detail={"source_kind": source_kind, "error": error})
        return {"connected": False, "error": error}

    _ensure_probe_tool(probe_tool, s["credential_scope"])
    try:
        out = execute(get_tool(probe_tool["id"]), {"sample_per_collection": 3}, sandbox=True)
    except ToolExecutionError as e:
        audit.log(session_id, "onboarding_probe", status="error", detail={"internal": e.internal_detail[:500]})
        return {"connected": False, "error": e.public_message}
    if not out.get("connected"):
        error = "Connected tool ran but reported no successful connection — check the credential values."
        audit.log(session_id, "onboarding_probe", status="error",
                  detail={"source_kind": source_kind, "error": error})
        return {"connected": False, "error": error}
    s["structure"] = out.get("collections", {})
    s["transcript"].append(f"probed: {list(s['structure'])}")
    audit.log(session_id, "onboarding_probe",
              detail={"connected": True, "collections": list(s["structure"])})
    return {"connected": True, "collections": s["structure"]}


def _tool_system_context(source_kind: str, spec: dict, structure: dict, output_schema: dict) -> str:
    table = spec.get("collection")
    fields = json.dumps(structure.get(table, {}))
    out_fields = json.dumps(list(output_schema["properties"]))

    if source_kind == "postgres":
        return (
            f"PostgreSQL via psycopg2; credential JSON in env PANDABEAR_CREDENTIAL with keys "
            f"host, port, database, user, password — connect with psycopg2.connect(**those).\n"
            f"Table '{table}', columns (name->type): {fields}\n"
            f"SECURITY: build the query with a parameterized statement — "
            f"cur.execute(\"SELECT ... WHERE col = %s\", (value,)) — NEVER with an f-string, "
            f"%-format, or .format() on user-supplied input. This is a hard requirement, not a "
            f"style preference: string-built SQL is a SQL-injection vulnerability.\n"
            f"Output ONLY these fields: {out_fields}"
        )
    # default: firestore
    return (
        f"Firestore via firebase_admin; credential JSON in env PANDABEAR_CREDENTIAL.\n"
        f"Collection '{table}', fields (name->type): {fields}\n"
        f"Output ONLY these fields: {out_fields}"
    )


def generate(session_id: str, goals: str) -> dict:
    """Step 4: goals -> capability specs -> airgap-gated toolgen -> sandbox verify."""
    s = _session(session_id)
    if s["structure"] is None:
        raise ValueError("probe the source first")

    msg, model_used, _ = models.chat(
        [{"role": "system", "content": GOALS_SYSTEM},
         {"role": "user", "content":
             f"Source structure (names/types only):\n{json.dumps(s['structure'])}\n\nAdmin goals:\n{goals}"}],
        force_cloud=True,
    )
    specs = _parse_json(msg.content or "{}").get("capabilities", [])
    s["transcript"].append(f"designed {len(specs)} capability specs via {model_used}")

    source_kind = (s.get("plan") or {}).get("source_kind", "firestore")
    sdk_hint = (s.get("plan") or {}).get("sdk") or "firebase_admin"

    results = []
    for spec in specs:
        tool_id = f"gen_{spec['id']}"[:40]
        output_schema = {"type": "object",
                         "properties": {k: {"description": v} for k, v in
                                        {**spec.get("output_fields", {}), "found": "whether a record matched"}.items()}}
        report = toolgen.generate_tool(
            tool_id=tool_id,
            capability_description=spec["description"],
            input_schema=spec.get("input_schema", {"type": "object", "properties": {}}),
            system_context=_tool_system_context(source_kind, spec, s["structure"], output_schema),
            sample_args=_sample_args(spec.get("input_schema", {})),
            credential_scope=s["credential_scope"],
            sdk_hint=sdk_hint,
        )
        if report.get("ok"):
            with get_conn() as conn:
                conn.execute("UPDATE tools SET output_schema = ? WHERE id = ?",
                             (json.dumps(output_schema), tool_id))
                row = conn.execute(
                    "SELECT allowed_tools FROM credential_bindings WHERE credential_scope = ?",
                    (s["credential_scope"],)).fetchone()
                allowed = json.loads(row["allowed_tools"]) if row else []
                if tool_id not in allowed:
                    allowed.append(tool_id)
                conn.execute("UPDATE credential_bindings SET allowed_tools = ? WHERE credential_scope = ?",
                             (json.dumps(allowed), s["credential_scope"]))
            verify = _sandbox_verify(tool_id, _sample_args(spec.get("input_schema", {})))
            report["sandbox_verify"] = verify
            _register_capability(spec, tool_id)
        results.append({"tool_id": tool_id, "ok": report.get("ok"),
                        "steps": report.get("steps"), "sandbox_verify": report.get("sandbox_verify")})
        s["generated"].append(tool_id)

    audit.log(session_id, "onboarding_generate", model_used=model_used, remote_model_used=True,
              detail={"tools": [r["tool_id"] for r in results]})
    return {"generated": results,
            "note": "tools are registered UNAPPROVED — review and approve them in the admin panel"}


def finalize(session_id: str) -> dict:
    """Step 5: context wipe. Transcript, plan, and structure dump are destroyed;
    what remains is only what ideal_arhc.md says should remain — metadata,
    tools, policies, vault."""
    s = _sessions.pop(session_id, None)
    if not s:
        return {"wiped": False, "reason": "no such session"}
    generated = s["generated"]
    audit.log(session_id, "onboarding_wipe",
              detail={"wiped": ["transcript", "plan", "structure"], "tools_kept": generated})
    return {"wiped": True, "tools_awaiting_approval": generated}


def _ensure_probe_tool(probe_tool: dict, credential_scope: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tools
               (id, type, entrypoint, file_path, input_schema, output_schema,
                credential_scope, generated_by, human_approved, status)
               VALUES (?, 'read_connector', ?, ?, ?, ?, ?, 'human', 1, 'active')""",
            (probe_tool["id"], probe_tool["entrypoint"], probe_tool["file_path"],
             json.dumps({"type": "object", "properties": {
                "sample_per_collection": {"type": "integer"}}}),
             json.dumps({"type": "object", "properties": {
                 "connected": {}, "collections": {}}}),
             credential_scope),
        )


def _sandbox_verify(tool_id: str, sample_args: dict) -> dict:
    try:
        out = execute(get_tool(tool_id), sample_args, sandbox=True)
        return {"ok": True, "output_keys": sorted(k for k in out if not k.startswith("_"))}
    except ToolExecutionError as e:
        return {"ok": False, "error": e.public_message, "internal": e.internal_detail[:300]}


def _register_capability(spec: dict, tool_id: str) -> None:
    rules = [{"role": r, "decision": "allow"} for r in spec.get("allowed_roles", [])]
    policy_id = f"policy_{spec['id']}"[:40]
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO domains (id, name, description)
               VALUES ('onboarded', 'Onboarded sources', 'Capabilities created via source onboarding')""",
        )
        conn.execute(
            "INSERT OR REPLACE INTO policies (id, action, rules, default_decision) VALUES (?,?,?,?)",
            (policy_id, spec["id"], json.dumps(rules), "deny"),
        )
        conn.execute(
            """INSERT OR REPLACE INTO capabilities
               (id, domain_id, intent, description, example_utterances, required_entities,
                tool_id, policy_id, risk_level, requires_approval, remote_model_allowed, status)
               VALUES (?,?,?,?,?,?,?,?,1,0,0,'active')""",
            (spec["id"], "onboarded", spec["id"], spec["description"],
             json.dumps(spec.get("example_utterances", [])),
             json.dumps(list((spec.get("input_schema", {}).get("properties") or {}).keys())),
             tool_id, policy_id),
        )


def _sample_args(input_schema: dict) -> dict:
    out = {}
    for name, prop in (input_schema.get("properties") or {}).items():
        out[name] = 1 if prop.get("type") == "integer" else "test"
    return out


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(m.group(0) if m else text)
    except json.JSONDecodeError:
        return {}


def _session(session_id: str) -> dict:
    if session_id not in _sessions:
        raise ValueError(f"no onboarding session {session_id}")
    return _sessions[session_id]
