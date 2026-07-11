"""Tests for the ideal_arhc.md security guarantees: airgap AST gate + 0/1 output
contract. These are the claims that must never silently regress."""

import json

import pytest

from pandabear import airgap
from pandabear.db import get_conn, init_db
from pandabear.executor import _enforce_output_contract


@pytest.fixture(autouse=True)
def seeded():
    init_db()
    import scripts.seed_demo as seed
    seed.main()


@pytest.mark.parametrize("src", [
    "import socket",
    "import requests",
    "import urllib.request",
    "import subprocess",
    "import os\nos.system('x')",
    "from os import popen",
    "eval('1')",
    "exec('x=1')",
    "open('/etc/passwd')",
    "__import__('os')",
])
def test_airgap_rejects_egress_and_exec(src):
    assert airgap.validate(src).ok is False


@pytest.mark.parametrize("src", [
    "import json\nimport sys",
    "import os\nx = os.environ.get('PANDABEAR_CREDENTIAL')",
    "from os import environ\nx = environ['PANDABEAR_CREDENTIAL']",
    "import firebase_admin\nfrom firebase_admin import credentials, firestore",
])
def test_airgap_allows_legitimate_tool_code(src):
    assert airgap.validate(src).ok is True


def test_generated_tools_pass_airgap():
    from pathlib import Path
    for name in ("fb_check_stock.py", "fb_check_invoice.py"):
        p = Path("tools/generated") / name
        if p.is_file():
            assert airgap.validate(p.read_text()).ok is True


def test_output_contract_drops_undeclared_fields():
    tool = {
        "output_schema": json.dumps({
            "type": "object",
            "properties": {"status": {}, "found": {}},
        })
    }
    raw = {"status": "STOCK_LOW", "found": True,
           "secret_customer_email": "vip@bigco.com", "raw_row": {"ssn": "..."}}
    out = _enforce_output_contract(tool, raw)
    assert "secret_customer_email" not in out
    assert "raw_row" not in out
    assert out["status"] == "STOCK_LOW"
    assert set(out["_contract_dropped_fields"]) == {"secret_customer_email", "raw_row"}


def test_output_contract_noop_without_schema():
    out = _enforce_output_contract({"output_schema": "{}"}, {"anything": 1})
    assert out == {"anything": 1}
