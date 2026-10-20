# Failure modes and degradation

Design rule: **the read path for decisions never depends on the LLM**, and
the copilot never turns a dependency failure into a 500.

| # | Failure | Detection | Behaviour | Recovery |
|---|---|---|---|---|
| 1 | Bad data load (nulls, dupes, gaps) | Contracts at train start | Training aborts; champion keeps serving | Fix source; rerun |
| 2 | New model worse / mis-calibrated | Gates | Run stored, not promoted | Investigate leaderboard in manifest |
| 3 | Promoted model misbehaves in prod | Online WAPE alert, planner reports | — | `kairos rollback` (pointer swap, hot-reload) |
| 4 | Training crashes mid-run | Job exit code | Run dir written to `.tmp`, never published | Rerun; tmp dir cleaned |
| 5 | Publish interrupted | — | Tables replaced in one transaction | — |
| 6 | No champion yet (fresh deploy) | `/readyz` 503 | Pod not in LB; agent tools return `is_error` | Bootstrap job trains |
| 7 | LLM 429 / 5xx / timeout | SDK retries ×3 then `LLMUnavailable` | Degraded answer from tools, status `degraded` | Automatic |
| 8 | LLM refusal | `stop_reason == "refusal"` | Strong tier: server-side fallback model; else polite refusal | — |
| 9 | Model loops on tools | Step / token budget | Final no-tool call; status `budget_exhausted` | Inspect trace |
| 10 | Hallucinated number | Grounding verifier | One revision; then warning banner, no caching | Eval regression → prompt fix |
| 11 | Unsafe SQL from model | AST guard | `is_error` with reason; model rephrases | — |
| 12 | Tool bug (exception) | Caught in `execute` | `internal tool error: <Type>`; logged with trace | Fix; test |
| 13 | Prompt injection in docs | Index-time sanitiser | Sentences removed, chunk flagged untrusted | Review flagged docs |
| 14 | Stale cache after retrain | Key includes run_id | Old entries unreachable | Automatic |
| 15 | Rate-limit exhaustion | Bucket | 429 with Retry-After | Client backs off |

Every row with a test: 1, 2, 3, 7, 9, 10, 11, 13, 14 (see
`tests/unit/test_decisions.py`, `tests/unit/test_llm_safety.py`,
`tests/integration/test_system.py`).
