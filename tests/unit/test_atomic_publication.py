"""Regression checks for incomplete files becoming visible to live readers."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import joblib
import pytest

from pipeline.publication import atomic_output
from pipeline import train, infer


@pytest.mark.unit
def test_failed_publication_preserves_previous_file(tmp_path):
    destination = tmp_path / 'state.json'
    destination.write_text('old complete state')
    with pytest.raises(RuntimeError):
        with atomic_output(destination) as temporary:
            temporary.write_text('partial new state')
            assert destination.read_text() == 'old complete state'
            raise RuntimeError('interrupted write')
    assert destination.read_text() == 'old complete state'
    assert not list(tmp_path.glob('.pending-*'))


@pytest.mark.unit
def test_reader_cannot_discover_partial_checkpoint(tmp_path, monkeypatch):
    original_dump = joblib.dump
    writing, release = Event(), Event()

    def slow_dump(bundle, filename):
        filename.write_bytes(b'partial checkpoint')
        writing.set()
        assert release.wait(5)
        return original_dump(bundle, filename)

    monkeypatch.setattr(train.joblib, 'dump', slow_dump)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(train.write_checkpoint, {'test': 'model'}, {}, tmp_path, '20261001_120000')
        try:
            assert writing.wait(5)
            assert infer.newest_checkpoint(tmp_path) is None
        finally:
            release.set()
        published = future.result(timeout=5)
    assert infer.newest_checkpoint(tmp_path) == published
    assert infer.load_checkpoint(published)['model'] == {'test': 'model'}
    assert (published.parent / 'metrics_20261001_120000.json').exists()
    assert not list(published.parent.glob('.pending-*'))


@pytest.mark.unit
def test_failed_dump_does_not_publish_checkpoint(tmp_path, monkeypatch):
    def broken_dump(bundle, filename):
        filename.write_bytes(b'partial')
        raise OSError('simulated write failure')
    monkeypatch.setattr(train.joblib, 'dump', broken_dump)
    with pytest.raises(OSError, match='simulated'):
        train.write_checkpoint({}, {}, tmp_path, '20261001_120001')
    assert infer.newest_checkpoint(tmp_path) is None
    assert not list((tmp_path / 'data/models').glob('.pending-*'))


@pytest.mark.unit
def test_existing_checkpoint_is_not_overwritten(tmp_path):
    path = train.write_checkpoint({'original': True}, {}, tmp_path, '20261001_120002')
    with pytest.raises(FileExistsError):
        train.write_checkpoint({'replacement': True}, {}, tmp_path, '20261001_120002')
    assert joblib.load(path)['model'] == {'original': True}
