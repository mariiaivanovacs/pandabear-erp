"""AI tool-generation pipeline: the system writes its own deterministic tools.

Given a capability description + the external system's real schema, a model
(cloud by default — this is design-time work, credits fund it) generates a
candidate tool file. The candidate is:
  1. syntax-checked (compile()),
  2. contract-checked (runs under the executor against sample args),
  3. registered with status='testing', human_approved=0.

Nothing the model writes can execute in the live graph until a human flips
human_approved — approve_tool() is that flip, and it is the only path to
status='active'.
"""

import json
import re

from . import airgap, models
from .config import settings
from .db import get_conn

GEN_SYSTEM = """You write deterministic Python tools for an enterprise assistant.

Hard requirements for every tool file:
- Reads its arguments as JSON from sys.argv[1]; prints a single JSON object to
  stdout; exits 0 on success, non-zero with a stderr message on failure.
- If the tool needs external-system access, the credential arrives ONLY via the
  PANDABEAR_CREDENTIAL environment variable (a JSON string for service accounts).
  Never hardcode, log, or print any part of it.
- Deterministic: no randomness, no LLM calls, no network beyond the one target
  system, no shell commands, no file writes.
- From the os module, ONLY os.environ is allowed — an AST validator rejects any
  other os attribute, and any import of subprocess/socket/requests/urllib, and
  any eval/exec/open/input call.
- Output ONLY the fields in the declared output contract — never dump whole
  records; undeclared fields are stripped by the runtime anyway.
- Handle missing/malformed inputs by returning {"found": false, ...} or a clear
  error on stderr — never a stack trace on stdout.
- Keep it under ~80 lines. Standard library plus the named SDK only.

Return ONLY the Python source, no markdown fences, no commentary."""


def generate_tool(
    tool_id: str,
    capability_description: str,
    input_schema: dict,
    system_context: str,
    sample_args: dict,
    *,
    credential_scope: str | None = None,
    sdk_hint: str = "firebase_admin",
) -> dict:
    """Generate, verify, and register a candidate tool. Returns a report dict —
    including failures, so the caller (or the demo audience) sees exactly what
    the pipeline caught."""
    prompt = (
        f"Tool id: {tool_id}\n"
        f"Purpose: {capability_description}\n"
        f"Input JSON schema: {json.dumps(input_schema)}\n"
        f"Target system details:\n{system_context}\n"
        f"SDK to use: {sdk_hint}\n"
    )
    report: dict = {"tool_id": tool_id, "steps": []}

    # generate → airgap-validate; violations are fed back for one regeneration,
    # per ideal_arhc.md ("the tool is rejected and regenerated")
    messages = [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": prompt}]
    source, model_used = "", ""
    for attempt in range(2):
        msg, model_used, _ = models.chat(messages, force_cloud=True)
        source = _strip_fences(msg.content or "")
        report["steps"].append({"step": f"generate_attempt_{attempt + 1}", "ok": bool(source)})
        if not source:
            report["ok"] = False
            return report

        gate = airgap.validate(source)
        report["steps"].append(
            {"step": f"airgap_check_attempt_{attempt + 1}", "ok": gate.ok, "violations": gate.violations}
        )
        if gate.ok:
            break
        if attempt == 0:
            messages.append({"role": "assistant", "content": source})
            messages.append({"role": "user", "content":
                "REJECTED by the security validator. Violations:\n"
                + "\n".join(gate.violations)
                + "\nRegenerate the full tool without these patterns. "
                  "Remember: only os.environ may be used from os; no sockets, "
                  "subprocess, eval, exec, or file access."})
        else:
            report["ok"] = False
            report["rejected_by"] = "airgap_validator"
            return report

    report["generated_by"] = model_used

    rel_path = f"tools/generated/{tool_id}.py"
    path = settings.tools_dir.parent / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "__init__.py").touch()
    path.write_text(source)

    contract_ok, contract_detail = _contract_check(rel_path, sample_args)
    report["steps"].append({"step": "contract_check", "ok": contract_ok, "detail": contract_detail})

    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tools
               (id, type, entrypoint, file_path, input_schema, credential_scope,
                generated_by, human_approved, status)
               VALUES (?,?,?,?,?,?,?,0,'testing')""",
            (tool_id, "read_connector", f"tools.generated.{tool_id}.run", rel_path,
             json.dumps(input_schema), credential_scope, model_used),
        )

    report["ok"] = contract_ok
    report["file_path"] = rel_path
    report["awaiting_human_approval"] = True
    return report


def approve_tool(tool_id: str, approved_by: str) -> None:
    """The human gate. The only way a generated tool becomes executable."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE tools SET human_approved = 1, status = 'active' WHERE id = ?",
            (tool_id,),
        )


def _contract_check(rel_path: str, sample_args: dict) -> tuple[bool, str]:
    """Run the candidate the same way the executor will (but without approval, via
    a direct subprocess) and verify it honors the stdout-JSON contract."""
    import subprocess
    import sys

    try:
        proc = subprocess.run(
            [sys.executable, str(settings.tools_dir.parent / rel_path), json.dumps(sample_args)],
            capture_output=True, text=True, timeout=settings.tool_timeout_seconds,
            cwd=str(settings.tools_dir.parent),
            env={"PATH": "", "PANDABEAR_TOOL_ID": "contract_check"},
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    if proc.returncode != 0:
        # a clean stderr failure on missing credentials is acceptable at this
        # stage — the tool can't reach its system yet; a stack trace is not
        clean_fail = bool(proc.stderr.strip()) and "Traceback" not in proc.stderr
        return clean_fail, f"rc={proc.returncode} stderr={proc.stderr[:300]}"
    try:
        json.loads(proc.stdout)
        return True, "stdout is valid JSON"
    except json.JSONDecodeError:
        return False, f"non-JSON stdout: {proc.stdout[:200]}"


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()
