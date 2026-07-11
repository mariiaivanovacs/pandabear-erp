import sys
import json
import os

def main():
    import firebase_admin
    from firebase_admin import credentials, firestore

    # Parse input
    try:
        args = json.loads(sys.argv[1])
        identifier = args.get("employee_identifier", "").strip()
        if not identifier:
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

    # Query by email or name
    try:
        # Try email first
        query = db.collection('employees').where('email', '==', identifier).limit(1).stream()
        doc = next(query, None)
        if not doc:
            # Try name
            query = db.collection('employees').where('name', '==', identifier).limit(1).stream()
            doc = next(query, None)
        if not doc:
            print(json.dumps({"found": False}))
            return 0
        data = doc.to_dict()
        result = {
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "role": data.get("role", ""),
            "approval_limit": data.get("approval_limit", 0),
            "found": True
        }
        print(json.dumps(result))
        return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

if __name__ == "__main__":
    main()