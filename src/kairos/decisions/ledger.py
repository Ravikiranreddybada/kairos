"""Decision ledger: the copilot recommends, a human decides, the system learns.

Three ideas, kept deliberately small:

1. **Staged work product, human sign-off.** A purchase-order proposal freezes
   the policy recommendation (model run id, inputs, quantity). A *different*
   person approves or rejects it, optionally overriding the quantity with a
   reason (four-eyes rule: the proposer cannot approve their own proposal).
   The agent's tools never write here (CLAUDE.md invariant 4); only
   authenticated humans do, through the API.

2. **Tamper-evident audit trail.** Every event is appended to a hash chain:
   ``hash = sha256(prev_hash + canonical_json(event))``. ``verify_chain``
   recomputes it, so an edited or deleted row is detected.

3. **Lessons that refine, not overwrite.** When the realised demand for a
   decision is recorded, we compute the hindsight-ideal order and score both
   the model's and the planner's quantity against it. Lessons are recomputed
   from all evidence on every read: each carries its evidence count, the
   decision ids behind it and a confidence label, so a new outcome strengthens
   or weakens a belief instead of replacing it. This is forecast value-add
   (FVA) at the decision level: does the human override actually help?
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


class LedgerError(ValueError):
    """Invalid state transition (unknown id, already decided, self-approval...)."""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _confidence(n: int) -> str:
    return "high" if n >= 8 else "medium" if n >= 3 else "low"


class DecisionLedger:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._con.executescript(
                """
                CREATE TABLE IF NOT EXISTS proposals(
                    id TEXT PRIMARY KEY, created_at REAL, store_id TEXT, sku_id TEXT, run_id TEXT,
                    proposed_by TEXT, recommended_qty REAL, snapshot TEXT, status TEXT,
                    final_qty REAL, decided_by TEXT, reason TEXT, decided_at REAL,
                    actual_demand REAL, outcome_at REAL);
                CREATE INDEX IF NOT EXISTS ix_prop ON proposals(store_id, sku_id, created_at);
                CREATE TABLE IF NOT EXISTS audit(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, proposal_id TEXT, action TEXT,
                    actor TEXT, data TEXT, prev_hash TEXT, hash TEXT);
                """
            )

    # ------------------------------------------------------------- audit chain
    def _append(self, proposal_id: str, action: str, actor: str, data: dict[str, Any]) -> None:
        """Caller holds the lock and commits."""
        row = self._con.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        ts = time.time()
        event = {"ts": ts, "proposal_id": proposal_id, "action": action, "actor": actor, "data": data}
        h = hashlib.sha256((prev + _canon(event)).encode()).hexdigest()
        self._con.execute("INSERT INTO audit(ts, proposal_id, action, actor, data, prev_hash, hash) "
                          "VALUES (?,?,?,?,?,?,?)", (ts, proposal_id, action, actor, _canon(data), prev, h))

    def verify_chain(self) -> dict[str, Any]:
        with self._lock:
            rows = self._con.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        prev = GENESIS
        for r in rows:
            event = {"ts": r["ts"], "proposal_id": r["proposal_id"], "action": r["action"], "actor": r["actor"],
                     "data": json.loads(r["data"])}
            expect = hashlib.sha256((prev + _canon(event)).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != expect:
                return {"ok": False, "entries": len(rows), "broken_at_seq": r["seq"]}
            prev = r["hash"]
        return {"ok": True, "entries": len(rows), "head": prev}

    def audit_log(self, proposal_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._con.execute("SELECT seq, ts, action, actor, data, hash FROM audit WHERE proposal_id=? "
                                     "ORDER BY seq", (proposal_id,)).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    # ----------------------------------------------------------- transitions
    def propose(self, snapshot: dict[str, Any], actor: str) -> dict[str, Any]:
        """Freeze a policy recommendation (output of ``ForecastService.inventory_policy``)."""
        d = snapshot["decision"]
        pid = f"PO-{uuid.uuid4().hex[:10]}"
        with self._lock:
            self._con.execute(
                "INSERT INTO proposals(id, created_at, store_id, sku_id, run_id, proposed_by, recommended_qty, "
                "snapshot, status) VALUES (?,?,?,?,?,?,?,?, 'pending')",
                (pid, time.time(), d["store_id"], d["sku_id"], snapshot.get("run_id"), actor,
                 float(d["order_qty"]), _canon(snapshot)))
            self._append(pid, "proposed", actor, {"recommended_qty": d["order_qty"], "run_id": snapshot.get("run_id")})
            self._con.commit()
        return self.get(pid)

    def decide(self, proposal_id: str, approve: bool, actor: str, qty: float | None = None,
               reason: str | None = None) -> dict[str, Any]:
        with self._lock:
            p = self._row(proposal_id)
            if p["status"] != "pending":
                raise LedgerError(f"{proposal_id} is already {p['status']}")
            if p["proposed_by"] == actor:
                raise LedgerError("four-eyes rule: the proposer cannot approve or reject their own proposal")
            final = (float(qty) if qty is not None else float(p["recommended_qty"])) if approve else 0.0
            if approve and qty is not None and float(qty) != float(p["recommended_qty"]) and not reason:
                raise LedgerError("an override quantity needs a reason")
            status = "approved" if approve else "rejected"
            self._con.execute("UPDATE proposals SET status=?, final_qty=?, decided_by=?, reason=?, decided_at=? "
                              "WHERE id=?", (status, final, actor, reason, time.time(), proposal_id))
            self._append(proposal_id, status, actor, {"final_qty": final, "reason": reason})
            self._con.commit()
        return self.get(proposal_id)

    def record_outcome(self, proposal_id: str, actual_demand: float, actor: str) -> dict[str, Any]:
        """Realised demand over the decision's coverage window (lead time + review period)."""
        if actual_demand < 0:
            raise LedgerError("actual_demand must be >= 0")
        with self._lock:
            p = self._row(proposal_id)
            if p["status"] != "approved":
                raise LedgerError("outcomes can only be recorded for approved proposals")
            if p["actual_demand"] is not None:
                raise LedgerError(f"{proposal_id} already has an outcome")
            self._con.execute("UPDATE proposals SET actual_demand=?, outcome_at=? WHERE id=?",
                              (float(actual_demand), time.time(), proposal_id))
            self._append(proposal_id, "outcome", actor, {"actual_demand": actual_demand})
            self._con.commit()
        return self.get(proposal_id)

    # ----------------------------------------------------------------- reads
    def _row(self, proposal_id: str) -> sqlite3.Row:
        r = self._con.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if r is None:
            raise LedgerError(f"unknown proposal {proposal_id}")
        return r

    @staticmethod
    def _public(r: sqlite3.Row) -> dict[str, Any]:
        out = dict(r)
        snap = json.loads(out.pop("snapshot"))
        d = snap["decision"]
        out["recommendation"] = {k: d.get(k) for k in ("reorder_point", "safety_stock", "inventory_position",
                                                       "stockout_probability", "service_level", "rationale")}
        out.update(_hindsight(out, d))
        return out

    def get(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            return self._public(self._row(proposal_id))

    def find(self, store_id: str | None = None, sku_id: str | None = None, status: str | None = None,
             limit: int = 20) -> list[dict[str, Any]]:
        where, params = [], []
        for col, v in (("store_id", store_id), ("sku_id", sku_id), ("status", status)):
            if v:
                where.append(f"{col}=?")
                params.append(v)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._lock:
            rows = self._con.execute(f"SELECT * FROM proposals {clause} ORDER BY created_at DESC LIMIT ?",
                                     [*params, limit]).fetchall()
        return [self._public(r) for r in rows]

    def lessons(self, store_id: str | None = None, sku_id: str | None = None) -> list[dict[str, Any]]:
        """Evidence-backed observations per store/SKU, recomputed from every decision."""
        decided = [p for p in self.find(store_id, sku_id, limit=10_000) if p["status"] == "approved"]
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for p in decided:
            groups.setdefault((p["store_id"], p["sku_id"]), []).append(p)
        out = []
        for (store, sku), ps in sorted(groups.items()):
            overrides = [p for p in ps if p["final_qty"] != p["recommended_qty"]]
            pcts = [100 * (p["final_qty"] / p["recommended_qty"] - 1) for p in overrides if p["recommended_qty"]]
            scored = [p for p in ps if p.get("model_error") is not None]
            model_err = sum(p["model_error"] for p in scored)
            planner_err = sum(p["planner_error"] for p in scored)
            fva = round(100 * (model_err - planner_err) / model_err, 1) if scored and model_err > 0 else None
            ups = sum(1 for x in pcts if x > 0)
            direction = ("raise" if ups > len(pcts) / 2 else "cut") if pcts else None
            mean_pct = round(sum(pcts) / len(pcts), 1) if pcts else 0.0
            text = f"{store}/{sku}: {len(overrides)} of {len(ps)} approved orders were overridden"
            if pcts:
                text += f" (planners usually {direction} the quantity, mean {mean_pct:+}%)"
            if fva is not None:
                verdict = "improved" if fva > 0 else "worsened" if fva < 0 else "did not change"
                text += f"; on {len(scored)} realised outcomes the final orders {verdict} order error by {abs(fva)}%"
            out.append({
                "store_id": store, "sku_id": sku, "decisions": len(ps), "overrides": len(overrides),
                "mean_override_pct": mean_pct, "override_direction": direction, "outcomes": len(scored),
                "override_value_add_pct": fva, "confidence": _confidence(len(scored) or len(ps)),
                "evidence": [p["id"] for p in ps][:10], "observation": text + ".",
            })
        return out

    def close(self) -> None:
        self._con.close()


def _hindsight(p: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    """Ideal order in hindsight = realised demand + safety stock - inventory position (>= 0)."""
    if p.get("actual_demand") is None or p.get("status") != "approved":
        return {"hindsight_ideal_qty": None, "model_error": None, "planner_error": None}
    ideal = max(0.0, float(p["actual_demand"]) + float(d["safety_stock"]) - float(d["inventory_position"]))
    return {"hindsight_ideal_qty": round(ideal, 1),
            "model_error": round(abs(float(p["recommended_qty"]) - ideal), 1),
            "planner_error": round(abs(float(p["final_qty"]) - ideal), 1)}
