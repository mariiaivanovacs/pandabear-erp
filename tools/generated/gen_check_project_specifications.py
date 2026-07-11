import sys
import json
import os

def main():
    import firebase_admin
    from firebase_admin import credentials, firestore

    try:
        args = json.loads(sys.argv[1])
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            print(json.dumps({"found": False}), flush=True)
            sys.exit(0)
    except Exception:
        print(json.dumps({"found": False}), flush=True)
        sys.exit(0)

    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        sys.stderr.write("Missing credentials\n")
        sys.exit(1)
    try:
        cred = credentials.Certificate(json.loads(cred_json))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception:
        sys.stderr.write("Failed to initialize Firestore\n")
        sys.exit(1)

    try:
        needle = query.strip().lower()
        match = None
        for doc in db.collection("projects").stream():
            data = doc.to_dict()
            if needle in (data.get("name") or "").lower() or needle in (data.get("client") or "").lower():
                match = data
                break
        if not match:
            print(json.dumps({"found": False}), flush=True)
            sys.exit(0)
        output = {
            "name": match.get("name"),
            "client": match.get("client"),
            "specifications": match.get("specifications"),
            "found": True,
        }
        print(json.dumps(output), flush=True)
        sys.exit(0)
    except Exception:
        sys.stderr.write("Error querying Firestore\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
