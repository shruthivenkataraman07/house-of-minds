# AI-use disclosure

**Short version (for submission):** We used Claude Code (Anthropic) as a coding assistant to write, run and test the code, SQL and documentation, under human direction. The analytics use no LLMs: forecasting is a statsmodels Holt-Winters model, optimisation is an exact MILP, and the six council agents are RULE_BASED deterministic analyses with a deterministic verifier. No LLM calls were made by the product (0 tokens, $0). The Ask the House interface is not yet built.

## Detailed record (from `ai_usage_audit`)

| Area | Implementation | Evidence | LLM used | Status |
|---|---|---|---|---|
| A. Coding assistance | Claude Code (Anthropic) in VS Code wrote and ran the code, SQL, tests and docs under human direction | docs/AI_USE_LOG.md entries per step | True | USED (development only; not part of the analytical pipeline) |
| B. Predictive modeling | Holt-Winters additive weekly seasonality, trend=add (damped); baseline weekday mean of training window; holdout 2025-05-01..2025-06-30 | model_evaluation_runs S5-4F2E08B4433A | False | statsmodels time-series model, not an LLM |
| C. Adversarial council | Six RULE_BASED specialist agents: deterministic analyses over allowlisted read-only tools | council_runs.execution_mode = ['RULE_BASED'] | False | NOT LLM agents |
| D. Whisper Network | Deterministic routing, budgets, origin tracking, duplicate suppression, retraction propagation | council_whispers | False | deterministic |
| E. LLM calls in the product | None; an adapter exists (council/llm.py) but is not called and no provider is configured | llm_tokens=0, llm_cost_usd=0.0 | False | NONE |
| F. Natural-language interface | Ask the House semantic contract only; no chat interface exists | semantic/ask_the_house_contract.json | False | NOT YET IMPLEMENTED |
| G. Human oversight | Causal promotion uplift, inspection fix probability, move transfer, cross-platform forecast metrics | claims_evidence_registry | False | requires human / experimental validation |
