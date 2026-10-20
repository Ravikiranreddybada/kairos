from __future__ import annotations

import logging

import pytest

from kairos.bootstrap import System, build, seed
from kairos.config import Settings
from kairos.data.synthetic import SyntheticDataset, generate
from kairos.forecasting.pipeline import TrainResult, train

logging.disable(logging.INFO)


@pytest.fixture(scope="session")
def dataset() -> SyntheticDataset:
    return generate(n_stores=2, n_skus=6, days=540, seed=11)


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    return Settings(env="test", data_dir=tmp_path_factory.mktemp("kairos"), n_stores=2, n_skus=6,
                    history_days=540, seed=11, backtest_folds=2, api_keys=["test-key"], rate_limit_per_min=1000)


@pytest.fixture(scope="session")
def trained(settings: Settings) -> tuple[System, TrainResult]:
    wh = seed(settings)
    result = train(wh, settings)
    return build(settings, wh=wh), result


@pytest.fixture(scope="session")
def system(trained: tuple[System, TrainResult]) -> System:
    return trained[0]
