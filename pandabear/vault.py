"""Credential vault — Fernet-encrypted file store with a vault_ref interface.

The whole point of this module is the boundary it draws: credentials go in once
(seed_secret), and after that the ONLY way out is get_scoped(), which checks the
requesting tool against credential_bindings.allowed_tools. Nothing in the agent
or model path imports this module — only the tool executor does. Swapping this
for real HashiCorp Vault later means reimplementing these four functions against
its HTTP API; every caller keeps the same vault_ref strings.
"""

import json
import os
import stat

from cryptography.fernet import Fernet

from .config import settings
from .db import get_conn, loads_field


class VaultError(Exception):
    """Fail closed: any problem resolving a credential must abort the tool run."""


def _fernet() -> Fernet:
    if settings.vault_key_path.exists():
        key = settings.vault_key_path.read_bytes()
    else:
        key = Fernet.generate_key()
        settings.vault_key_path.write_bytes(key)
        os.chmod(settings.vault_key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    return Fernet(key)


def _load_store() -> dict:
    if not settings.vault_path.exists():
        return {}
    return json.loads(_fernet().decrypt(settings.vault_path.read_bytes()))


def _save_store(store: dict) -> None:
    settings.vault_path.write_bytes(_fernet().encrypt(json.dumps(store).encode()))
    os.chmod(settings.vault_path, stat.S_IRUSR | stat.S_IWUSR)


def seed_secret(vault_ref: str, secret: dict | str) -> None:
    """Store a secret under a vault_ref like 'vault://firebase/admin'."""
    if not vault_ref.startswith("vault://"):
        raise VaultError(f"invalid vault_ref: {vault_ref}")
    store = _load_store()
    store[vault_ref] = secret
    _save_store(store)


def get_scoped(credential_scope: str, tool_id: str) -> dict | str:
    """Resolve a credential for a specific tool. Raises VaultError unless a
    binding exists for this scope AND lists this tool as allowed."""
    with get_conn() as conn:
        binding = conn.execute(
            "SELECT * FROM credential_bindings WHERE credential_scope = ?",
            (credential_scope,),
        ).fetchone()
    if not binding:
        raise VaultError(f"no binding for scope '{credential_scope}'")
    loads_field(binding, "allowed_tools")
    if tool_id not in binding["allowed_tools"]:
        raise VaultError(f"tool '{tool_id}' not allowed for scope '{credential_scope}'")

    store = _load_store()
    if binding["vault_ref"] not in store:
        raise VaultError(f"vault_ref '{binding['vault_ref']}' not found in vault")
    return store[binding["vault_ref"]]


def list_refs() -> list[str]:
    """Names only — never values. Safe to show in admin/demo output."""
    return sorted(_load_store().keys())
