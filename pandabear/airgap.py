"""AST 'airgap' validator — the deterministic code check from ideal_arhc.md.

Every generated tool is parsed (never executed) and its AST scanned before it
can be registered. Anything not on the allowlist, or any egress/exec-shaped
call, rejects the tool. Deterministic by design: a validator the model could
argue with would be no validator at all.

Allowed: json/sys stdlib basics + the one SDK the tool declares. `os` is NOT
allowed generally — only reading os.environ (that's how the executor hands the
tool its credential). No sockets, no subprocess, no eval/exec, no file writes.
"""

import ast
from dataclasses import dataclass, field

ALLOWED_MODULES = {
    "json", "sys", "math", "datetime", "decimal", "re", "typing",
    "firebase_admin", "google",  # google.cloud.firestore comes with firebase_admin
}
# os is special-cased: `os.environ.get(...)` / `os.environ[...]` only
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "input"}
FORBIDDEN_OS_ATTRS_EXAMPLES = "os.system / os.popen / os.remove / os.fork ..."


@dataclass
class AirgapReport:
    ok: bool
    violations: list[str] = field(default_factory=list)


def validate(source: str, extra_allowed_modules: set[str] | None = None) -> AirgapReport:
    allowed = ALLOWED_MODULES | (extra_allowed_modules or set())
    violations: list[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return AirgapReport(False, [f"syntax error: {e}"])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "os":
                    continue  # usage checked below
                if root not in allowed:
                    violations.append(f"line {node.lineno}: forbidden import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root == "os":
                # `from os import environ` is fine; anything else from os is not
                for alias in node.names:
                    if alias.name != "environ":
                        violations.append(f"line {node.lineno}: forbidden 'from os import {alias.name}'")
            elif root not in allowed:
                violations.append(f"line {node.lineno}: forbidden import 'from {node.module}'")
        elif isinstance(node, ast.Attribute):
            # os.<anything other than environ> — os.environ.get() parses as
            # Attribute(Attribute(Name('os'),'environ'),'get'), so checking the
            # attribute whose value is the bare name 'os' covers every direct use
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr != "environ":
                violations.append(
                    f"line {node.lineno}: forbidden os.{node.attr} (only os.environ is allowed; "
                    f"not {FORBIDDEN_OS_ATTRS_EXAMPLES})"
                )
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                violations.append(f"line {node.lineno}: forbidden call '{fn.id}()'")

    return AirgapReport(not violations, violations)
