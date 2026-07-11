import sys
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def error_exit(msg):
    sys.stderr.write(msg.strip() + "\n")
    sys.exit(1)

def main():
    try:
        args = json.loads(sys.argv[1])
        invoice_id = args.get("invoice_id")
        if not isinstance(invoice_id, str) or not invoice_id.strip():
            print(json.dumps({"found": False}))
            return
        invoice_id = invoice_id.strip().upper()
    except Exception:
        print(json.dumps({"found": False}))
        return

    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        error_exit("Missing PANDABEAR_CREDENTIAL environment variable.")
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {"projectId": "studybuddy-31043"})
        db = firestore.client()
    except Exception:
        error_exit("Failed to initialize Firestore client.")

    try:
        doc = db.collection("invoices").document(invoice_id).get()
        if not doc.exists:
            print(json.dumps({"found": False}))
            return
        data = doc.to_dict()
        result = {
            "found": True,
            "invoice_id": invoice_id,
            "vendor": data.get("vendor"),
            "amount": data.get("amount"),
            "currency": data.get("currency"),
            "status": data.get("status"),
            "po_number": data.get("po_number"),
            "po_status": data.get("po_status"),
            "issued": data.get("issued"),
            "due": data.get("due"),
            "branch": data.get("branch"),
        }
        print(json.dumps(result))
    except Exception:
        print(json.dumps({"found": False}))

if __name__ == "__main__":
    main()