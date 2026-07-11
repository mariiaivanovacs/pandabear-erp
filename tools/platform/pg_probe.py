"""Platform probe tool (human-authored, ships with PandaBear — not generated)
for PostgreSQL sources. Discovers STRUCTURE ONLY: table names and column
name/type maps read from information_schema, never row data — this is what
lets the onboarding model design tools without ever seeing real values.

Contract: argv[1] JSON args {"sample_per_collection": int?} (unused here,
kept for symmetry with fb_probe.py's contract)
stdout: {"connected": bool, "collections": {table_name: {column: type_name}}}
"""

import json
import os
import sys


def main() -> None:
    cred_json = os.environ.get("PANDABEAR_CREDENTIAL")
    if not cred_json:
        print("Missing PANDABEAR_CREDENTIAL", file=sys.stderr)
        sys.exit(1)

    try:
        import psycopg2
        creds = json.loads(cred_json)
        conn = psycopg2.connect(
            host=creds.get("host"),
            port=int(creds.get("port") or 5432),
            dbname=creds.get("database"),
            user=creds.get("user"),
            password=creds.get("password"),
            connect_timeout=10,
        )
    except Exception:
        print(json.dumps({"connected": False, "collections": {}}))
        return

    collections: dict = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position"
            )
            for table_name, column_name, data_type in cur.fetchall():
                collections.setdefault(table_name, {})[column_name] = data_type
    except Exception:
        print(json.dumps({"connected": False, "collections": {}}))
        return
    finally:
        conn.close()

    print(json.dumps({"connected": True, "collections": collections}))


if __name__ == "__main__":
    main()
