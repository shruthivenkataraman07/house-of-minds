"""Canonical, versioned fingerprints for model inputs (contract `chf-v1`).

Historical fingerprints (Step 3 `InvestmentModel.fingerprint`, Step 4 snapshot IDs) are
left untouched. Cross-engine float noise (~1e-9 relative, different summation order in
DuckDB vs Databricks) changed those raw hashes; this contract removes it without altering
any financial calculation:

  * fields sorted by name; JSON with sorted keys, no whitespace
  * every number quantised with Decimal ROUND_HALF_EVEN by unit class:
      money (USD, *_usd, *_per_day, *_theo*, loss, repair)  -> 0.01
      counts (machines, events)                              -> 1
      everything else (ratios, rates, hours, factors)        -> 1e-6
  * None -> null; NaN -> "NaN"; booleans as JSON booleans
  * version string and unit map are part of the hashed payload
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

CONTRACT_VERSION = "chf-v1"
MONEY_HINTS = ("usd", "per_day", "theo", "loss", "repair", "ceiling_rate", "target_rate",
               "gap", "excess")
COUNT_HINTS = ("machines", "events_observed", "owned")


def unit_class(name: str) -> str:
    n = name.lower()
    if any(h in n for h in COUNT_HINTS):
        return "count"
    if "share" in n or "factor" in n or "per_theo" in n or "per_carded" in n \
            or n.endswith("_per_ah") or "down_h" in n:
        return "ratio"
    if any(h in n for h in MONEY_HINTS):
        return "money"
    return "ratio"


QUANTUM = {"money": Decimal("0.01"), "count": Decimal("1"), "ratio": Decimal("0.000001")}


def quantise(name: str, v: Any) -> Any:
    if v is None or isinstance(v, bool | str):
        return v
    f = float(v)
    if math.isnan(f):
        return "NaN"
    return str(Decimal(repr(f)).quantize(QUANTUM[unit_class(name)], rounding=ROUND_HALF_EVEN))


def canonical_payload(facts: dict[str, Any], assumptions: dict[str, Any],
                      source_version: str) -> dict[str, Any]:
    return {"contract": CONTRACT_VERSION, "source_version": source_version,
            "units": {k: unit_class(k) for k in sorted(facts)},
            "facts": {k: quantise(k, facts[k]) for k in sorted(facts)},
            "assumptions": {k: [quantise(k, v[0]), bool(v[1])]
                            for k, v in sorted(assumptions.items())}}


def canonical_fingerprint(model: Any, source_version: str) -> str:
    payload = canonical_payload(
        model.facts, {k: (a.value, a.valid) for k, a in model.assumptions.items()},
        source_version)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{CONTRACT_VERSION}:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
