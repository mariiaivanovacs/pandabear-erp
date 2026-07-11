import sys
import json
import os
import psycopg2
from decimal import Decimal

def main():
    try:
        args = json.loads(sys.argv[1])
        order_id = args.get("order_id")
        if not isinstance(order_id, str) or not order_id:
            print(json.dumps({"found": False}))
            sys.exit(0)
    except Exception:
        print(json.dumps({"found": False}))
        sys.exit(0)

    try:
        cred = json.loads(os.environ.get("PANDABEAR_CREDENTIAL", "{}"))
        conn = psycopg2.connect(
            host=cred["host"],
            port=cred["port"],
            database=cred["database"],
            user=cred["user"],
            password=cred["password"]
        )
    except Exception as e:
        sys.stderr.write("Database connection error\n")
        sys.exit(1)

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT order_id, status, total_amount FROM orders WHERE order_id = %s",
                    (order_id,)
                )
                row = cur.fetchone()
                if row:
                    order_id_val, status, total_amount = row
                    if isinstance(total_amount, Decimal):
                        total_amount = float(total_amount)
                    result = {
                        "order_id": order_id_val,
                        "status": status,
                        "total_amount": total_amount,
                        "found": True
                    }
                else:
                    result = {"found": False}
        print(json.dumps(result))
    except Exception as e:
        sys.stderr.write("Query error\n")
        sys.exit(1)
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()