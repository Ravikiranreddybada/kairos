"""Zero-shot time-series foundation models as one more *candidate*, not a shortcut.

Pretrained forecasters (Chronos-Bolt, TimesFM, Moirai, ...) forecast a series
they have never seen. They are strong on short or new histories and weak on
retail drivers they cannot see (promotions, price, festivals). So Kairos does
not trust them by default: the adapter is a ``Forecaster`` like any other, it
runs through the same rolling-origin backtest, per-segment selection,
conformal calibration and champion/challenger gates (with the Diebold-Mariano
test). It ships only where it wins, on data – ADR-0018.

Inputs are uncensored demand (stockout days filled, ADR-0004), so the
foundation model never learns a stockout as "low demand".

Enable with ``KAIROS_FOUNDATION_MODEL=chronos`` after
``pip install -e '.[foundation]'``. Tests inject a ``predictor`` so CI never
downloads weights.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache

import numpy as np
import pandas as pd

from kairos.forecasting.features import KEYS
from kairos.forecasting.models import OUT_COLS, _demand_series, _future_dates

# contexts (one 1-D array per series), horizon -> median forecasts, shape (n_series, horizon)
Predictor = Callable[[list[np.ndarray], int], np.ndarray]


@cache  # one weight load per process, not one per backtest fold
def chronos_predictor(model_id: str, context_days: int = 512) -> Predictor:
    """Load a Chronos(-Bolt) pipeline lazily; import errors surface only when enabled."""
    import torch
    from chronos import BaseChronosPipeline

    pipe = BaseChronosPipeline.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32)

    def predict(contexts: list[np.ndarray], h: int) -> np.ndarray:
        ctx = [torch.tensor(c[-context_days:], dtype=torch.float32) for c in contexts]
        quantiles, _ = pipe.predict_quantiles(ctx, prediction_length=h, quantile_levels=[0.5])
        return np.asarray(quantiles[..., 0], dtype=float)

    return predict


class FoundationForecaster:
    def __init__(self, name: str = "chronos", model_id: str = "amazon/chronos-bolt-small",
                 predictor: Predictor | None = None, batch_size: int = 64) -> None:
        self.name = name
        self.model_id = model_id
        self._predictor = predictor
        self.batch_size = batch_size

    def fit(self, history: pd.DataFrame, skus: pd.DataFrame) -> FoundationForecaster:
        if self._predictor is None:
            self._predictor = chronos_predictor(self.model_id)
        return self  # zero-shot: nothing to train

    def predict(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
        if self._predictor is None:
            raise RuntimeError("fit() first")
        groups = list(history.groupby(KEYS, sort=False))
        h = int(future.groupby(KEYS).size().max())
        contexts = [_demand_series(g) for _, g in groups]
        preds = []
        for i in range(0, len(contexts), self.batch_size):
            preds.append(np.asarray(self._predictor(contexts[i : i + self.batch_size], h), dtype=float))
        fc = np.clip(np.concatenate(preds, axis=0), 0, None) if preds else np.empty((0, h))
        out = []
        for ((store, sku), _), row in zip(groups, fc, strict=True):
            dates = _future_dates(future, store, sku)
            out.append(pd.DataFrame({"date": dates.to_numpy(), "store_id": store, "sku_id": sku,
                                     "yhat": row[: len(dates)]}))
        return pd.concat(out, ignore_index=True)[OUT_COLS]
