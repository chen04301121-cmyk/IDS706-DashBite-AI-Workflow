"""Inspection must fail for bad handoffs and preserve its original baseline."""
import json

import pandas as pd
import pytest
from scripts import check_artifacts as artifacts, check_persistence as persistence
from tests.integration.test_environment_pipeline import populated_root

pytestmark = pytest.mark.integration


def test_artifacts_and_persistence(populated_root):
    root = populated_root
    assert artifacts.main([]) == 0
    assert persistence.main(['save']) == 0
    baseline = (root / 'smoke-manifest.json').read_bytes()
    assert persistence.main(['verify']) == 0
    assert persistence.main(['save']) == 1
    assert (root / 'smoke-manifest.json').read_bytes() == baseline
    assert artifacts.main(['--new-since', 'smoke-manifest.json']) == 1
    path = next((root / 'raw').glob('*.csv'))
    path.write_text(path.read_text() + '\n')
    assert persistence.main(['verify']) == 1
    path.unlink()
    assert persistence.main(['verify']) == 1


@pytest.mark.parametrize('damage', ['duplicate', 'foreign', 'nan', 'range', 'label', 'checkpoint', 'marker', 'metrics', 'state', 'quality'])
def test_bad_handoffs_fail(populated_root, damage):
    root = populated_root
    path = next((root / 'predictions').glob('*.csv'))
    frame = pd.read_csv(path)
    if damage == 'duplicate': frame.loc[1, 'order_id'] = frame.loc[0, 'order_id']
    if damage == 'foreign': frame.loc[0, 'order_id'] = 'not-a-feature'
    if damage == 'nan': frame.loc[0, 'late_probability'] = float('nan')
    if damage == 'range': frame.loc[0, 'late_probability'] = 1.5
    if damage == 'label': frame.loc[0, 'predicted_late'] = 2
    if damage == 'checkpoint': frame.loc[0, 'checkpoint_id'] = 'missing'
    frame.to_csv(path, index=False)
    if damage == 'marker': next((root / 'features').glob('.done_*')).unlink()
    if damage == 'metrics': next((root / 'models').glob('metrics_*.json')).write_text('{}')
    if damage == 'state': (root / 'models/train_state.json').write_text('{}')
    if damage == 'quality': (root / 'quality/batch_quality.csv').write_text('batch_file,rows_in,rows_out\nx,0,0\n')
    assert artifacts.main([]) == 1


@pytest.mark.parametrize('relative', ['../outside', '/etc/passwd', 'linked/file'])
def test_manifest_escape(tmp_path, relative):
    root = tmp_path / 'data'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'linked').symlink_to(outside, target_is_directory=True)
    (root / 'smoke-manifest.json').write_text(json.dumps({'version': 1, 'files': {relative: '0' * 64}}))
    with pytest.raises(ValueError):
        artifacts.read_manifest(root)


def test_fixed_poll_deadline(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('DATA_ROOT', str(tmp_path))
    clock = [0.0]
    monkeypatch.setattr(artifacts.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(artifacts.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    assert artifacts.main(['--wait', '3']) == 1
    assert clock[0] == 3
    assert 'timed out after 3s' in capsys.readouterr().out


def test_new_predictions(populated_root, monkeypatch):
    from pipeline import simulator, preprocess, train, infer
    from pipeline.config import Config
    persistence.save(populated_root)
    old_manifest = (populated_root / 'smoke-manifest.json').read_bytes()
    batch = pd.read_csv(next((populated_root / 'raw').glob('*.csv')))
    batch['order_id'] = 'new-' + batch.order_id
    simulator.write_batch(batch, populated_root / 'raw', tick=1)
    preprocess.process_new_raw_files()
    original_write = train.write_checkpoint
    monkeypatch.setattr(train, 'write_checkpoint', lambda model, metrics, base=None: original_write(model, metrics, base, stamp='20990101_000000'))
    train.maybe_train(Config(train_every_n_events=50))
    infer.run_once()
    assert artifacts.main(['--new-since', 'smoke-manifest.json']) == 0
    assert (populated_root / 'smoke-manifest.json').read_bytes() == old_manifest


@pytest.mark.parametrize('point,diagnostic', [
    ('features', 'feature snapshot rows=50'),
    ('checkpoint', 'not in checkpoint snapshot'),
])
def test_live_training_can_advance_beyond_reader_snapshot(populated_root, monkeypatch, point, diagnostic):
    """Complete valid writes between reads reproduce both state failure branches.

    This does not diagnose a historical run or require a partial/corrupt file.
    """
    from pipeline import simulator, preprocess, train
    from pipeline.config import Config
    advanced = False

    def advance():
        nonlocal advanced
        if advanced:
            return
        advanced = True
        batch = pd.read_csv(next((populated_root / 'raw').glob('*.csv')))
        batch['order_id'] = 'later-' + batch.order_id
        simulator.write_batch(batch, populated_root / 'raw', tick=1)
        preprocess.process_new_raw_files()
        original = train.write_checkpoint
        with monkeypatch.context() as context:
            context.setattr(train, 'write_checkpoint', lambda model, metrics, base=None:
                            original(model, metrics, base, stamp='20990101_000000'))
            train.maybe_train(Config(train_every_n_events=50))

    if point == 'features':
        original_read = artifacts.read_frames
        def read(*args, **kwargs):
            result = original_read(*args, **kwargs)
            if args[1] == 'features/features_*.csv':
                advance()
            return result
        monkeypatch.setattr(artifacts, 'read_frames', read)
    else:
        original_load = artifacts.joblib.load
        def load(*args, **kwargs):
            result = original_load(*args, **kwargs)
            advance()
            return result
        monkeypatch.setattr(artifacts.joblib, 'load', load)
    with pytest.raises(ValueError, match=diagnostic):
        artifacts.validate(populated_root)
    # Same files pass on the next complete snapshot without repair or deletion.
    artifacts.validate(populated_root)


@pytest.mark.parametrize('count', [True, 0, -1, 51, '50'])
def test_invalid_state_count_diagnostic(populated_root, count, capsys):
    path = populated_root / 'models/train_state.json'
    state = json.loads(path.read_text())
    state['labeled_rows_at_last_train'] = count
    path.write_text(json.dumps(state))
    assert artifacts.main([]) == 1
    assert 'labeled_rows_at_last_train=' in capsys.readouterr().out
