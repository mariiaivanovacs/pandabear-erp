import sys
import json
import os
import psycopg2

def main():
    try:
        args = json.loads(sys.argv[1])
        customer_name = args.get("customer_name")
        if not customer_name or not isinstance(customer_name, str):
            print(json.dumps({"found": False}))
            return 0
    except Exception:
        print(json.dumps({"found": False}))
        return 0

    try:
        cred = json.loads(os.environ["PANDABEAR_CREDENTIAL"])
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
        with conn.cursor() as cur:
            # Find customer_id by case-insensitive match on name
            cur.execute(
                """
                SELECT customer_id
                FROM customers
                WHERE LOWER(name) = LOWER(%s)
                LIMIT 1
                """,
                (customer_name.strip(),)
            )
            row = cur.fetchone()
            if not row:
                print(json.dumps({"found": False}))
                return 0
            customer_id = row[0]

            # Find latest support ticket for this customer_id
            cur.execute(
                """
                SELECT ticket_id, status, message, created_at
                FROM support_tickets
                WHERE customer_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (customer_id,)
            )
            ticket = cur.fetchone()
            if not ticket:
                print(json.dumps({"found": False}))
                return 0

            ticket_id, status, message, created_at = ticket
            result = {
                "ticket_id": ticket_id,
                "status": status,
                "message": message,
                "created_at": created_at.isoformat() if created_at else None,
                "found": True
            }
            print(json.dumps(result))
            return 0
    except Exception as e:
        sys.stderr.write("Query error\n")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()