"""Real termination signals must finish work, wake polling and preserve failures."""
import importlib
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

import pytest
from pipeline.config import Config

pytestmark = pytest.mark.integration
WORKERS = [('simulator', 'run_once'), ('preprocess', 'process_new_raw_files'),
           ('train', 'maybe_train'), ('infer', 'run_once')]


@pytest.mark.parametrize('module_name,work_name', WORKERS)
@pytest.mark.parametrize('termination', [signal.SIGTERM, signal.SIGINT])
def test_signal_during_iteration_finishes_work(module_name, work_name, termination, monkeypatch, tmp_path):
    worker = importlib.import_module('pipeline.' + module_name)
    events = []
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def work(*args, **kwargs):
        events.append('begun')
        signal.raise_signal(termination)
        # A signal must not interrupt the in-progress handoff.
        (tmp_path / 'finished').write_text('complete')
        events.append('completed')

    monkeypatch.setattr(worker, work_name, work)
    started = time.monotonic()
    worker.run_loop(Config(poll_interval_seconds=60), base=tmp_path)
    assert time.monotonic() - started < 2
    assert events == ['begun', 'completed']
    assert (tmp_path / 'finished').read_text() == 'complete'
    assert all(signal.getsignal(sig) == handler for sig, handler in previous.items())


@pytest.mark.parametrize('module_name,work_name', WORKERS)
def test_exception_is_not_hidden(module_name, work_name, monkeypatch, tmp_path):
    worker = importlib.import_module('pipeline.' + module_name)
    previous = signal.getsignal(signal.SIGTERM)

    def fail(*args, **kwargs):
        raise RuntimeError('real worker failure')

    monkeypatch.setattr(worker, work_name, fail)
    with pytest.raises(RuntimeError, match='real worker failure'):
        worker.run_loop(Config(), base=tmp_path)
    assert signal.getsignal(signal.SIGTERM) == previous


@pytest.mark.parametrize('module_name,work_name', WORKERS)
def test_real_process_sigterm_wakes_sixty_second_poll(module_name, work_name, tmp_path):
    # Run the actual stage function once and announce completion before its wait.
    source = f'''
from pipeline import {module_name} as worker
from pipeline.config import Config
original = worker.{work_name}
def observed(*args, **kwargs):
    result = original(*args, **kwargs)
    print("TICK_COMPLETED", flush=True)
    return result
worker.{work_name} = observed
worker.run_loop(Config(poll_interval_seconds=60, corrupt_batch_rate=0))
'''
    env = dict(os.environ, DATA_ROOT=str(tmp_path / 'data'))
    with subprocess.Popen([sys.executable, '-u', '-c', source],
                          cwd=Path(__file__).resolve().parents[2], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + 30
                output = ''
                # Read bytes directly so buffered lines do not bypass select().
                while 'TICK_COMPLETED' not in output:
                    remaining = deadline - time.monotonic()
                    assert remaining > 0 and selector.select(remaining), output
                    chunk = os.read(process.stdout.fileno(), 4096).decode()
                    assert chunk, output
                    output += chunk
            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            tail, _ = process.communicate(timeout=5)
            assert process.returncode == 0, output + tail
            assert time.monotonic() - started < 5
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
