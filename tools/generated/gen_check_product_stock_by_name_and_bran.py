import sys
import json
import os

def main():
    import firebase_admin
    from firebase_admin import credentials, firestore

    try:
        args = json.loads(sys.argv[1])
        product = args.get("product")
        branch = args.get("branch")
        if not isinstance(product, str) or not isinstance(branch, int):
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
    except Exception as e:
        sys.stderr.write("Failed to initialize Firestore\n")
        sys.exit(1)

    try:
        docs = db.collection("inventory").where("product", "==", product).where("branch", "==", branch).limit(1).stream()
        doc = next(docs, None)
        if not doc or not doc.exists:
            print(json.dumps({"found": False}), flush=True)
            sys.exit(0)
        data = doc.to_dict()
        output = {
            "product": data.get("product"),
            "branch": data.get("branch"),
            "stock": data.get("stock"),
            "unit": data.get("unit"),
            "found": True
        }
        print(json.dumps(output), flush=True)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write("Error querying Firestore\n")
        sys.exit(1)

if __name__ == "__main__":
    main()