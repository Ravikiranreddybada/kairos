"""MCP server: exposes Kairos decision tools to any MCP client
(Claude Desktop, Claude Code, IDE agents, other teams' agents).

It reuses the exact tool registry the copilot uses (``agent.tools``), so a
capability is implemented once and validated, guarded and logged the same
way whether a human asks the copilot or another agent calls it over MCP.

Run:  kairos mcp            (stdio transport)
Claude Code:  claude mcp add kairos -- kairos mcp
"""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from mcp.server.mcpserver import MCPServer

from kairos.agent.tools import TOOLS, execute
from kairos.bootstrap import System, build
from kairos.data.warehouse import SCHEMA_DOC

mcp = MCPServer(
    name="kairos",
    instructions=(
        "Supply-chain decision tools: demand forecasts with prediction intervals and driver explanations, "
        "inventory reorder policy and store reorder worklists, "
        "promotion what-if, Monte-Carlo supply-risk stress tests, multi-echelon DC pooling, model drift health, "
        "purchase-order decision history with learned lessons, anomaly detection, read-only SQL over the planning "
        "warehouse, and policy document search and browsing. All tools are read-only."
    ),
)


@cache
def _system() -> System:
    return build(use_cache=False)


def _call(name: str, args: dict[str, Any]) -> str:
    out = execute(_system().ctx, name, {k: v for k, v in args.items() if v is not None})
    return json.dumps({"is_error": out.is_error, **out.output}, default=str)


@mcp.tool(description=TOOLS["get_forecast"].description)
def get_forecast(store_id: str, sku_id: str, horizon_days: int = 28) -> str:
    return _call("get_forecast", locals())


@mcp.tool(description=TOOLS["inventory_policy"].description)
def inventory_policy(store_id: str, sku_id: str, service_level: float | None = None,
                     lead_time_override_days: float | None = None) -> str:
    return _call("inventory_policy", locals())


@mcp.tool(description=TOOLS["what_if_promo"].description)
def what_if_promo(store_id: str, sku_id: str, start_date: str | None = None, days: int = 7) -> str:
    return _call("what_if_promo", locals())


@mcp.tool(description=TOOLS["explain_forecast"].description)
def explain_forecast(store_id: str, sku_id: str, horizon_days: int = 28) -> str:
    return _call("explain_forecast", locals())


@mcp.tool(description=TOOLS["reorder_worklist"].description)
def reorder_worklist(store_id: str, service_level: float | None = None, top_k: int = 10) -> str:
    return _call("reorder_worklist", locals())


@mcp.tool(description=TOOLS["detect_anomalies"].description)
def detect_anomalies(store_id: str | None = None, sku_id: str | None = None, top_k: int = 5,
                     include_explained: bool = False) -> str:
    return _call("detect_anomalies", locals())


@mcp.tool(description=TOOLS["run_sql"].description)
def run_sql(query: str) -> str:
    return _call("run_sql", locals())


@mcp.tool(description=TOOLS["simulate_supply_risk"].description)
def simulate_supply_risk(store_id: str, sku_id: str, lead_time_delay_days: float = 0, demand_shock_pct: float = 0,
                         service_level: float | None = None) -> str:
    return _call("simulate_supply_risk", locals())


@mcp.tool(description=TOOLS["network_pooling"].description)
def network_pooling(sku_id: str, service_level: float | None = None, dc_to_store_days: float | None = None) -> str:
    return _call("network_pooling", locals())


@mcp.tool(description=TOOLS["model_health"].description)
def model_health(top_k: int = 5) -> str:
    return _call("model_health", locals())


@mcp.tool(description=TOOLS["decision_history"].description)
def decision_history(store_id: str | None = None, sku_id: str | None = None, status: str | None = None,
                     limit: int = 10) -> str:
    return _call("decision_history", locals())


@mcp.tool(description=TOOLS["browse_docs"].description)
def browse_docs(node_id: str | None = None) -> str:
    return _call("browse_docs", locals())


@mcp.tool(description=TOOLS["search_docs"].description)
def search_docs(query: str, k: int = 3) -> str:
    return _call("search_docs", locals())


@mcp.resource("kairos://schema", description="Warehouse schema for run_sql", mime_type="text/plain")
def schema() -> str:
    return SCHEMA_DOC


@mcp.resource("kairos://model-card", description="Current champion forecast model: spec, metrics, gates",
              mime_type="application/json")
def model_card() -> str:
    return json.dumps(_system().forecasts.model_card(), default=str)


if __name__ == "__main__":
    mcp.run("stdio")
