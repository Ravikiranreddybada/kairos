"""Provider-neutral LLM interface with a Claude implementation and a deterministic fake.

Canonical message format is the Anthropic Messages shape (role + content
blocks). The agent never imports a provider SDK; it depends on ``LLMClient``.

* ``AnthropicClient`` – real model. Cost-tier routing (fast vs strong),
  prompt caching on the frozen system prompt + tool list, adaptive thinking
  controlled by ``effort``, server-side refusal fallback on the strong tier,
  typed error handling with graceful degradation.
* ``FakeLLM`` – deterministic, offline, free. Drives CI, unit tests and the
  eval gate so every PR is checked without an API key (ADR-0010). It plans
  tool calls from the question and writes answers only from tool outputs,
  so it exercises the exact same loop, guards and verifier as the real model.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from kairos.config import Settings
from kairos.observability import LLM_COST, LLM_LATENCY, LLM_TOKENS, get_logger

log = get_logger(__name__)
Tier = Literal["fast", "strong"]


class LLMUnavailable(RuntimeError):
    """Provider down / rate limited after retries. Callers degrade, never crash."""


class LLMBadRequest(RuntimeError):
    """Our request was invalid. Not retryable; indicates a bug."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __iadd__(self, other: Usage) -> Usage:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        return self

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    # Content to append verbatim as the assistant turn. For Claude this keeps
    # thinking blocks intact, which the API requires inside a tool loop.
    assistant_content: list[Any]
    stop_reason: str
    model: str
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class LLMClient(Protocol):
    def complete(
        self,
        *,
        tier: Tier,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 16000,
    ) -> LLMResponse: ...


def _cost(usage: Usage, price: tuple[float, float]) -> float:
    pin, pout = price
    # Cache reads bill at ~0.1x input, cache writes at ~1.25x input.
    return (
        usage.input_tokens * pin
        + usage.cache_read_tokens * pin * 0.1
        + usage.cache_write_tokens * pin * 1.25
        + usage.output_tokens * pout
    ) / 1_000_000


def _record(model: str, usage: Usage, cost: float, latency_s: float) -> None:
    LLM_TOKENS.labels(model, "input").inc(usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens)
    LLM_TOKENS.labels(model, "output").inc(usage.output_tokens)
    LLM_COST.labels(model).inc(cost)
    LLM_LATENCY.labels(model).observe(latency_s)


class AnthropicClient:
    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._anthropic = anthropic
        kwargs: dict[str, Any] = {"timeout": settings.llm_timeout_s, "max_retries": settings.llm_max_retries}
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
        self.client = anthropic.Anthropic(**kwargs)
        self.settings = settings

    def complete(
        self,
        *,
        tier: Tier,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 16000,
    ) -> LLMResponse:
        s = self.settings
        model = s.llm_strong_model if tier == "strong" else s.llm_fast_model
        effort = s.llm_strong_effort if tier == "strong" else s.llm_fast_effort
        price = s.llm_price_strong if tier == "strong" else s.llm_price_fast

        # Frozen system prompt + deterministic tool list = stable cache prefix.
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "tools": tools,
            "tool_choice": {"type": "auto"},
            "output_config": {"effort": effort},
        }
        if tier == "strong":
            # On a policy decline the API re-runs on a fallback model in the same call.
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"

        a = self._anthropic
        start = time.perf_counter()
        try:
            resp = self.client.beta.messages.create(**params)
        except a.BadRequestError as e:
            raise LLMBadRequest(str(e)) from e
        except (a.AuthenticationError, a.PermissionDeniedError) as e:
            raise LLMUnavailable(f"auth: {e}") from e
        except a.RateLimitError as e:
            raise LLMUnavailable("rate limited after retries") from e
        except a.APIStatusError as e:
            if e.status_code >= 500:
                raise LLMUnavailable(f"provider {e.status_code}") from e
            raise LLMBadRequest(str(e)) from e
        except a.APIConnectionError as e:  # includes APITimeoutError
            raise LLMUnavailable("connection/timeout") from e
        latency = time.perf_counter() - start

        u = resp.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        cost = _cost(usage, price)
        _record(resp.model, usage, cost, latency)

        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "refusal":
            text = text or "I can't help with that request."
            calls = []
        return LLMResponse(text, calls, list(resp.content), resp.stop_reason or "end_turn", resp.model,
                           usage, cost, latency * 1000)


# ----------------------------------------------------------------------------
# Deterministic fake
# ----------------------------------------------------------------------------
_STORE = re.compile(r"\bS\d{2}\b", re.I)
_SKU = re.compile(r"\bSKU\d{3}\b", re.I)
_PCT = re.compile(r"(\d{2}(?:\.\d+)?)\s*%")
_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_DELAY = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?days?\b")
_SHOCK = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%\s*(?:more|higher|extra|spike|surge|jump|demand)")


def _approx_tokens(obj: Any) -> int:
    return max(1, len(json.dumps(obj, default=str)) // 4)


class FakeLLM:
    """Rule-based stand-in for Claude. Deterministic by design."""

    model = "fake-llm"

    def plan(self, question: str) -> list[ToolCall]:
        q = question.lower()
        store = (_STORE.search(question) or [None])[0]
        sku = (_SKU.search(question) or [None])[0]
        store = store.upper() if store else None
        sku = sku.upper() if sku else None
        calls: list[ToolCall] = []

        def add(name: str, **inp: Any) -> None:
            calls.append(ToolCall(f"call_{len(calls)}", name, {k: v for k, v in inp.items() if v is not None}))

        policy_words = ("reorder", "order", "safety stock", "stock out", "stockout risk", "service level", "replenish")
        doc_words = ("policy", "contract", "sop", "penalty", "playbook", "escalat", "according to", "rule", "guideline")
        sim_words = ("stress test", "simulat", "monte carlo", "delay", "late deliver", "disrupt", "lost sales",
                     "demand shock", "supplier is late", "days late")
        if any(w in q for w in ("drop table", "delete from", "truncate", "update ", "insert into")):
            add("run_sql", query=question)
        elif any(w in q for w in ("outline", "table of contents", "browse", "what documents")):
            node = re.search(r"\b(inventory_policy|supplier_contracts|promotion_playbook|escalation_sop|vendor_portal_note)\b", q)
            add("browse_docs", node_id=node.group(1) if node else None)
        elif any(w in q for w in sim_words) and store and sku:
            delay = _DELAY.search(q)
            shock = _SHOCK.search(q)
            add("simulate_supply_risk", store_id=store, sku_id=sku,
                lead_time_delay_days=float(delay.group(1)) if delay else 0.0,
                demand_shock_pct=float(shock.group(1)) if shock else 0.0)
        elif any(w in q for w in ("pool", "distribution cent", " dc", "echelon", "network")) and sku:
            add("network_pooling", sku_id=sku)
        elif any(w in q for w in ("overrid", "past decision", "track record", "lesson", "approved", "proposal")):
            add("decision_history", store_id=store, sku_id=sku)
        elif any(w in q for w in ("drift", "model health", "stale", "still valid", "trust the forecast")):
            add("model_health", top_k=5)
        elif "what if" in q or ("promo" in q and ("run" in q or "launch" in q) and (store or sku)):
            date = (_DATE.search(question) or [None])[0]
            add("what_if_promo", store_id=store or "S01", sku_id=sku or "SKU001", start_date=date, days=7)
        elif re.search(r"\bwhy\b|explain|driv", q) and store and sku:
            add("explain_forecast", store_id=store, sku_id=sku, horizon_days=7 if "week" in q else 28)
        elif any(w in q for w in policy_words) and store and not sku:
            m = _PCT.search(question)
            add("reorder_worklist", store_id=store, service_level=float(m.group(1)) / 100 if m else None,
                top_k=5)
        elif any(w in q for w in policy_words) and store and sku:
            m = _PCT.search(question)
            add("inventory_policy", store_id=store, sku_id=sku,
                service_level=float(m.group(1)) / 100 if m else None)
        elif "anomal" in q or "unusual" in q or "spike" in q:
            add("detect_anomalies", store_id=store, sku_id=sku, top_k=5)
        elif ("forecast" in q or ("next" in q and ("week" in q or "days" in q))) and store and sku:
            days = 7 if "week" in q else 28
            add("get_forecast", store_id=store, sku_id=sku, horizon_days=days)
        elif any(w in q for w in doc_words):
            add("search_docs", query=question)
        elif any(w in q for w in ("how many", "total", "sum", "average", "top", "which", "list", "count")):
            add("run_sql", query=self._nl_to_sql(q, store, sku))
        if any(w in q for w in doc_words) and calls and calls[0].name not in ("search_docs", "browse_docs"):
            add("search_docs", query=question)
        return calls

    @staticmethod
    def _nl_to_sql(q: str, store: str | None, sku: str | None) -> str:
        where = []
        if store:
            where.append(f"store_id = '{store}'")
        if sku:
            where.append(f"sku_id = '{sku}'")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        if "supplier" in q:
            return ("SELECT supplier_id, name, lead_time_mean_days, on_time_rate FROM dim_supplier "
                    "ORDER BY on_time_rate ASC")
        if "top" in q or "best" in q:
            return (f"SELECT sku_id, SUM(units_sold) AS units FROM fact_sales{clause} "
                    "GROUP BY sku_id ORDER BY units DESC LIMIT 5")
        if "stockout" in q:
            return f"SELECT COUNT(*) AS stockout_days FROM fact_sales{clause}{' AND' if clause else ' WHERE'} stockout"
        return f"SELECT SUM(units_sold) AS total_units FROM fact_sales{clause}"

    def answer(self, question: str, results: list[tuple[str, dict[str, Any]]]) -> str:
        lines = []
        for name, r in results:
            if "error" in r:
                lines.append(f"I could not complete `{name}`: {r['error']}")
                continue
            if name == "get_forecast":
                lines.append(
                    f"Forecast for {r['store_id']}/{r['sku_id']} over the next {r['horizon_days']} days: "
                    f"{r['total_units']} units (80% interval {r['total_lo']}–{r['total_hi']}), "
                    f"model {r['model']}, run {r['run_id']}."
                )
            elif name == "inventory_policy":
                d = r["decision"]
                act = f"order {d['order_qty']} units" if d["should_order"] else "no order needed"
                lines.append(
                    f"For {d['store_id']}/{d['sku_id']} at {d['service_level']} service level: reorder point "
                    f"{d['reorder_point']}, safety stock {d['safety_stock']}, inventory position "
                    f"{d['inventory_position']} → {act}. Stockout probability {d['stockout_probability']}."
                )
            elif name == "explain_forecast":
                drivers = ", ".join(f"{d['driver']} {d['effect_pct']:+}%" for d in r["drivers"][:3])
                lines.append(
                    f"For {r['store_id']}/{r['sku_id']} a typical day is {r['model_units_per_day']} units against "
                    f"a baseline of {r['baseline_units_per_day']}. Biggest drivers: {drivers}. Run {r['run_id']}."
                )
            elif name == "reorder_worklist":
                top = [i for i in r["items"] if i["should_order"]]
                lines.append(f"{r['to_order']} of the top {len(r['items'])} SKUs at {r['store_id']} need an order "
                             f"(service level {r['service_level']}):")
                for i in top or r["items"][:3]:
                    act = f"order {i['order_qty']} units" if i["should_order"] else "no order"
                    lines.append(f"- {i['sku_id']}: stockout probability {i['stockout_probability']}, {act}.")
            elif name == "what_if_promo":
                lines.append(
                    f"Running a {r['days']}-day promotion on {r['store_id']}/{r['sku_id']} from {r['start_date']} "
                    f"changes expected units from {r['baseline_units']} to {r['promo_units']} "
                    f"(uplift {r['uplift_pct']}%)."
                )
            elif name == "detect_anomalies":
                items = r.get("anomalies", [])[:3]
                if not items:
                    lines.append("No unexplained anomalies found.")
                for a in items:
                    lines.append(f"{a['date']} {a['store_id']}/{a['sku_id']}: {a['explanation']}.")
            elif name == "simulate_supply_risk":
                b, d = r["baseline"], r["disrupted"]
                lines.append(
                    f"Stress test for {r['store_id']}/{r['sku_id']} over {b['horizon_days']} days "
                    f"({b['n_paths']} simulated paths): as-is, chance of at least one stockout day {b['prob_stockout_in_horizon']}, "
                    f"fill rate {b['fill_rate']}, expected lost units {b['expected_lost_units']}."
                )
                if d:
                    sc = r["scenario"]
                    lines.append(
                        f"With a {sc['lead_time_delay_days']}-day supplier delay and {sc['demand_shock_pct']}% demand "
                        f"shock: chance of a stockout day {d['prob_stockout_in_horizon']}, fill rate {d['fill_rate']}, expected "
                        f"lost units {d['expected_lost_units']} (change {r['stockout_risk_change_pts']} pts)."
                    )
                lines.append(f"Distribution-free reorder point {r['distribution_free_reorder_point']} vs policy "
                             f"{r['policy']['reorder_point']}; order now: {r['recommended_order_now']} units. "
                             f"Run {r['run_id']}.")
            elif name == "network_pooling":
                lines.append(
                    f"{r['sku_id']} across {len(r['stores'])} stores at {r['service_level']} service level: store-direct "
                    f"safety stock {r['store_direct_total_ss']} vs DC pooled {r['dc_pooled_ss']} plus store legs = "
                    f"{r['two_echelon_total_ss']} ({r['pct_saved']}% saved). Verdict: {r['verdict']}. "
                    f"Mean demand correlation {r['mean_demand_correlation']}; break-even DC-to-store "
                    f"{r['break_even_dc_to_store_days']} days."
                )
            elif name == "model_health":
                worst = ", ".join(f"{w['store_id']}/{w['sku_id']}" for w in r["worst"][:3] if w["drifting"])
                lines.append(
                    f"Model health: {r['status']}. {r['series_drifting']} of {r['series_checked']} series drifting "
                    f"({r['series_level_shifted']} with a level shift vs forecast); backtest WAPE "
                    f"{r['backtest_wape']}, coverage {r['backtest_coverage']}. Run {r['run_id']}."
                    + (f" Most drifted: {worst}." if worst else "")
                )
            elif name == "decision_history":
                chain = "intact" if r["audit_chain"]["ok"] else "BROKEN"
                lines.append(f"{r['count']} recorded purchase-order decisions; audit chain {chain} "
                             f"({r['audit_chain']['entries']} entries).")
                for lesson in r["lessons"][:3]:
                    lines.append(f"- {lesson['observation']} Confidence: {lesson['confidence']}.")
                if not r["lessons"]:
                    lines.append("No approved decisions yet, so there are no override lessons.")
            elif name == "browse_docs":
                if "documents" in r:
                    for doc in r["documents"]:
                        flag = " (untrusted source)" if doc["untrusted"] else ""
                        lines.append(f"- {doc['title']} [{doc['node_id']}]{flag}: {', '.join(doc['sections'])}")
                elif "sections" in r:
                    lines.append(f"{r['title']}:")
                    lines += [f"- {c['title']}: {c['summary']} [{c['node_id']}]" for c in r["sections"]]
                else:
                    lines.append(f"{r['text'][:400]} [source: {r['cite_as']}]")
            elif name == "run_sql":
                rows = r.get("rows", [])
                lines.append(f"Query returned {r.get('row_count', len(rows))} rows: {json.dumps(rows[:5], default=str)}")
            elif name == "search_docs":
                hits = r.get("results", [])
                if not hits:
                    lines.append("I found no relevant policy documents.")
                for h in hits[:2]:
                    lines.append(f"{h['text'][:220].strip()} [source: {h['source']}#{h['section']}]")
        if not lines:
            return ("I can answer questions about forecasts, inventory policy, anomalies, what-if promotions, "
                    "sales data and supply policies. Please name a store (e.g. S01) and SKU (e.g. SKU002).")
        return "\n".join(lines)

    def complete(
        self,
        *,
        tier: Tier,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 16000,
    ) -> LLMResponse:
        start = time.perf_counter()
        # Last user turn is the newest question (history may precede it).
        question = [m["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], str)][-1]
        tool_results = _collect_tool_results(messages)
        usage = Usage(input_tokens=_approx_tokens([system, messages, tools]))
        if not tool_results:
            calls = self.plan(question)
            if calls:
                content = [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]
                usage.output_tokens = _approx_tokens(content)
                return LLMResponse("", calls, content, "tool_use", self.model, usage, 0.0,
                                   (time.perf_counter() - start) * 1000)
        text = self.answer(question, tool_results)
        usage.output_tokens = _approx_tokens(text)
        return LLMResponse(text, [], [{"type": "text", "text": text}], "end_turn", self.model, usage, 0.0,
                           (time.perf_counter() - start) * 1000)


def _collect_tool_results(messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Pair tool_use names with their results from the current turn only."""
    last_q = max(i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str))
    names: dict[str, str] = {}
    out: list[tuple[str, dict[str, Any]]] = []
    for m in messages[last_q + 1 :]:
        if not isinstance(m["content"], list):
            continue
        for b in m["content"]:
            btype = b["type"] if isinstance(b, dict) else getattr(b, "type", None)
            if btype == "tool_use":
                names[b["id"] if isinstance(b, dict) else b.id] = b["name"] if isinstance(b, dict) else b.name
            elif btype == "tool_result":
                try:
                    payload = json.loads(b["content"])
                except (TypeError, json.JSONDecodeError):
                    payload = {"error": str(b["content"])}
                out.append((names.get(b["tool_use_id"], "unknown"), payload))
    return out


def build_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "anthropic":
        return AnthropicClient(settings)
    return FakeLLM()
