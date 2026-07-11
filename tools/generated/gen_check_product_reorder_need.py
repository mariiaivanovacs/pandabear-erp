import sys
import json
import os

def main():
    import firebase_admin
    from firebase_admin import credentials, firestore

    try:
        args = json.loads(sys.argv[1])
        branch = args.get("branch")
        product = args.get("product")
        if not isinstance(branch, int) or not isinstance(product, str):
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
        sys.stderr.write("Could not initialize Firestore\n")
        sys.exit(1)

    try:
        q = db.collection("inventory").where("branch", "==", branch).where("product", "==", product).limit(1)
        docs = list(q.stream())
        if not docs:
            print(json.dumps({"found": False}), flush=True)
            sys.exit(0)
        doc = docs[0]
        data = doc.to_dict()
        stock = data.get("stock")
        threshold = data.get("threshold")
        if not isinstance(stock, int) or not isinstance(threshold, int):
            print(json.dumps({"found": False}), flush=True)
            sys.exit(0)
        needs_reorder = stock <= threshold
        out = {
            "branch": branch,
            "product": product,
            "stock": stock,
            "threshold": threshold,
            "needs_reorder": needs_reorder,
            "found": True
        }
        print(json.dumps(out), flush=True)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write("Error querying Firestore\n")
        sys.exit(1)

if __name__ == "__main__":
    main()