import sys
import json
import os

def main():
    try:
        args = json.loads(sys.argv[1])
        product = args.get("product")
        branch = args.get("branch")
        if not isinstance(product, str) or not isinstance(branch, int):
            print(json.dumps({"found": False}))
            return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except Exception as e:
        sys.stderr.write("Failed to import firebase_admin SDK\n")
        sys.exit(1)

    try:
        cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
        if not cred_json:
            sys.stderr.write("Missing PANDABEAR_CREDENTIAL\n")
            sys.exit(1)
        cred = credentials.Certificate(json.loads(cred_json))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        sys.stderr.write("Failed to initialize Firestore\n")
        sys.exit(1)

    try:
        q = db.collection("inventory").where("product", "==", product).where("branch", "==", branch).limit(1)
        docs = list(q.stream())
        if not docs:
            print(json.dumps({"found": False}))
            return 0
        doc = docs[0]
        data = doc.to_dict()
        result = {
            "stock": data.get("stock"),
            "threshold": data.get("threshold"),
            "unit": data.get("unit"),
            "found": True
        }
        print(json.dumps(result))
        return 0
    except Exception as e:
        sys.stderr.write("Error querying Firestore\n")
        sys.exit(1)

if __name__ == "__main__":
    main()