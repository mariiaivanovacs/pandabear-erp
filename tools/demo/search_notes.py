"""Search organizational memory (channel posts, notes). No credential needed —
memory is local. Contract: argv[1] JSON args -> stdout JSON."""

import json
import os
import sys

sys.path.insert(0, os.getcwd())


def run(args: dict) -> dict:
    from pandabear.memory import search_notes

    query = str(args.get("query", "")).strip()
    if not query:
        return {"found": False, "notes": []}
    notes = search_notes(query, top_k=int(args.get("top_k", 5)))
    return {"found": bool(notes), "notes": notes}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}"))))
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
