"""File-based model registry with champion/challenger promotion gates.

Layout::

    registry/
      champion.json                 -> {"run_id": ..., "promoted_at": ...}
      runs/<run_id>/
        manifest.json               -> spec, metrics, gates, data fingerprint, versions
        lightgbm.txt                -> booster (if used)
        calibrator.json             -> conformal quantiles + scales
        quality.json                -> data contract report for the training set

Every forecast row carries ``run_id``, so any number shown to a planner can be
traced to the exact data, code version and metrics that produced it.

The interface (``save_run`` / ``load_manifest`` / ``champion``) is the seam for
MLflow or SageMaker Model Registry (ADR-0008). If ``mlflow`` is installed and
``MLFLOW_TRACKING_URI`` is set, runs are mirrored there too.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kairos.observability import get_logger

log = get_logger(__name__)


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


class Registry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.root / "runs" / run_id

    def new_run_id(self) -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")

    def save_run(self, run_id: str, manifest: dict[str, Any], files: dict[str, str | bytes]) -> Path:
        d = self.run_dir(run_id)
        tmp = d.with_suffix(".tmp")
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        manifest = {
            **manifest,
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "python": platform.python_version(),
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        for name, content in files.items():
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(tmp / name, mode) as fh:
                fh.write(content)
        tmp.rename(d)  # atomic publish: readers never see a half-written run
        self._mirror_mlflow(manifest)
        return d

    def load_manifest(self, run_id: str) -> dict[str, Any]:
        return json.loads((self.run_dir(run_id) / "manifest.json").read_text())

    def read_file(self, run_id: str, name: str) -> str:
        return (self.run_dir(run_id) / name).read_text()

    def champion(self) -> str | None:
        p = self.root / "champion.json"
        return json.loads(p.read_text())["run_id"] if p.exists() else None

    def promote(self, run_id: str, reason: str) -> None:
        p = self.root / "champion.json"
        history = json.loads(p.read_text()).get("history", []) if p.exists() else []
        prev = self.champion()
        if prev:
            history.append({"run_id": prev, "replaced_at": datetime.now(UTC).isoformat()})
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"run_id": run_id, "promoted_at": datetime.now(UTC).isoformat(),
                                   "reason": reason, "history": history[-20:]}, indent=2))
        tmp.replace(p)
        log.info("promoted run", fields={"run_id": run_id, "previous": prev, "reason": reason})

    def rollback(self) -> str:
        p = self.root / "champion.json"
        data = json.loads(p.read_text())
        if not data.get("history"):
            raise RuntimeError("no previous champion to roll back to")
        prev = data["history"].pop()["run_id"]
        data.update(run_id=prev, promoted_at=datetime.now(UTC).isoformat(), reason="rollback")
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(p)  # same atomic swap as promote()
        return prev

    def list_runs(self) -> list[str]:
        return sorted(p.name for p in (self.root / "runs").iterdir() if p.is_dir())

    @staticmethod
    def _mirror_mlflow(manifest: dict[str, Any]) -> None:
        if not os.environ.get("MLFLOW_TRACKING_URI"):
            return
        try:
            import mlflow
        except ImportError:
            return
        with mlflow.start_run(run_name=manifest["run_id"]):
            mlflow.log_params({k: str(v) for k, v in manifest.get("spec", {}).items()})
            flat = {k: v for k, v in manifest.get("metrics", {}).items() if isinstance(v, int | float)}
            mlflow.log_metrics(flat)


def evaluate_gates(
    challenger: dict[str, float],
    champion: dict[str, float] | None,
    quality_passed: bool,
    nominal_coverage: float,
    min_improvement: float,
    dm_p_value: float | None = None,
    dm_alpha: float = 0.10,
    champion_unservable: str | None = None,
) -> list[GateResult]:
    """Promotion policy. All gates must pass.

    Champion and challenger are scored on the *same* backtest folds, so the
    comparison is apples-to-apples even though the champion was trained earlier.
    With a champion, the gain must also be statistically significant
    (one-sided Diebold-Mariano p-value < ``dm_alpha``), so we do not promote noise.
    """
    gates = [GateResult("data_quality", quality_passed, "training data passed contracts")]
    cov = challenger["coverage_empirical"]
    gates.append(
        GateResult(
            "interval_calibration",
            nominal_coverage - 0.05 <= cov <= nominal_coverage + 0.10,
            f"empirical {cov:.3f} vs nominal {nominal_coverage:.2f}",
        )
    )
    gates.append(GateResult("beats_naive", challenger["mase"] < 1.0, f"MASE {challenger['mase']:.3f} < 1"))
    gates.append(GateResult("bias", abs(challenger["bias"]) < 0.1, f"|bias| {abs(challenger['bias']):.3f} < 0.10"))
    if champion_unservable:
        gates.append(GateResult("beats_champion", True, f"champion unservable: {champion_unservable}"))
    elif champion is None:
        gates.append(GateResult("beats_champion", True, "no champion yet"))
    else:
        target = champion["wape"] * (1 - min_improvement)
        gates.append(
            GateResult(
                "beats_champion",
                challenger["wape"] <= target,
                f"WAPE {challenger['wape']:.4f} <= {target:.4f} (champion {champion['wape']:.4f})",
            )
        )
        p = 1.0 if dm_p_value is None else dm_p_value
        gates.append(GateResult("significant_improvement", p < dm_alpha,
                                f"Diebold-Mariano one-sided p {p:.4f} < {dm_alpha}"))
    return gates
