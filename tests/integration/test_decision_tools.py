"""Tools planners asked for: 'why is the forecast this?' and 'what do I reorder today?'."""

import math

import pytest

from kairos.agent.tools import TOOLS, execute, tool_definitions

pytestmark = pytest.mark.slow


def test_explain_forecast_drivers_add_up_to_the_model_prediction(system):
    out = execute(system.ctx, "explain_forecast", {"store_id": "S01", "sku_id": "SKU002", "horizon_days": 7})
    assert not out.is_error, out.output
    r = out.output
    assert {d["driver"] for d in r["drivers"]} >= {"recent demand level", "weekly & yearly seasonality"}
    # SHAP additivity in log space: baseline x product of driver multipliers == model prediction.
    implied = r["baseline_units_per_day"] * math.prod(1 + d["effect_pct"] / 100 for d in r["drivers"])
    assert implied == pytest.approx(r["model_units_per_day"], rel=0.02)
    assert r["explained_model"] == "lightgbm" and r["run_id"] == system.forecasts.data_version


def test_reorder_worklist_ranks_store_skus_by_stockout_risk(system):
    out = execute(system.ctx, "reorder_worklist", {"store_id": "S01", "top_k": 6})
    assert not out.is_error, out.output
    rows = out.output["items"]
    assert len(rows) == 6
    risks = [r["stockout_probability"] for r in rows]
    assert risks == sorted(risks, reverse=True)
    one = execute(system.ctx, "inventory_policy", {"store_id": "S01", "sku_id": rows[0]["sku_id"]}).output
    assert rows[0]["order_qty"] == one["decision"]["order_qty"]
    assert out.output["to_order"] == sum(r["should_order"] for r in rows)


def test_new_tools_are_in_the_single_registry_and_sorted():
    names = [t["name"] for t in tool_definitions()]
    assert {"explain_forecast", "reorder_worklist"} <= set(TOOLS) and names == sorted(names)


def test_rest_exposes_explain_worklist_and_patterns(system):
    from fastapi.testclient import TestClient

    from kairos.api.main import app

    app.state.system = system
    h = {"X-API-Key": "test-key"}
    with TestClient(app) as client:
        ex = client.get("/v1/forecast/S01/SKU002/explain?horizon_days=7", headers=h)
        assert ex.status_code == 200 and ex.json()["drivers"]
        wl = client.get("/v1/inventory/worklist/S01?top_k=3", headers=h)
        assert wl.status_code == 200 and len(wl.json()["items"]) == 3
        assert client.get("/v1/inventory/worklist/S99", headers=h).status_code == 404
        card = client.get("/v1/model", headers=h).json()
        assert {p["pattern"] for p in card["demand_patterns"]} <= {"smooth", "erratic", "intermittent", "lumpy"}


def test_admin_routes_need_an_admin_key(system):
    from fastapi.testclient import TestClient

    from kairos.api.main import app

    app.state.system = system
    with TestClient(app) as client:
        assert client.post("/v1/admin/rollback", headers={"X-API-Key": "test-key"}).status_code == 403
        assert client.post("/v1/admin/train", headers={"X-API-Key": "test-key"}).status_code == 403
