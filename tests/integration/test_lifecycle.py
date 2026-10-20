"""Model lifecycle: what planners are served must always match the champion the registry names."""

import pytest

pytestmark = pytest.mark.slow


def _served_run(system) -> set[str]:
    return set(system.wh.query("SELECT DISTINCT run_id FROM fact_forecast").run_id)


def test_rollback_serves_the_previous_champions_forecasts(trained, settings):
    from kairos.forecasting.pipeline import publish_run, rollback, train

    system, first = trained
    challenger = train(system.wh, settings, promote=False)
    system.forecasts.registry.promote(challenger.run_id, reason="manual override in test")
    publish_run(system.wh, system.forecasts.registry, challenger.run_id)
    assert _served_run(system) == {challenger.run_id}

    restored = rollback(system.wh, settings)

    assert restored == first.run_id
    assert system.forecasts.data_version == first.run_id
    assert _served_run(system) == {first.run_id}
    assert system.forecasts.forecast("S01", "SKU002", 7)["run_id"] == first.run_id


def test_model_serves_with_the_features_it_was_trained_on(system):
    import json

    from kairos.forecasting.service import ForecastService

    run_dir = system.forecasts.registry.run_dir(system.forecasts.data_version)
    meta = json.loads((run_dir / "lightgbm_meta.json").read_text())
    assert meta["features"] and "is_intermittent" not in meta["features"]

    # A champion trained by an older code version with a feature this code no longer builds:
    stale = {**meta, "features": [*meta["features"], "legacy_feature"]}
    (run_dir / "lightgbm_meta.json").write_text(json.dumps(stale))
    try:
        svc = ForecastService(system.wh, system.settings)
        with pytest.raises(Exception, match="retrain"):
            svc.what_if_promo("S01", "SKU002", None, 7)
    finally:
        (run_dir / "lightgbm_meta.json").write_text(json.dumps(meta))


def test_unservable_champion_does_not_block_a_retrain(trained, settings):
    import json

    from kairos.forecasting.pipeline import rollback, train

    system, first = trained
    meta_path = system.forecasts.registry.run_dir(first.run_id) / "lightgbm_meta.json"
    meta = json.loads(meta_path.read_text())
    meta_path.write_text(json.dumps({**meta, "features": [*meta["features"], "legacy_feature"]}))
    try:
        fresh = train(system.wh, settings)
        assert fresh.promoted, fresh.gates
        assert any(g["name"] == "beats_champion" and "unservable" in g["detail"] for g in fresh.gates)
    finally:
        meta_path.write_text(json.dumps(meta))
        if system.forecasts.registry.champion() != first.run_id:
            rollback(system.wh, settings)
    assert system.forecasts.data_version == first.run_id
