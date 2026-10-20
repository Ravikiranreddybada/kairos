PY ?= .venv/bin/python
BIN = .venv/bin

.PHONY: setup seed train serve ask eval test lint type check docker up down mcp clean

setup:            ## create venv + install everything
	python3 -m venv .venv && $(BIN)/pip install -U pip && $(BIN)/pip install -e ".[dev,mcp,llm]"

seed:             ## generate synthetic data into var/warehouse.duckdb
	$(BIN)/kairos seed

train:            ## backtest, select, calibrate, gate, promote
	$(BIN)/kairos train

serve:            ## REST API on :8000 (docs at /docs)
	$(BIN)/kairos serve

ask:              ## make ask Q="Should we reorder SKU002 at S01?"
	$(BIN)/kairos ask "$(Q)"

eval:             ## golden-set eval with CI gate
	$(BIN)/kairos eval --gate

mcp:              ## MCP server on stdio
	$(BIN)/kairos mcp

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check src tests

type:
	$(BIN)/mypy src

check: lint type test eval   ## everything CI runs

docker:
	docker build -t kairos:local .

up:
	cp -n .env.example .env 2>/dev/null || true; docker compose up --build

down:
	docker compose down -v

clean:
	rm -rf var .pytest_cache .mypy_cache .ruff_cache
