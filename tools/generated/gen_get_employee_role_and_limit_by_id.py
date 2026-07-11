import sys
import json
import os

def main():
    import firebase_admin
    from firebase_admin import credentials, firestore

    # Parse input
    try:
        args = json.loads(sys.argv[1])
        employee_id = args.get("employee_id")
        if not isinstance(employee_id, str) or not employee_id:
            print(json.dumps({"found": False}))
            return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

    # Get credentials from env
    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        sys.stderr.write("Missing PANDABEAR_CREDENTIAL\n")
        sys.exit(1)
    try:
        cred = credentials.Certificate(json.loads(cred_json))
    except Exception:
        sys.stderr.write("Malformed credential\n")
        sys.exit(1)

    # Initialize app if not already
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    try:
        doc_ref = db.collection("employees").document(employee_id)
        doc = doc_ref.get()
        if not doc.exists:
            print(json.dumps({"found": False}))
            return 0
        data = doc.to_dict()
        role = data.get("role")
        approval_limit = data.get("approval_limit")
        if not isinstance(role, str) or not isinstance(approval_limit, int):
            print(json.dumps({"found": False}))
            return 0
        print(json.dumps({
            "role": role,
            "approval_limit": approval_limit,
            "found": True
        }))
        return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

if __name__ == "__main__":
    main()