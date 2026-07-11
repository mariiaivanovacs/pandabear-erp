import sys
import json
import os

def main():
    import firebase_admin
    from firebase_admin import credentials, firestore

    # Parse input
    try:
        args = json.loads(sys.argv[1])
        email = args.get("email", "").strip().lower()
        if not email:
            print(json.dumps({"found": False}))
            return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

    # Get credentials
    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        sys.stderr.write("Missing credentials\n")
        sys.exit(1)
    try:
        cred = credentials.Certificate(json.loads(cred_json))
    except Exception:
        sys.stderr.write("Invalid credentials\n")
        sys.exit(1)

    # Initialize app if not already
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    try:
        docs = db.collection("employees").where("email", "==", email).limit(1).stream()
        doc = next(docs, None)
        if not doc or not doc.exists:
            print(json.dumps({"found": False}))
            return 0
        data = doc.to_dict()
        output = {
            "name": data.get("name", ""),
            "role": data.get("role", ""),
            "approval_limit": data.get("approval_limit", 0),
            "branch": data.get("branch", 0),
            "found": True
        }
        print(json.dumps(output))
        return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

if __name__ == "__main__":
    main()