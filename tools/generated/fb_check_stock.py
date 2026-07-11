import sys
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def error_exit(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)

def main():
    # Parse input
    try:
        args = json.loads(sys.argv[1])
        product = args["product"].strip().lower()
        branch = int(args["branch"])
    except Exception:
        print(json.dumps({"found": False}))
        return

    # Get credentials
    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        error_exit("Missing PANDABEAR_CREDENTIAL")
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
    except Exception:
        error_exit("Malformed credential")

    # Initialize Firebase
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {"projectId": "studybuddy-31043"})
        db = firestore.client()
    except Exception:
        error_exit("Could not initialize Firestore")

    # Query Firestore
    try:
        q = db.collection("inventory").where("product", "==", product).where("branch", "==", branch).limit(1)
        docs = list(q.stream())
        if not docs:
            print(json.dumps({"found": False}))
            return
        doc = docs[0].to_dict()
    except Exception:
        error_exit("Firestore query failed")

    # Prepare output
    stock = doc.get("stock")
    threshold = doc.get("threshold")
    daily_usage = doc.get("daily_usage")
    supplier = doc.get("supplier")
    supplier_lead_days = doc.get("supplier_lead_days")
    reorder_needed = stock is not None and threshold is not None and stock <= threshold
    try:
        estimated_days = float(stock) / float(daily_usage) if stock is not None and daily_usage else None
        if estimated_days is not None:
            estimated_days = round(estimated_days, 2)
    except Exception:
        estimated_days = None

    out = {
        "found": True,
        "product": doc.get("product"),
        "branch": doc.get("branch"),
        "stock": stock,
        "threshold": threshold,
        "reorder_needed": reorder_needed,
        "estimated_days_of_stock_left": estimated_days,
        "supplier": supplier,
        "supplier_lead_days": supplier_lead_days
    }
    print(json.dumps(out))

if __name__ == "__main__":
    main()