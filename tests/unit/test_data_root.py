"""The environment selects a data directory, explicit base selects a project."""
from pathlib import Path

import pytest
from pipeline import paths

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('value', [None, '', '   ', '/tmp/example', 'relative', '~/dashbite'])
def test_resolution(value, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, 'PROJECT_ROOT', tmp_path / 'project')
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    if value is None:
        monkeypatch.delenv('DATA_ROOT', raising=False)
    else:
        monkeypatch.setenv('DATA_ROOT', value)
    monkeypatch.chdir(tmp_path)
    expected = {None: tmp_path / 'project/data', '': tmp_path / 'project/data',
                '   ': tmp_path / 'project/data', '/tmp/example': Path('/tmp/example'),
                'relative': tmp_path / 'project/relative',
                '~/dashbite': tmp_path / 'home/dashbite'}[value]
    assert paths.data_root() == expected
    assert paths.data_root(tmp_path) == tmp_path / 'data'


def test_all_helpers_and_runtime_changes(monkeypatch, tmp_path):
    for name in ('first', 'second'):
        root = tmp_path / name
        monkeypatch.setenv('DATA_ROOT', str(root))
        for _ in range(2):
            assert paths.ensure_data_dirs() == {s: root / s for s in paths.DATA_SUBDIRS}
        for sub in paths.DATA_SUBDIRS:
            assert getattr(paths, sub + '_dir')() == root / sub
            assert (root / sub).is_dir()
