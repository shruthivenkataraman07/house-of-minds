"""Optional LLM adapter (not used in RULE_BASED mode).

Bounded calls with timeout, retries, token budget and schema validation. Any failure
returns a structured error and the council continues with deterministic analysis; LLM
output can never bypass the verifier or reach the optimiser directly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError


class Provider(Protocol):
    name: str
    model: str

    def complete(self, prompt: str, timeout_s: float) -> tuple[str, int]: ...


@dataclass
class LLMCallRecord:
    provider: str
    model: str
    prompt_version: str
    status: str  # OK | TIMEOUT | INVALID_JSON | SCHEMA_ERROR | BUDGET_EXCEEDED | DISABLED
    attempts: int
    tokens: int
    latency_s: float
    output: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class LLMBudget:
    max_tokens: int = 20_000
    used: int = 0


def call_structured(provider: Provider | None, prompt: str, schema: type[BaseModel],
                    budget: LLMBudget, prompt_version: str = "v1", timeout_s: float = 20.0,
                    max_retries: int = 1) -> LLMCallRecord:
    if provider is None:
        return LLMCallRecord("none", "none", prompt_version, "DISABLED", 0, 0, 0.0)
    rec = LLMCallRecord(provider.name, provider.model, prompt_version, "OK", 0, 0, 0.0)
    t0 = time.perf_counter()
    for _ in range(max_retries + 1):
        if budget.used >= budget.max_tokens:
            rec.status = "BUDGET_EXCEEDED"
            break
        rec.attempts += 1
        try:
            text, tokens = provider.complete(prompt, timeout_s)
        except TimeoutError as e:
            rec.status, rec.errors = "TIMEOUT", rec.errors + [str(e)]
            continue
        budget.used += tokens
        rec.tokens += tokens
        try:
            rec.output = schema.model_validate(json.loads(text)).model_dump()
            rec.status = "OK"
            break
        except json.JSONDecodeError as e:
            rec.status, rec.errors = "INVALID_JSON", rec.errors + [str(e)]
        except ValidationError as e:
            rec.status, rec.errors = "SCHEMA_ERROR", rec.errors + [str(e)[:200]]
    rec.latency_s = time.perf_counter() - t0
    if rec.status != "OK":
        rec.output = None
    return rec
