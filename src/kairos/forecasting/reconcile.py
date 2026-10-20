"""Hierarchical forecast reconciliation.

Planners look at total -> store -> store x SKU. Independently forecast
levels do not add up, which destroys trust ("the store number doesn't match
the sum of its SKUs"). Reconciliation projects base forecasts onto the
coherent subspace:

    y_tilde = S (S' W^-1 S)^-1 S' W^-1 y_hat

``S`` is the summing matrix. ``W`` choices:
* identity        -> OLS
* diag(S @ 1)     -> WLS-structural (weights by number of children; robust default)

Bottom-up is the special case that ignores upper-level information.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


def summing_matrix(bottom: list[tuple[str, str]]) -> tuple[np.ndarray, list[str]]:
    """Rows: total, each store, each (store, sku). Columns: bottom series."""
    stores = sorted({s for s, _ in bottom})
    labels = ["total", *[f"store:{s}" for s in stores], *[f"{s}|{k}" for s, k in bottom]]
    n_b = len(bottom)
    rows = [np.ones(n_b)]
    for s in stores:
        rows.append(np.array([1.0 if b[0] == s else 0.0 for b in bottom]))
    rows.extend(np.eye(n_b))
    return np.vstack(rows), labels


def reconcile(
    base: np.ndarray, S: np.ndarray, method: Literal["ols", "wls_struct", "bottom_up"] = "wls_struct"
) -> np.ndarray:
    """``base``: (n_nodes, H) base forecasts for every node. Returns coherent (n_nodes, H)."""
    n_b = S.shape[1]
    if method == "bottom_up":
        return S @ base[-n_b:]
    w = np.ones(S.shape[0]) if method == "ols" else S.sum(axis=1)
    winv = np.diag(1.0 / w)
    P = np.linalg.solve(S.T @ winv @ S, S.T @ winv)  # (n_b, n_nodes)
    return S @ (P @ base)


def reconcile_frame(
    bottom_fc: pd.DataFrame, upper_fc: pd.DataFrame, method: Literal["ols", "wls_struct", "bottom_up"] = "wls_struct"
) -> pd.DataFrame:
    """Reconcile long-format forecasts.

    ``bottom_fc``: date, store_id, sku_id, yhat. ``upper_fc``: date, node, yhat
    with node in {"total", "store:<id>"}. Returns date, node, yhat for all nodes.
    """
    wide_b = bottom_fc.pivot_table(index=["store_id", "sku_id"], columns="date", values="yhat")
    bottom = [(str(s), str(k)) for s, k in wide_b.index]
    S, labels = summing_matrix(bottom)
    wide_u = upper_fc.pivot_table(index="node", columns="date", values="yhat").reindex(columns=wide_b.columns)
    n_upper = S.shape[0] - len(bottom)
    upper_labels = labels[:n_upper]
    if method != "bottom_up" and set(upper_labels) - set(wide_u.index):
        raise ValueError("upper forecasts missing nodes; use bottom_up")
    upper = wide_u.reindex(upper_labels).to_numpy() if method != "bottom_up" else np.zeros((n_upper, wide_b.shape[1]))
    base = np.vstack([upper, wide_b.to_numpy()])
    coherent = np.clip(reconcile(base, S, method), 0, None)
    out = pd.DataFrame(coherent, index=labels, columns=wide_b.columns)
    long = out.reset_index(names="node").melt(id_vars="node", var_name="date", value_name="yhat")
    long["date"] = pd.to_datetime(long["date"])
    return long
