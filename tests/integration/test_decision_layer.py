"""v2 decision layer end-to-end: stress test, pooling, health, doc tree, and the human sign-off workflow."""

import pytest
from fastapi.testclient import TestClient

from kairos.agent.tools import TOOLS, execute

pytestmark = pytest.mark.slow

PLANNER = {"X-API-Key": "test-key"}
APPROVER = {"X-API-Key": "dev-approver-key"}


@pytest.fixture()
def client(system):
    from kairos.api.main import app

    app.state.system = system
    with TestClient(app) as c:
        yield c


def test_stress_test_tool_compares_as_is_with_a_supplier_delay(system):
    out = execute(system.ctx, "simulate_supply_risk",
                  {"store_id": "S01", "sku_id": "SKU002", "lead_time_delay_days": 10})
    assert not out.is_error, out.output
    r = out.output
    assert r["disrupted"]["fill_rate"] <= r["baseline"]["fill_rate"]
    assert r["disrupted"]["expected_lost_units"] >= r["baseline"]["expected_lost_units"]
    assert r["run_id"] == system.forecasts.data_version
    # Seeded: the same question gives the same numbers (cacheable, auditable).
    again = execute(system.ctx, "simulate_supply_risk",
                    {"store_id": "S01", "sku_id": "SKU002", "lead_time_delay_days": 10}).output
    assert again == r


def test_network_pooling_and_model_health_tools(system):
    pool = execute(system.ctx, "network_pooling", {"sku_id": "SKU002"})
    assert not pool.is_error, pool.output
    p = pool.output
    assert len(p["stores"]) == 2 and p["dc_pooled_ss"] <= p["store_direct_total_ss"] + 1e-6
    assert p["store_direct_total_ss"] == pytest.approx(sum(s["store_direct_ss"] for s in p["stores"]), abs=0.2)
    health = execute(system.ctx, "model_health", {"top_k": 3})
    assert not health.is_error and health.output["series_checked"] == 12
    assert health.output["status"] in {"healthy", "watch", "retrain_recommended"}


def test_unknown_inputs_fail_softly(system):
    assert execute(system.ctx, "network_pooling", {"sku_id": "SKU999"}).is_error
    assert execute(system.ctx, "browse_docs", {"node_id": "nope"}).is_error
    bad = execute(system.ctx, "simulate_supply_risk", {"store_id": "S01", "sku_id": "SKU002",
                                                       "lead_time_delay_days": -3})
    assert bad.is_error and "invalid arguments" in bad.output["error"]


def test_new_tools_stay_read_only_and_in_one_registry(system):
    assert {"simulate_supply_risk", "network_pooling", "model_health", "decision_history",
            "browse_docs"} <= set(TOOLS)
    before = system.ledger.verify_chain()["entries"]
    execute(system.ctx, "decision_history", {})
    assert system.ledger.verify_chain()["entries"] == before  # reading never writes


def test_human_sign_off_workflow_feeds_copilot_lessons(system, client):
    # Pick a SKU the policy says to order.
    wl = client.get("/v1/inventory/worklist/S01?top_k=6", headers=PLANNER).json()
    sku = next((i["sku_id"] for i in wl["items"] if i["should_order"]), None)
    if sku is None:
        pytest.skip("no SKU needs an order in this dataset")

    created = client.post("/v1/decisions/proposals", json={"store_id": "S01", "sku_id": sku}, headers=PLANNER)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    rec = created.json()["recommended_qty"]

    # Planner key cannot approve; approver cannot override without a reason.
    assert client.post(f"/v1/decisions/proposals/{pid}/approve", json={}, headers=PLANNER).status_code == 403
    no_reason = client.post(f"/v1/decisions/proposals/{pid}/approve", json={"qty": rec + 50}, headers=APPROVER)
    assert no_reason.status_code == 409

    ok = client.post(f"/v1/decisions/proposals/{pid}/approve",
                     json={"qty": rec + 50, "reason": "local festival"}, headers=APPROVER)
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["final_qty"] == rec + 50
    assert client.post(f"/v1/decisions/proposals/{pid}/approve", json={}, headers=APPROVER).status_code == 409

    out = client.post(f"/v1/decisions/proposals/{pid}/outcome", json={"actual_demand": 400}, headers=PLANNER)
    assert out.status_code == 200 and out.json()["model_error"] is not None

    detail = client.get(f"/v1/decisions/proposals/{pid}", headers=PLANNER).json()
    assert [a["action"] for a in detail["audit"]] == ["proposed", "approved", "outcome"]
    assert client.get("/v1/decisions/audit/verify", headers=PLANNER).json()["ok"]
    lessons = client.get(f"/v1/decisions/lessons?store_id=S01&sku_id={sku}", headers=PLANNER).json()["lessons"]
    assert lessons and lessons[0]["overrides"] >= 1

    # The copilot reads the same ledger through its read-only tool.
    res = system.copilot.ask(f"Have planners overridden orders for S01 {sku}?", session_id="ledger-test")
    assert [t["name"] for t in res.tool_calls] == ["decision_history"]
    assert "overridden" in res.answer and res.grounding["passed"]


def test_rest_exposes_stress_network_and_health(client):
    st = client.post("/v1/inventory/stress-test", json={"store_id": "S01", "sku_id": "SKU002",
                                                         "demand_shock_pct": 40}, headers=PLANNER)
    assert st.status_code == 200 and st.json()["disrupted"] is not None
    assert client.get("/v1/inventory/network/SKU002", headers=PLANNER).status_code == 200
    assert client.get("/v1/model/health", headers=PLANNER).json()["series_checked"] == 12
    assert client.get("/v1/decisions/proposals/PO-missing", headers=PLANNER).status_code == 404
