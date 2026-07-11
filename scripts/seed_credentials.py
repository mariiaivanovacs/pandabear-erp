"""One-time credential seeding into the vault. After this runs, the source
values can be deleted from .env / disk — the encrypted vault is the only copy
the system uses, and only the tool executor can read it back out.

Run: uv run python scripts/seed_credentials.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pandabear.config import settings  # noqa: E402
from pandabear.db import get_conn, init_db  # noqa: E402
from pandabear.vault import list_refs, seed_secret  # noqa: E402


def main() -> None:
    init_db()
    seeded = []

    if settings.firebase_service_account_path:
        sa_path = Path(settings.firebase_service_account_path).expanduser()
        if sa_path.is_file():
            seed_secret("vault://firebase/admin", json.loads(sa_path.read_text()))
            seeded.append("vault://firebase/admin")
        else:
            print(f"! firebase service account not found at {sa_path}")

    if settings.telegram_bot_token:
        seed_secret("vault://telegram/bot", settings.telegram_bot_token)
        seeded.append("vault://telegram/bot")

    # bind the firebase credential to firebase tools (extend allowed_tools as
    # new tools are approved)
    if "vault://firebase/admin" in seeded:
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO credential_bindings
                   (id, credential_scope, vault_ref, allowed_tools, model_visible)
                   VALUES (?,?,?,?,0)""",
                ("firebase_admin_binding", "firebase.admin", "vault://firebase/admin",
                 json.dumps([])),
            )

    print(f"seeded: {seeded or 'nothing (no credentials configured in .env)'}")
    print(f"vault now holds: {list_refs()}")
    if seeded:
        print("\nYou can now REMOVE the raw values from .env / delete the JSON file —")
        print("the encrypted vault is the only copy the system needs.")


if __name__ == "__main__":
    main()
