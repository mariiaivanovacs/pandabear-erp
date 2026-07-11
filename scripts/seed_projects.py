"""Seed a 'projects' collection into the (real) Firestore demo dataset — client
work with deadlines and confidential specifications, so the permission story
plays out on business data judges immediately recognize, not just kg of beans.
Idempotent — fixed doc ids.

Run: uv run python scripts/seed_projects.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

from pandabear.vault import _load_store  # noqa: E402

PROJECTS = {
    "proj_northwind_crm": {
        "name": "Northwind CRM Integration",
        "client": "Northwind Trading Co",
        "deadline": "2026-08-15",
        "status": "in_progress",
        "priority": "high",
        "specifications": (
            "Full CRM sync via REST API, SSO via Okta, GDPR-compliant data "
            "retention (90 days max), weekly automated reporting to client "
            "dashboard, must support 500 concurrent users at peak."
        ),
    },
    "proj_bluewave_migration": {
        "name": "Ecommerce Platform Migration",
        "client": "BlueWave Retail",
        "deadline": "2026-07-30",
        "status": "review",
        "priority": "critical",
        "specifications": (
            "Migrate from Shopify to headless commerce (Next.js + Medusa), "
            "preserve existing SEO rankings, zero-downtime cutover window, "
            "PCI-DSS compliant payment handling, multi-currency (USD/EUR/GBP)."
        ),
    },
    "proj_internal_dashboard": {
        "name": "Internal Analytics Dashboard",
        "client": "Internal - Ops Team",
        "deadline": "2026-09-01",
        "status": "planning",
        "priority": "medium",
        "specifications": (
            "Real-time KPI dashboard for branch managers, role-based data "
            "visibility, exportable to PDF/Excel, mobile-responsive layout."
        ),
    },
    "proj_horizon_onboarding": {
        "name": "Horizon Logistics Vendor Onboarding",
        "client": "Horizon Logistics",
        "deadline": "2026-07-22",
        "status": "in_progress",
        "priority": "high",
        "specifications": (
            "Automated vendor KYC verification, EDI 850/856 document exchange, "
            "SLA breach alerting within 15 minutes, audit trail retained 7 years "
            "per client's regulatory requirement."
        ),
    },
}


def main() -> None:
    sa = _load_store()["vault://firebase/admin"]
    cred = credentials.Certificate(sa)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    for doc_id, data in PROJECTS.items():
        db.collection("projects").document(doc_id).set(data)
    print(f"seeded projects: {len(PROJECTS)} docs")


if __name__ == "__main__":
    main()
