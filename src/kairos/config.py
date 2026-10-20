"""Typed runtime configuration.

All settings come from env vars prefixed ``KAIROS_`` (or a ``.env`` file).
Nothing else in the codebase reads ``os.environ`` directly; this keeps
configuration auditable and testable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KAIROS_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    data_dir: Path = Path("var")

    # --- Data ---------------------------------------------------------------
    n_stores: int = 4
    n_skus: int = 12
    history_days: int = 730
    seed: int = 7

    # --- Forecasting --------------------------------------------------------
    horizon_days: int = 28
    backtest_folds: int = 3
    interval_alpha: float = Field(0.2, description="1-alpha = nominal interval coverage")
    promotion_min_improvement: float = Field(
        0.02, description="challenger must beat champion WAPE by this fraction to be promoted"
    )
    foundation_model: Literal["none", "chronos"] = Field(
        "none", description="add a pretrained zero-shot forecaster as a backtest candidate (ADR-0018)")
    foundation_model_id: str = "amazon/chronos-bolt-small"

    # --- Decisions ----------------------------------------------------------
    simulation_paths: int = Field(2000, ge=200, le=20000, description="Monte-Carlo paths per stress test")
    dc_to_store_days: float = Field(2.0, gt=0, le=14, description="DC -> store transfer lead time")

    # --- LLM ----------------------------------------------------------------
    llm_provider: Literal["fake", "anthropic"] = "fake"
    anthropic_api_key: str | None = None
    llm_fast_model: str = "claude-haiku-5-5"
    llm_strong_model: str = "claude-opus-5-5"
    llm_fast_effort: Literal["low", "medium", "high"] = "low"
    llm_strong_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 3
    # USD per 1M tokens (input, output). Override per deployment; used for cost accounting.
    llm_price_fast: tuple[float, float] = (0.10, 0.50)
    llm_price_strong: tuple[float, float] = (4.0, 20.0)

    # --- Agent --------------------------------------------------------------
    agent_max_steps: int = 6
    agent_token_budget: int = 40_000
    semantic_cache_threshold: float = 0.92
    sql_timeout_s: float = Field(5.0, description="wall-clock cap for one LLM-written SQL query")

    # --- API ----------------------------------------------------------------
    api_keys: list[str] = Field(default_factory=lambda: ["dev-key"])
    # Retrain / rollback change what every planner sees: separate, smaller key set.
    admin_api_keys: list[str] = Field(default_factory=lambda: ["dev-admin-key"])
    # May approve/reject purchase-order proposals (four-eyes: never the proposer's own).
    approver_api_keys: list[str] = Field(default_factory=lambda: ["dev-approver-key"])
    rate_limit_per_min: int = 120

    @model_validator(mode="after")
    def _no_dev_keys_in_prod(self) -> Settings:
        dev = {"dev-key", "dev-admin-key", "dev-approver-key"}
        used = dev & {*self.api_keys, *self.admin_api_keys, *self.approver_api_keys}
        if self.env == "prod" and used:
            raise ValueError(f"dev API keys not allowed when KAIROS_ENV=prod: {sorted(used)}")
        return self

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse.duckdb"

    @property
    def registry_dir(self) -> Path:
        return self.data_dir / "registry"

    @property
    def memory_path(self) -> Path:
        return self.data_dir / "memory.sqlite"

    @property
    def decisions_path(self) -> Path:
        return self.data_dir / "decisions.sqlite"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
