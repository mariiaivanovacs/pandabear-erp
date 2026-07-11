"""Platform probe tool (human-authored, ships with PandaBear — not generated).

Discovers STRUCTURE ONLY from a Firestore source: collection names and
field->type maps sampled from a few docs. Never returns field values — this is
what lets the onboarding model design tools without ever seeing company data.

Contract: argv[1] JSON args {"max_collections": int?, "sample_per_collection": int?}
stdout: {"connected": bool, "collections": {name: {field: type_name}}}
"""

import json
import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore


def main() -> None:
    args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    max_collections = int(args.get("max_collections", 20))
    sample = int(args.get("sample_per_collection", 3))

    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        print("Missing PANDABEAR_CREDENTIAL", file=sys.stderr)
        sys.exit(1)

    try:
        cred = credentials.Certificate(json.loads(cred_json))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception:
        print(json.dumps({"connected": False, "collections": {}}))
        return

    collections: dict = {}
    try:
        for col in list(db.collections())[:max_collections]:
            fields: dict[str, str] = {}
            for doc in col.limit(sample).stream():
                for k, v in (doc.to_dict() or {}).items():
                    fields[k] = type(v).__name__  # type names only, never values
            collections[col.id] = fields
    except Exception:
        print(json.dumps({"connected": False, "collections": {}}))
        return

    print(json.dumps({"connected": True, "collections": collections}))


if __name__ == "__main__":
    main()
