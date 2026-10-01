"""Slow commands and dirty exits must fail even when Compose reports success."""
import json
from types import SimpleNamespace

import pytest
from tests import docker_verify as gate

pytestmark = pytest.mark.unit


def events(container, duration=0.5):
    return [
        {'Actor': {'ID': container, 'Attributes': {'signal': '15'}},
         'Action': 'kill', 'timeNano': 1_000_000_000},
        {'Actor': {'ID': container}, 'Action': 'die',
         'timeNano': int((1 + duration) * 1e9)},
    ]


@pytest.mark.parametrize('wall,exit_code,oom,daemon,returncode,passes', [
    (1, 0, False, 0.5, 0, True),
    (12.93, 0, False, 0.5, 0, False),
    (1, 137, False, 0.5, 0, False),
    (1, 0, True, 0.5, 0, False),
    (1, 0, False, 10.1, 0, False),
    (1, 0, False, 0.5, 1, False),
])
def test_stop_evidence_and_criteria(monkeypatch, capsys, wall, exit_code, oom, daemon, returncode, passes):
    containers = [{'Id': name, 'Config': {'Labels': {'com.docker.compose.service': name}},
                   'State': {'Status': 'exited', 'ExitCode': exit_code if name == 'train' else 0,
                             'OOMKilled': oom, 'FinishedAt': 'timestamp'}}
                  for name in ('train', 'infer')]
    def compose(*args, **kwargs):
        return SimpleNamespace(returncode=returncode if args[0] == 'stop' else 0,
                               stdout='Compose progress' if args[0] == 'stop' else 'train infer')
    def run(command, **kwargs):
        if command[1] == 'inspect':
            value = json.dumps(containers)
        elif command[1] == 'events':
            assert int(command[command.index('--since') + 1]) < 1790812800
            assert int(command[command.index('--until') + 1]) > 1790812800
            value = '\n'.join(json.dumps(e) for name in ('train', 'infer') for e in events(name, daemon))
        else:
            value = '2026-10-01T00:00:00Z'
        return SimpleNamespace(returncode=0, stdout=value)
    ticks = iter([0, wall])
    monkeypatch.setattr(gate.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(gate, 'compose', compose)
    monkeypatch.setattr(gate, 'run', run)
    if passes:
        gate.stop_and_check('train', 'infer')
    else:
        with pytest.raises(AssertionError):
            gate.stop_and_check('train', 'infer')
    output = capsys.readouterr().out
    assert 'Shutdown train: status=exited' in output
    assert 'Shutdown infer: status=exited' in output
    assert f'exit={exit_code}' in output
    assert f'wall_seconds={wall:.3f}' in output
    assert 'Compose progress' in output


def test_events_are_per_container_and_required():
    assert gate.shutdown_event_seconds(events('other', 20) + events('train'), 'train') == 0.5
    with pytest.raises(AssertionError, match='missing SIGTERM/die'):
        gate.shutdown_event_seconds(events('other'), 'train')


def test_event_query_failure_keeps_exit_status_visible(monkeypatch, capsys):
    container = {'Id': 'train', 'Config': {'Labels': {'com.docker.compose.service': 'train'}},
                 'State': {'Status': 'exited', 'ExitCode': 137, 'OOMKilled': False,
                           'FinishedAt': 'timestamp'}}
    def run(command, **kwargs):
        if command[1] == 'events':
            raise RuntimeError('daemon event query failed')
        return SimpleNamespace(stdout=json.dumps([container]) if command[1] == 'inspect' else '2026-10-01T00:00:00Z')
    monkeypatch.setattr(gate, 'run', run)
    monkeypatch.setattr(gate, 'compose', lambda *args, **kwargs:
                        SimpleNamespace(stdout='train', returncode=0))
    with pytest.raises(RuntimeError, match='event query failed'):
        gate.stop_and_check('train')
    assert 'exit=137, OOMKilled=False' in capsys.readouterr().out


@pytest.mark.parametrize('response', ['', '\n', 'yes\n'])
def test_browser_gate_requires_explicit_observation(monkeypatch, response):
    from io import StringIO
    monkeypatch.setitem(gate.ENV, 'DASHBOARD_PORT', '8501')
    monkeypatch.setattr(gate.sys, 'stdin', StringIO(response))
    monkeypatch.setattr(gate.select, 'select', lambda *args: ([gate.sys.stdin], [], []))
    with pytest.raises(RuntimeError, match='NOT VERIFIED'):
        gate.browser_checkpoint()


def test_browser_gate_times_out(monkeypatch):
    monkeypatch.setitem(gate.ENV, 'DASHBOARD_PORT', '8501')
    monkeypatch.setattr(gate.select, 'select', lambda *args: ([], [], []))
    with pytest.raises(RuntimeError, match='timed out'):
        gate.browser_checkpoint()
