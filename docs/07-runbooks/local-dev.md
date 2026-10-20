# Runbook: local development

## First run (≈ 2 minutes)

```bash
make setup                 # venv + all extras
make seed                  # var/warehouse.duckdb (35,040 rows)
make train                 # backtest 4 models, calibrate, gate, promote (~25 s)
make ask Q="Should we reorder SKU002 at S01?"
make serve                 # http://localhost:8000/docs  (X-API-Key: dev-key)
```

## Daily loop

```bash
make check                 # ruff + mypy + pytest + eval gate  (what CI runs)
pytest -m "not slow" -q    # unit tests only, seconds
```

## Use the real model

```bash
export KAIROS_LLM_PROVIDER=anthropic
export KAIROS_ANTHROPIC_API_KEY=sk-ant-...      # or `ant auth login`
make ask Q="Compare the reorder needs of SKU002 and SKU008 at S01 and explain why"
make eval                  # same golden set, real model (costs money)
```

## Connect the MCP server to Claude Code / Claude Desktop

```bash
claude mcp add kairos -- /abs/path/.venv/bin/kairos mcp
```
Claude Desktop `claude_desktop_config.json`:
```json
{"mcpServers": {"kairos": {"command": "/abs/path/.venv/bin/kairos", "args": ["mcp"],
                           "env": {"KAIROS_DATA_DIR": "/abs/path/var"}}}}
```

## Full stack with metrics

```bash
make up        # api :8000, prometheus :9090, grafana :3000 (admin/admin)
make down
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/readyz` 503 | No champion | `make train` |
| `lightgbm` import error on macOS | missing OpenMP | `brew install libomp` |
| `IO Error: Could not set lock` | Another process holds the DuckDB file | Stop the API before `kairos train`, or use `/v1/admin/train` |
| Agent answers `degraded` | LLM unavailable / bad key | Check key; logs show `llm.call` with `degraded` |
