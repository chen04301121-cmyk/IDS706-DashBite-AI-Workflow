"""Explicit Docker gate; not collected by ordinary pytest. Uses only stdlib.

Owns a unique project. Success removes only its disposable resources; failure
stops writers and preserves the volume and diagnostics for investigation.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import select
import subprocess
import sys
import time
import uuid
import urllib.request

REPO = Path(__file__).resolve().parents[1]
SERVICES = {'simulator', 'preprocess', 'train', 'infer', 'dashboard'}
PROJECT = 'dashbite-test-' + uuid.uuid4().hex[:12]
ENV = dict(os.environ, COMPOSE_PROJECT_NAME=PROJECT, DATA_ROOT='/tmp/dashbite-verify-data',
           TRAIN_EVERY_N_EVENTS='50', BATCH_SIZE='50', POLL_INTERVAL_SECONDS='2',
           CORRUPT_BATCH_RATE='0', RANDOM_SEED='42')
# Do not inherit external Compose files/profiles/platform selection.
for key in ('COMPOSE_FILE', 'COMPOSE_PROFILES', 'DOCKER_DEFAULT_PLATFORM'):
    ENV.pop(key, None)
COMPOSE = ['docker', 'compose', '--env-file', os.devnull, '-f', str(REPO / 'docker-compose.yml'), '-p', PROJECT]


def run(command, *, check=True, timeout=180):
    result = subprocess.run(command, cwd=REPO, env=ENV, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{command}:\n{result.stdout}')
    return result


def compose(*args, **kwargs):
    return run(COMPOSE + list(args), **kwargs)


def check_config(config, root):
    assert set(config['services']) == SERVICES
    assert len(config['volumes']) == 1
    assert config['volumes']['dashbite-data']['name'] == PROJECT + '_dashbite-data'
    for name, service in config['services'].items():
        assert service['image'] == PROJECT + ':local'
        assert service.get('platform') is None and not service.get('container_name')
        assert service.get('restart', 'no') == 'no'
        assert service['stop_grace_period'] == '10s'
        env = service['environment']
        assert env['DATA_ROOT'] == root
        for key in ('BATCH_SIZE', 'TRAIN_EVERY_N_EVENTS', 'POLL_INTERVAL_SECONDS', 'CORRUPT_BATCH_RATE', 'RANDOM_SEED'):
            assert str(env[key]) == ENV[key]
        mount, = service['volumes']
        assert mount['type'] == 'volume' and mount['source'] == 'dashbite-data'
        assert mount['target'] == root and bool(mount.get('read_only')) == (name == 'dashboard')
        assert ('healthcheck' in service) == (name == 'dashboard')
        if name != 'dashboard':
            assert service['command'] == ['python', '-m', 'pipeline.' + name]
            assert not service.get('ports')
    dashboard = config['services']['dashboard']
    assert dashboard['command'] == ['streamlit', 'run', 'pipeline/dashboard/app.py', '--server.address', '0.0.0.0', '--server.port', '8501', '--server.headless', 'true']
    port, = dashboard['ports']
    assert port['host_ip'] == '127.0.0.1' and port['target'] == 8501
    assert str(port['published']) == ENV['DASHBOARD_PORT']


def states(expected):
    rows = [json.loads(line) for line in compose('ps', '-a', '--format', 'json').stdout.splitlines() if line.strip()]
    assert {r['Service'] for r in rows} == expected, rows
    assert all(r['State'] == 'running' for r in rows), rows
    return rows


def shutdown_event_seconds(events, container_id):
    """Daemon timestamps only: do not subtract host and VM clocks."""
    relevant = [event for event in events if event.get('Actor', {}).get('ID') == container_id]
    signals = [event['timeNano'] for event in relevant
               if event.get('Action') == 'kill'
               and event.get('Actor', {}).get('Attributes', {}).get('signal') in ('15', 'SIGTERM')]
    deaths = [event['timeNano'] for event in relevant if event.get('Action') == 'die']
    assert signals and deaths, f'missing SIGTERM/die evidence for {container_id}: {relevant}'
    elapsed = (min(t for t in deaths if t >= min(signals)) - min(signals)) / 1e9
    return elapsed


def stop_and_check(*services):
    """Keep the command SLA; independently measure signal-to-exit time."""
    expected = set(services) or SERVICES
    # Query daemon time to delimit event history without assuming host/VM sync.
    since = run(['docker', 'info', '--format', '{{.SystemTime}}']).stdout.strip()
    started = time.monotonic()
    result = compose('stop', *services, check=False)
    elapsed = time.monotonic() - started
    print(f'Compose stop: returncode={result.returncode}, wall_seconds={elapsed:.3f}', flush=True)
    print(result.stdout, flush=True)
    ids = compose('ps', '-aq', *services).stdout.split()
    assert len(ids) == len(expected), 'missing stopped containers'
    containers = json.loads(run(['docker', 'inspect', *ids]).stdout)
    assert {c['Config']['Labels']['com.docker.compose.service'] for c in containers} == expected
    # Print every exit status before any assertion, including on failure.
    for container in containers:
        name = container['Config']['Labels']['com.docker.compose.service']
        state = container['State']
        print(f"Shutdown {name}: status={state['Status']}, exit={state['ExitCode']}, "
              f"OOMKilled={state['OOMKilled']}, FinishedAt={state['FinishedAt']}", flush=True)
    until = run(['docker', 'info', '--format', '{{.SystemTime}}']).stdout.strip()
    event_output = run(['docker', 'events', '--since', since, '--until', until,
                        '--filter', 'type=container', '--filter',
                        f'label=com.docker.compose.project={PROJECT}', '--format', '{{json .}}']).stdout
    events = [json.loads(line) for line in event_output.splitlines() if line.strip()]
    print('Shutdown daemon events: ' + json.dumps(events), flush=True)
    assert result.returncode == 0, f'Compose stop failed: {result.returncode}'
    for container in containers:
        state = container['State']
        assert state['Status'] == 'exited' and state['ExitCode'] == 0 and not state['OOMKilled'], state
        duration = shutdown_event_seconds(events, container['Id'])
        name = container['Config']['Labels']['com.docker.compose.service']
        print(f'Shutdown {name}: daemon SIGTERM-to-die={duration:.3f}s', flush=True)
        assert duration < 10, f'{name} signal-to-exit took {duration:.3f}s (10s grace)'
    # A slow command remains a failing gate, even if containers exit promptly.
    assert elapsed < 10, f'Compose stop wall time {elapsed:.3f}s exceeds under-10-second command criterion'
    print(f'PASS: clean stop of {sorted(expected)} in {elapsed:.3f}s (10s grace unchanged)', flush=True)


def wait_for(check, expected):
    deadline = time.monotonic() + 120
    while True:
        rows = states(expected)  # Worker exit fails immediately, even if HTTP works.
        passed = check(rows)
        if time.monotonic() >= deadline:
            raise RuntimeError('120s readiness deadline expired')
        if passed:
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def artifacts(*args):
    result = compose('exec', '-T', 'dashboard', 'python', 'scripts/check_artifacts.py', *args, check=False, timeout=30)
    print(result.stdout, flush=True)
    return result.returncode == 0


def browser_checkpoint():
    """Observer-assisted real browser verification; never infer it from HTTP."""
    print(f'BROWSER CHECK: http://127.0.0.1:{ENV["DASHBOARD_PORT"]}', flush=True)
    print('Open/reload this URL in a real browser. Leave Auto-refresh (15s) checked. '
          'Observe at least two automatic updates without reloading, then leave the tab open. '
          'Type browser-verified within 180s to run the timed stop:', flush=True)
    if not select.select([sys.stdin], [], [], 180)[0]:
        raise RuntimeError('browser observation timed out; NOT VERIFIED')
    if sys.stdin.readline().strip() != 'browser-verified':
        raise RuntimeError('browser observation not confirmed; NOT VERIFIED')
    print('Browser observer confirmed active auto-refresh; tab must remain open during stop.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true',
                        help='require two real-browser auto-refresh observations before stops')
    args = parser.parse_args(argv)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        ENV['DASHBOARD_PORT'] = str(listener.getsockname()[1])
    try:
        print(run(['docker', 'version'], timeout=15).stdout)
        print(run(['docker', 'compose', 'version'], timeout=15).stdout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'NOT VERIFIED: Docker unavailable: {exc}')
        return 2
    print(f'Isolated project: {PROJECT}; root: {ENV["DATA_ROOT"]}; port: {ENV["DASHBOARD_PORT"]}', flush=True)
    started = False
    try:
        check_config(json.loads(compose('config', '--format', 'json').stdout), ENV['DATA_ROOT'])
        custom = ENV.pop('DATA_ROOT')
        try:
            check_config(json.loads(compose('config', '--format', 'json').stdout), '/app/data')
        finally:
            ENV['DATA_ROOT'] = custom
        print('PASS: default/custom Compose configuration', flush=True)
        print(compose('build', 'simulator', timeout=600).stdout, flush=True)
        started = True
        compose('up', '-d', '--no-build', 'dashboard')
        wait_for(lambda rows: rows[0].get('Health') == 'healthy', {'dashboard'})
        with urllib.request.urlopen(f'http://127.0.0.1:{ENV["DASHBOARD_PORT"]}/_stcore/health', timeout=3) as response:
            assert response.status == 200
        assert not artifacts(), 'empty volume must not be pipeline-ready'
        print('PASS: empty dashboard healthy, pipeline not ready', flush=True)
        compose('up', '-d', '--no-build')
        wait_for(lambda rows: artifacts() and next(r for r in rows if r['Service'] == 'dashboard').get('Health') == 'healthy', SERVICES)
        architecture = compose('exec', '-T', 'simulator', 'uname', '-m').stdout.strip()
        print(f'Runtime architecture: {architecture}', flush=True)
        assert architecture == 'aarch64', 'ARM64 acceptance gate not met'
        print(run(['docker', 'image', 'inspect', PROJECT + ':local', '--format', '{{.Os}}/{{.Architecture}}']).stdout)
        print(compose('exec', '-T', 'simulator', 'python', '-m', 'pip', 'freeze').stdout)
        ids = compose('ps', '-q').stdout.split()
        images = run(['docker', 'inspect', '--format', '{{.Image}}', *ids]).stdout.splitlines()
        assert len(images) == 5 and len(set(images)) == 1
        if args.browser:
            browser_checkpoint()
        stop_and_check('simulator')
        time.sleep(10)
        stop_and_check('preprocess', 'train', 'infer')
        assert artifacts()
        print(compose('run', '--rm', '--no-deps', '-T', 'simulator', 'python', 'scripts/check_persistence.py', 'save').stdout)
        stop_and_check('dashboard')
        compose('down')
        compose('up', '-d', '--no-build', 'dashboard')
        print(compose('exec', '-T', 'dashboard', 'python', 'scripts/check_persistence.py', 'verify').stdout)
        wait_for(lambda rows: rows[0].get('Health') == 'healthy', {'dashboard'})
        # This bounded auto-enabled render catches a blocking refresh sleep,
        # but only --browser covers the real server/browser shutdown lifecycle.
        app_source = 'from pipeline.dashboard.app import main; main()'
        render = (f"from streamlit.testing.v1 import AppTest; a=AppTest.from_string({app_source!r}); "
                  "a.run(timeout=5); assert not a.exception, a.exception; "
                  "assert a.checkbox[0].value; assert a.title[0].value == 'DashBite'; "
                  "print('PASS: auto-enabled Streamlit render completed without blocking')")
        print(compose('exec', '-T', 'dashboard', 'python', '-c', render, timeout=15).stdout)
        compose('up', '-d', '--no-build')
        wait_for(lambda rows: artifacts('--new-since', 'smoke-manifest.json'), SERVICES)
        if args.browser:
            browser_checkpoint()
        stop_and_check()
        print('PASS: Docker shared image, health separation, handoffs, restart persistence and clean shutdown', flush=True)
        print('PASS: observer-assisted active-browser shutdown' if args.browser else
              'NOT VERIFIED: active-browser shutdown (run make docker-verify-browser)', flush=True)
        compose('down', '--volumes')
        run(['docker', 'image', 'rm', PROJECT + ':local'])
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', flush=True)
        if started:
            for args in [('ps', '-a'), ('logs', '--tail=60'), ('stop',)]:
                try:
                    print(compose(*args, check=False).stdout)
                except Exception as diagnostic:
                    print(f'Diagnostic failed: {diagnostic}')
        if started:
            print(f'Preserved project {PROJECT}. Inspect with docker compose -p {PROJECT} ps -a; do not replace its manifest.')
        else:
            print('Verification stopped before creating service containers or volumes.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
