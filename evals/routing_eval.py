"""Routing quality gate: does the model pick the right capability with the right
arguments? Runs the same eval set through the local model and the OpenAI baseline
and prints a comparison table. This is the number that goes in the deck.

Run: uv run python evals/routing_eval.py [--models local,cloud]
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI  # noqa: E402

from pandabear import registry  # noqa: E402
from pandabear.config import settings  # noqa: E402
from pandabear.graph import SYSTEM_PROMPT  # noqa: E402

# Each case: utterance -> expected capability (or None = should NOT call a tool)
# and the argument key/values that must appear (substring match, case-insensitive).
EVAL_SET = [
    # clear matches
    {"q": "Can we reorder oat milk for branch 5?", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "5"}},
    {"q": "check stock of oat milk in branch 5", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "5"}},
    {"q": "how much espresso beans does branch 5 have left", "cap": "inventory_check_stock", "args": {"product": "espresso", "branch": "5"}},
    {"q": "is branch 2 running low on oat milk?", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "2"}},
    {"q": "stock status for oat milk at branch two", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "2"}},
    {"q": "do we need to restock oat milk at the 5th branch", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "5"}},
    {"q": "inventory check: espresso beans, branch 5", "cap": "inventory_check_stock", "args": {"product": "espresso", "branch": "5"}},
    {"q": "will branch 5 run out of oat milk soon?", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "5"}},
    # paraphrase / noisy phrasing
    {"q": "yo quick q - r we good on oat milk over at branch5??", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "5"}},
    {"q": "Branch 5 said they're almost out of the oat milk again, can you check", "cap": "inventory_check_stock", "args": {"product": "oat milk", "branch": "5"}},
    # missing info -> should ask, not guess
    {"q": "can we reorder oat milk?", "cap": None},
    {"q": "check the stock", "cap": None},
    # out of scope -> should refuse/no-match, not hallucinate a call
    {"q": "give everyone at branch 5 a raise", "cap": None},
    {"q": "what's the weather in branch 5's city", "cap": None},
    {"q": "delete all inventory records", "cap": None},
    {"q": "who won the world cup in 2022", "cap": None},
]


def run_model(client: OpenAI, model: str, tools: list[dict]) -> dict:
    correct_cap = correct_args = json_valid = 0
    latencies = []
    rows = []

    for case in EVAL_SET:
        start = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": case["q"]}],
                tools=tools, temperature=0,
            )
            msg = resp.choices[0].message
        except Exception as e:
            rows.append((case["q"][:40], "API-ERROR", str(e)[:40]))
            continue
        latencies.append(time.monotonic() - start)

        picked, args, valid = None, {}, True
        if msg.tool_calls:
            picked = msg.tool_calls[0].function.name
            try:
                args = json.loads(msg.tool_calls[0].function.arguments or "{}")
            except json.JSONDecodeError:
                valid = False
        json_valid += valid

        cap_ok = picked == case["cap"]
        correct_cap += cap_ok

        args_ok = cap_ok
        if cap_ok and case["cap"] and case.get("args"):
            blob = json.dumps(args).lower()
            args_ok = all(str(v).lower() in blob for v in case["args"].values())
        correct_args += args_ok

        rows.append((case["q"][:40], picked or "—", "✓" if args_ok else "✗"))

    n = len(EVAL_SET)
    return {
        "model": model,
        "capability_accuracy": correct_cap / n,
        "argument_accuracy": correct_args / n,
        "json_validity": json_valid / n,
        "avg_latency_s": sum(latencies) / len(latencies) if latencies else None,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="local,cloud")
    args = parser.parse_args()

    tools = registry.as_openai_tools()
    if not tools:
        sys.exit("no active capabilities — run scripts/seed_demo.py first")

    results = []
    for which in args.models.split(","):
        if which == "local":
            client = OpenAI(base_url=settings.ollama_base_url, api_key="ollama")
            model = settings.local_model
        elif which == "cloud":
            if not settings.openai_api_key:
                print("skipping cloud: OPENAI_API_KEY not set")
                continue
            client = OpenAI(api_key=settings.openai_api_key)
            model = settings.cloud_model
        else:
            continue
        print(f"\n=== {which}: {model} ({len(EVAL_SET)} cases) ===")
        r = run_model(client, model, tools)
        for q, picked, ok in r["rows"]:
            print(f"  {ok}  {q:<42} -> {picked}")
        results.append(r)

    print(f"\n{'model':<24}{'cap acc':>10}{'arg acc':>10}{'json ok':>10}{'avg lat':>10}")
    for r in results:
        lat = f"{r['avg_latency_s']:.1f}s" if r["avg_latency_s"] else "n/a"
        print(f"{r['model']:<24}{r['capability_accuracy']:>9.0%}{r['argument_accuracy']:>10.0%}"
              f"{r['json_validity']:>10.0%}{lat:>10}")

    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps([{k: v for k, v in r.items() if k != "rows"} for r in results], indent=2))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
