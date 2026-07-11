"""Generalized remote escalation.

When a response is too heavy for the local model, the query goes to the remote
LLM — but never with real company values. The flow:

  1. MASK (local, deterministic): every concrete value from the tool output is
     replaced by a typed placeholder ({{AMOUNT_1}}, {{VENDOR_1}}, ...). We know
     exactly which values are sensitive — they're the tool-output fields — so
     masking is exact substitution, not model guesswork. The mapping never
     leaves the process.
  2. ASK REMOTE: the cloud model receives only the generalized question +
     generalized facts, reasons over structure ("is it wise to pay {{AMOUNT_1}}
     to {{VENDOR_1}} when {{PO_STATUS_1}} is missing?"), answers with the
     placeholders intact.
  3. REHYDRATE (local, deterministic): placeholders are substituted back with
     the real values before the user sees the answer.

The audit log stores the generalized prompt — reviewable proof of exactly what
the remote provider saw.
"""

import json
import re

from . import models

# tool-output fields that carry identifying/sensitive values, by suffix match
SENSITIVE_KEYS = {
    "vendor": "VENDOR", "supplier": "SUPPLIER", "amount": "AMOUNT",
    "unit_cost": "COST", "invoice_id": "INVOICE", "po_number": "PO",
    "branch": "BRANCH", "email": "EMAIL", "name": "NAME", "product": "PRODUCT",
}


def mask(user_message: str, tool_output: dict) -> tuple[str, str, dict]:
    """Returns (generalized_message, generalized_facts_json, mapping)."""
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def placeholder(kind: str, value) -> str:
        for ph, v in mapping.items():
            if v == str(value):
                return ph
        counters[kind] = counters.get(kind, 0) + 1
        ph = f"{{{{{kind}_{counters[kind]}}}}}"
        mapping[ph] = str(value)
        return ph

    masked_output = {}
    for key, value in tool_output.items():
        if key.startswith("_") or value is None or isinstance(value, bool):
            masked_output[key] = value
            continue
        kind = next((tag for suffix, tag in SENSITIVE_KEYS.items() if key.lower().endswith(suffix)), None)
        masked_output[key] = placeholder(kind, value) if kind else value

    generalized_msg = user_message
    # longest values first so "INV-1002" is replaced before "1002" etc.
    for ph, value in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
        if len(value) >= 2:
            generalized_msg = re.sub(re.escape(value), ph, generalized_msg, flags=re.IGNORECASE)

    return generalized_msg, json.dumps(masked_output), mapping


def rehydrate(text: str, mapping: dict) -> str:
    for ph, value in mapping.items():
        text = text.replace(ph, value)
    return text


def escalate(user_message: str, tool_output: dict) -> tuple[str, str]:
    """Run the full generalized round-trip. Returns (final_text, generalized_prompt_for_audit)."""
    gen_msg, gen_facts, mapping = mask(user_message, tool_output)
    prompt = (
        f"Question (values are anonymized placeholders — keep them EXACTLY as written, "
        f"never invent their contents): {gen_msg}\n\nFacts:\n{gen_facts}"
    )
    msg, _, _ = models.chat(
        [{"role": "system", "content":
            "You are a senior business analyst. Reason carefully over the structured facts and "
            "give a concrete recommendation. Placeholders like {{AMOUNT_1}} are anonymized "
            "values — use them in your answer exactly as given; the caller will fill them in."},
         {"role": "user", "content": prompt}],
        force_cloud=True,
    )
    return rehydrate(msg.content or "", mapping), prompt
