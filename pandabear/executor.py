"""Deterministic tool executor. Runs an approved tool in a subprocess with the
credential resolved from the vault injected into that subprocess's env ONLY.
The parent process's graph state — everything any model can see — never holds
the credential. Tools read args as JSON from argv[1] and print JSON to stdout.
"""

import json
import os
import subprocess
import sys
import time

from .config import settings
from .vault import VaultError, get_scoped


class ToolExecutionError(Exception):
    def __init__(self, public_message: str, internal_detail: str = ""):
        super().__init__(public_message)
        self.public_message = public_message
        self.internal_detail = internal_detail  # goes to audit log, never to the user/model


def execute(tool: dict, args: dict, *, sandbox: bool = False) -> dict:
    """Run one tool row (from registry.get_tool) with validated business args.
    Returns the tool's parsed JSON output. Raises ToolExecutionError on any failure.

    sandbox=True is the onboarding verification path: it may run tools still in
    'testing' (pre-approval) — code that has already passed the airgap AST gate —
    but everything else (vault scoping, subprocess isolation, output contract)
    applies identically. The live graph never sets this flag."""
    if not sandbox and (tool["status"] != "active" or not tool["human_approved"]):
        raise ToolExecutionError(
            "This action is not yet enabled.",
            f"tool {tool['id']} status={tool['status']} approved={tool['human_approved']}",
        )

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PANDABEAR_TOOL_ID": tool["id"],
    }
    if tool.get("credential_scope"):
        try:
            cred = get_scoped(tool["credential_scope"], tool["id"])
        except VaultError as e:
            # fail closed — never run a credentialed tool without its credential
            raise ToolExecutionError("Credential resolution failed; action aborted.", str(e)) from e
        env["PANDABEAR_CREDENTIAL"] = cred if isinstance(cred, str) else json.dumps(cred)

    tool_path = settings.tools_dir.parent / tool["file_path"]
    if not tool_path.is_file():
        raise ToolExecutionError("Tool implementation missing.", f"no file at {tool_path}")

    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(tool_path), json.dumps(args)],
            capture_output=True,
            text=True,
            timeout=tool.get("timeout_seconds") or settings.tool_timeout_seconds,
            env=env,
            cwd=str(settings.tools_dir.parent),
        )
    except subprocess.TimeoutExpired as e:
        raise ToolExecutionError(
            "The action timed out.", f"tool {tool['id']} exceeded {settings.tool_timeout_seconds}s"
        ) from e

    if proc.returncode != 0:
        raise ToolExecutionError(
            "The action failed while running.",
            f"tool {tool['id']} rc={proc.returncode} stderr={proc.stderr[-2000:]}",
        )

    try:
        output = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ToolExecutionError(
            "The action returned an unreadable result.",
            f"tool {tool['id']} non-JSON stdout: {proc.stdout[:500]}",
        ) from e
    if not isinstance(output, dict):
        raise ToolExecutionError(
            "The action returned an unreadable result.",
            f"tool {tool['id']} returned {type(output).__name__}, expected object",
        )

    output = _enforce_output_contract(tool, output)
    output["_latency_ms"] = int((time.monotonic() - start) * 1000)
    return output


def _enforce_output_contract(tool: dict, output: dict) -> dict:
    """The runtime half of the '0/1 rule': whatever a tool prints, only fields
    declared in its output_schema pass through to the model layer. A tool (or a
    compromised regeneration of one) cannot exfiltrate raw records it never
    declared. No declared schema = output passes as-is (schema is opt-in but
    every generated tool gets one)."""
    schema = tool.get("output_schema") or {}
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except json.JSONDecodeError:
            schema = {}
    declared = set((schema.get("properties") or {}).keys())
    if not declared:
        return output
    dropped = [k for k in output if k not in declared]
    if dropped:
        for k in dropped:
            output.pop(k)
        output["_contract_dropped_fields"] = dropped
    return output
