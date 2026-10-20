"""Multi-user safety: one planner's session must never change another planner's answers."""

import pytest

pytestmark = pytest.mark.slow


def test_service_level_preference_stays_in_its_session(system):
    system.copilot.ask("Our target service level is 99%.", "planner-a")
    a = system.copilot.ask("Should we reorder SKU002 at S01?", "planner-a")
    b = system.copilot.ask("Should we reorder SKU002 at S01?", "planner-b")
    assert "0.99 service level" in a.answer
    assert "0.95 service level" in b.answer


def test_streamed_turn_is_remembered_like_a_normal_turn(system):
    events = list(system.copilot.stream("forecast S01 SKU001 next week", "streamer"))
    assert events[-1]["event"] == "result" and events[-1]["status"] == "ok"
    history = system.copilot.memory.history("streamer")
    assert history[0]["content"] == "forecast S01 SKU001 next week"


def test_llm_sql_cannot_hang_the_warehouse(system):
    import dataclasses

    from kairos.agent.tools import execute

    ctx = dataclasses.replace(system.ctx, sql_timeout_s=0.3)
    out = execute(ctx, "run_sql", {"query": "SELECT COUNT(*) FROM fact_sales a, fact_sales b, fact_sales c"})
    assert out.is_error and "exceeded" in out.output["error"]
    assert out.latency_ms < 3000
