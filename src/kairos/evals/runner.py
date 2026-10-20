"""Golden-set evaluation of the copilot, with a CI gate.

Metrics, and why each exists:

* ``tool_selection_f1``  – did the agent call the right tools (and only those)?
  Wrong tool = wrong answer, regardless of how fluent the text is.
* ``answer_correctness`` – for cases with a ``reference_sql``, the ground-truth
  value is recomputed *from the live warehouse*, so the golden set never goes
  stale when data or models change. The answer must contain it (within tolerance).
* ``retrieval_hit_rate`` – for policy questions, was the expected
  ``source#section`` retrieved? (context recall; isolates retriever bugs from
  generation bugs).
* ``numeric_grounding``  – share of answer numbers traceable to tool outputs
  (faithfulness / hallucination rate).
* ``security_pass_rate`` – injection blocked, destructive SQL rejected,
  poisoned-document content never surfaces.
* latency p95 and mean cost – quality that is too slow or expensive is a regression too.

Offline (FakeLLM) this gates every PR for free; with ``KAIROS_LLM_PROVIDER=anthropic``
the same suite scores the real model (nightly job). ``to_ragas_rows`` exports
the RAG cases in the column layout RAGAS / DeepEval expect.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

from kairos.bootstrap import System

HERE = Path(__file__).parent


def load_cases(path: Path = HERE / "golden.jsonl") -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_thresholds(path: Path = HERE / "thresholds.json") -> dict[str, float]:
    return {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}


def _contains_value(answer: str, value: Any, tol: float) -> bool:
    if isinstance(value, str):
        return value.lower() in answer.lower()
    nums = [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", answer)]
    v = float(value)
    return any(abs(n - v) <= max(tol * abs(v), 0.051) for n in nums)


def _tool_f1(expected: set[str], actual: set[str]) -> float:
    if not expected and not actual:
        return 1.0
    tp = len(expected & actual)
    p = tp / len(actual) if actual else 0.0
    r = tp / len(expected) if expected else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def score_case(system: System, case: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    res = system.copilot.ask(case["question"], session_id=f"eval-{case['id']}")
    latency = (time.perf_counter() - start) * 1000
    tools = {t["name"] for t in res.tool_calls}
    row: dict[str, Any] = {
        "id": case["id"], "category": case["category"], "status": res.status, "tools": sorted(tools),
        "tool_f1": _tool_f1(set(case.get("expected_tools", [])), tools),
        "grounding": res.grounding.get("score", 1.0), "latency_ms": latency, "cost_usd": res.cost_usd,
        "answer": res.answer,
    }
    if "reference_sql" in case:
        ref = system.wh.query(case["reference_sql"]).iloc[0, 0]
        ref = ref.item() if hasattr(ref, "item") else ref
        row["reference"] = ref
        row["correct"] = _contains_value(res.answer, ref, case.get("tolerance", 0.02))
    if "must_contain" in case:
        row["must_contain_ok"] = all(s.lower() in res.answer.lower() for s in case["must_contain"])
    if "expected_sources" in case:
        retrieved = {
            f"{h.chunk.source}#{h.chunk.section}" for h in system.index.search(case["question"], k=3)
        }
        row["retrieval_hit"] = all(s in retrieved for s in case["expected_sources"])
    if case["category"] == "security" or "must_not_contain" in case:
        ok = True
        if "expect_status" in case:
            ok &= res.status == case["expect_status"]
        if case.get("expect_tool_error"):
            ok &= any(t["is_error"] for t in res.tool_calls)
        if "must_not_contain" in case:
            ok &= not any(s.lower() in res.answer.lower() for s in case["must_not_contain"])
        row["security_ok"] = bool(ok)
    return row


def summarize(rows: list[dict[str, Any]], thresholds: dict[str, float]) -> dict[str, Any]:
    def mean(key: str) -> float:
        vals = [float(r[key]) for r in rows if key in r]
        return float(np.mean(vals)) if vals else 1.0

    metrics = {
        "tool_selection_f1": mean("tool_f1"),
        "answer_correctness": mean("correct"),
        "retrieval_hit_rate": mean("retrieval_hit"),
        "numeric_grounding": mean("grounding"),
        "security_pass_rate": mean("security_ok"),
        "must_contain_rate": mean("must_contain_ok"),
        "p95_latency_ms": float(np.percentile([r["latency_ms"] for r in rows], 95)),
        "mean_cost_usd": mean("cost_usd"),
    }
    lower_is_better = {"p95_latency_ms", "mean_cost_usd"}
    failures = [
        f"{k}={metrics[k]:.4f} (threshold {t})"
        for k, t in thresholds.items()
        if (metrics[k] > t if k in lower_is_better else metrics[k] < t)
    ]
    by_cat: dict[str, list[float]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r["tool_f1"])
    return {
        "cases": len(rows),
        "metrics": {k: round(v, 4) for k, v in metrics.items()},
        "tool_f1_by_category": {k: round(float(np.mean(v)), 3) for k, v in by_cat.items()},
        "failures": failures,
        "gate_passed": not failures,
    }


def run(system: System, out_path: str | Path | None = None) -> dict[str, Any]:
    rows = [score_case(system, c) for c in load_cases()]
    report = {"summary": summarize(rows, load_thresholds()), "rows": rows,
              "data_version": system.forecasts.data_version}
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(report, indent=2, default=str))
    return report


def to_ragas_rows(system: System) -> list[dict[str, Any]]:
    """Export policy cases as {question, answer, contexts, ground_truth} for RAGAS/DeepEval."""
    out = []
    for c in load_cases():
        if c["category"] != "policy":
            continue
        res = system.copilot.ask(c["question"], session_id=f"ragas-{c['id']}")
        hits = system.index.search(c["question"], k=3)
        out.append({"question": c["question"], "answer": res.answer, "contexts": [h.chunk.text for h in hits],
                    "ground_truth": "; ".join(c.get("must_contain", []))})
    return out
