"""Real stage and dashboard handoffs with environment-only configuration."""
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pipeline import paths, simulator, preprocess, train, infer
from pipeline.config import Config
from pipeline.dashboard import app

pytestmark = pytest.mark.integration


@pytest.fixture
def populated_root(monkeypatch, tmp_path):
    root = tmp_path / 'shared'
    monkeypatch.setenv('DATA_ROOT', str(root))
    monkeypatch.setattr(paths, 'PROJECT_ROOT', tmp_path / 'sentinel')
    batch = simulator.generate_batch(50, seed=123)
    batch['order_id'] = [f'order-{i}' for i in range(len(batch))]
    batch['was_late'] = [i % 2 for i in range(len(batch))]
    monkeypatch.setattr(simulator, 'generate_batch', lambda *a, **kw: batch.copy())
    cfg = Config(batch_size=50, train_every_n_events=50, corrupt_batch_rate=0)
    raw = simulator.run_once(cfg)
    features = preprocess.process_new_raw_files()
    checkpoint = train.maybe_train(cfg)
    prediction = infer.run_once(cfg)
    assert all(p.is_relative_to(root) for p in [raw, *features, checkpoint, prediction])
    assert not (tmp_path / 'sentinel').exists()
    return root


def test_environment_handoff_and_dashboard(populated_root, monkeypatch):
    features = app.load_features()
    predictions = app.load_predictions()
    quality = app.load_quality_log()
    assert len(features) == len(predictions) == 50
    assert set(features.order_id) == set(predictions.order_id)
    assert {'hour', 'is_peak'} <= set(features.columns)
    assert quality.rows_out.sum() == 50
    assert preprocess.process_new_raw_files() == []
    assert train.maybe_train(Config(train_every_n_events=50)) is None
    assert infer.run_once() is None
    # Execute main once with actual loaders; avoid the deliberate refresh loop.
    ui = MagicMock()
    ui.sidebar.checkbox.return_value = False
    ui.fragment.side_effect = lambda **kwargs: lambda render: render
    ui.columns.return_value = [MagicMock() for _ in range(3)]
    monkeypatch.setattr(app, 'st', ui)
    app.main()
    ui.columns.return_value[0].metric.assert_called_once_with('Samples scored', '50')
    assert ui.altair_chart.call_count == 2
    # Loader explicit-base precedence remains intact in an environment-root run.
    assert app.load_features(populated_root / 'other-project').empty
