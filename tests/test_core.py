"""Deterministic-layer tests: policy, vault scoping, executor contract, audit scrub.
These run with no model and no external system — the layers that must be exact."""

import json

import pytest

from pandabear import audit, policy, registry, vault
from pandabear.db import get_conn, init_db
from pandabear.executor import ToolExecutionError, execute


@pytest.fixture(autouse=True)
def seeded():
    init_db()
    import scripts.seed_demo as seed
    seed.main()


def test_policy_allows_branch_manager():
    r = policy.evaluate("inventory_read_policy", "branch_manager", {})
    assert r.decision == "allow"


def test_policy_denies_barista():
    r = policy.evaluate("inventory_read_policy", "barista", {})
    assert r.decision == "deny"


def test_policy_unknown_role_hits_default_deny():
    r = policy.evaluate("inventory_read_policy", "intern", {})
    assert r.decision == "deny"
    assert r.reason_code == "DEFAULT_DECISION"


def test_policy_missing_policy_fails_closed():
    assert policy.evaluate(None, "ops_manager", {}).decision == "deny"
    assert policy.evaluate("nonexistent", "ops_manager", {}).decision == "deny"


def test_limit_rule_forces_approval():
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO policies (id, action, rules, default_decision) VALUES (?,?,?,?)",
            ("spend_policy", "spend",
             json.dumps([{"role": "branch_manager", "decision": "allow", "limit": 500}]),
             "deny"),
        )
    assert policy.evaluate("spend_policy", "branch_manager", {"amount": 100}).decision == "allow"
    assert policy.evaluate("spend_policy", "branch_manager", {"amount": 900}).decision == "approval_required"


def test_vault_scoping_blocks_unbound_tool():
    vault.seed_secret("vault://test/secret", {"key": "value"})
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO credential_bindings (id, credential_scope, vault_ref, allowed_tools) VALUES (?,?,?,?)",
            ("b1", "test.scope", "vault://test/secret", json.dumps(["allowed_tool"])),
        )
    assert vault.get_scoped("test.scope", "allowed_tool") == {"key": "value"}
    with pytest.raises(vault.VaultError):
        vault.get_scoped("test.scope", "some_other_tool")
    with pytest.raises(vault.VaultError):
        vault.get_scoped("nonexistent.scope", "allowed_tool")


def test_executor_runs_approved_tool():
    tool = registry.get_tool("check_stock")
    out = execute(tool, {"product": "oat milk", "branch": "5"})
    assert out["reorder_needed"] is True
    assert out["stock"] == 4


def test_executor_rejects_unapproved_tool():
    tool = registry.get_tool("check_stock")
    tool = dict(tool, human_approved=0)
    with pytest.raises(ToolExecutionError):
        execute(tool, {"product": "oat milk", "branch": "5"})


def test_executor_edge_case_unknown_product():
    tool = registry.get_tool("check_stock")
    out = execute(tool, {"product": "unicorn tears", "branch": "9"})
    assert out["found"] is False


def test_audit_scrubs_credential_shaped_content():
    audit.log("req_test_scrub", "agent",
              detail={"oops": "-----BEGIN PRIVATE KEY-----\nabc"})
    rows = audit.trace("req_test_scrub")
    assert json.loads(rows[-1]["detail"]).get("scrubbed") is True


def test_registry_exposes_no_internals_to_model():
    tools = registry.as_openai_tools()
    surface = json.dumps(tools)
    assert "file_path" not in surface
    assert "credential_scope" not in surface
    assert "vault://" not in surface
