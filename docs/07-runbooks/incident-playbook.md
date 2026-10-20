# Incident playbook

Start every incident with the trace id (from the `x-trace-id` header or the
user's screenshot) and grep the JSON logs for it: the full span tree (agent →
llm calls → tools) is there.

## P1 – Forecast/policy API down or 5xx > 1%
1. `kubectl get pods`, `/readyz`. If not ready → champion missing or registry volume unmounted.
2. Check `kairos_http_request_seconds{status=~"5.."}` by route.
3. Recent deploy? `kubectl rollout undo deploy/kairos-api`.
4. Warehouse locked? (DuckDB single writer) → ensure training runs as the job, not in-pod.

## P2 – Planners report "numbers look wrong"
1. Get the `run_id` from the answer/forecast response.
2. `GET /v1/model` → check gates, data fingerprint, date range. Was data stale or partial?
3. Compare realised vs forecast for the series; check `quality.json` in the run dir.
4. If the model is at fault → `kairos rollback`; open an eval case for the failure.

## P2 – Copilot degraded / slow
1. Status mix on the Copilot dashboard: many `degraded` → provider issue (check `llm.call` spans for the error class).
2. Latency up with no errors → token growth? Check `kairos_llm_tokens_total` by model; a prompt or tool payload change usually explains it.
3. Cost spike → cache hit rate dropped (new run_id invalidates – expected after promotion) or routing shifted to strong tier.

## P3 – Suspected prompt injection
1. Find blocked attempts: logs with `status: blocked`.
2. For document-borne attempts: list chunks with `untrusted: true`; review the source document; remove from corpus if malicious.
3. Add the payload as a golden-set security case.

## Post-incident
Every incident produces: a regression test or eval case, a runbook update if a step was missing, and an ADR if a design assumption was wrong.
