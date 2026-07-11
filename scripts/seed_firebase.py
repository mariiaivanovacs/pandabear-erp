"""Seed the (empty) studybuddy-31043 Firestore with a realistic demo-company
dataset so tools query real, live remote data. Idempotent — fixed doc ids.

Run: uv run python scripts/seed_firebase.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

from pandabear.vault import _load_store  # noqa: E402

INVENTORY = {
    "oatmilk_b5": {"product": "oat milk", "branch": 5, "stock": 4, "threshold": 20,
                   "unit": "carton", "supplier": "SupplierX", "supplier_lead_days": 3,
                   "daily_usage": 15, "unit_cost": 2.10},
    "oatmilk_b2": {"product": "oat milk", "branch": 2, "stock": 31, "threshold": 20,
                   "unit": "carton", "supplier": "SupplierX", "supplier_lead_days": 3,
                   "daily_usage": 9, "unit_cost": 2.10},
    "espresso_b5": {"product": "espresso beans", "branch": 5, "stock": 42, "threshold": 25,
                    "unit": "kg", "supplier": "BeanCo", "supplier_lead_days": 2,
                    "daily_usage": 6, "unit_cost": 14.50},
    "cups12_b5": {"product": "12oz cups", "branch": 5, "stock": 180, "threshold": 400,
                  "unit": "piece", "supplier": "PackPro", "supplier_lead_days": 5,
                  "daily_usage": 210, "unit_cost": 0.08},
    "espresso_b2": {"product": "espresso beans", "branch": 2, "stock": 11, "threshold": 25,
                    "unit": "kg", "supplier": "BeanCo", "supplier_lead_days": 2,
                    "daily_usage": 7, "unit_cost": 14.50},
}

INVOICES = {
    "INV-1001": {"vendor": "SupplierX", "amount": 840.00, "currency": "USD",
                 "status": "pending_approval", "po_number": "PO-771", "po_status": "approved",
                 "issued": "2026-07-01", "due": "2026-07-15", "branch": 5},
    "INV-1002": {"vendor": "BeanCo", "amount": 4350.00, "currency": "USD",
                 "status": "pending_approval", "po_number": None, "po_status": "missing",
                 "issued": "2026-07-03", "due": "2026-07-17", "branch": 2},
    "INV-1003": {"vendor": "PackPro", "amount": 96.00, "currency": "USD",
                 "status": "paid", "po_number": "PO-765", "po_status": "approved",
                 "issued": "2026-06-20", "due": "2026-07-04", "branch": 5},
    "INV-1004": {"vendor": "CleanServ", "amount": 12500.00, "currency": "USD",
                 "status": "pending_approval", "po_number": "PO-780", "po_status": "approved",
                 "issued": "2026-07-08", "due": "2026-07-22", "branch": 1},
}

EMPLOYEES = {
    "emp_014": {"name": "Alex Ng", "role": "branch_manager", "branch": 5,
                "approval_limit": 1000, "email": "alex@demo.co"},
    "emp_007": {"name": "Dana Cruz", "role": "ops_manager", "branch": None,
                "approval_limit": 10000, "email": "dana@demo.co"},
    "emp_021": {"name": "Sam Lee", "role": "barista", "branch": 5,
                "approval_limit": 0, "email": "sam@demo.co"},
}


def main() -> None:
    sa = _load_store()["vault://firebase/admin"]
    cred = credentials.Certificate(sa)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    for col, docs in [("inventory", INVENTORY), ("invoices", INVOICES), ("employees", EMPLOYEES)]:
        for doc_id, data in docs.items():
            db.collection(col).document(doc_id).set(data)
        print(f"seeded {col}: {len(docs)} docs")


if __name__ == "__main__":
    main()
