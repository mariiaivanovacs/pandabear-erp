import sys
import json
import os

def main():
    try:
        args = json.loads(sys.argv[1])
        po_number = args.get("po_number")
        if not isinstance(po_number, str) or not po_number.strip():
            print(json.dumps({"found": False}))
            return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        sys.stderr.write("Missing credentials\n")
        sys.exit(1)

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except Exception:
        sys.stderr.write("firebase_admin not installed\n")
        sys.exit(1)

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(json.loads(cred_json))
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        invoices = db.collection('invoices').where('po_number', '==', po_number).limit(1).stream()
        invoice = next(invoices, None)
        if not invoice or not invoice.exists:
            print(json.dumps({"found": False}))
            return 0
        data = invoice.to_dict()
        output = {
            "status": data.get("status"),
            "amount": data.get("amount"),
            "vendor": data.get("vendor"),
            "due": data.get("due"),
            "currency": data.get("currency"),
            "found": True
        }
        print(json.dumps(output))
        return 0
    except Exception as e:
        sys.stderr.write("Error retrieving invoice\n")
        sys.exit(1)

if __name__ == "__main__":
    main()