# Independent Tester/Reviewer — Chen Liu (cl787)

Review date: 2026-10-01. Repository B, Option 1: Extend and Containerize DashBite.

## Scope and preservation

Reviewed the existing checkout directly at `/Users/chenliu/Desktop/data engineering/IDS706-DashBite-AI-Workflow`. Remote: `https://github.com/chen04301121-cmyk/IDS706-DashBite-AI-Workflow.git`. HEAD before and after review: `fe1b3e681ef312cdc3e5e7ea878b2f6eda7a01e1`.

Context was reconstructed from the repository, particularly the approved appended plan and all README Builder/student observations. No Builder conversation was used. The initial working tree already contained modified Makefile, README, Architect transcript, dashboard, paths and four workers, plus untracked Docker packaging, Builder transcript, shutdown module, verification helpers and tests. Those changes were retained. No reset, discard, commit, or push was performed.

The plan and both transcripts retain their pre-review SHA-256 checksums. README additions are append-only, preserving every historical observation and classroom attribution. Neither student smoke-test volume nor manifest was mounted, modified, or deleted, including `dashbite-smoke-shutdown-20260930232346-29245`.

All file references below are relative to the absolute checkout above. This report is automated Reviewer evidence; it does not claim the student personally tested these changes.

## Findings, ranked by severity

1. **P2 — False dashboard failure and waiting claims; fixed.** `pipeline/dashboard/app.py:78`, `:169`, `:184`. An all-zero ranking still has rows, so the former code blamed its first field. The failure panel also treated completed zero-failure batches like missing preprocessing data. The dashboard now distinguishes empty quality data, completed zero failures, and actual failures. A feature window without rows no longer says preprocessing is pending when quality records exist. Real Streamlit AppTest coverage checks all three states, including the actual failure chart (`tests/integration/test_dashboard_failure_states.py:11`).

2. **P2 — Shutdown measurements were conflated; diagnostic gap fixed, historical cause remains unresolved.** `tests/docker_verify.py:74`, `:86`. Whole-command wall time includes CLI startup, Compose orchestration, daemon requests and completion handling. Docker's grace period concerns each container's stop handling. Compose progress durations are not a substitute for either measurement. The prior gate described wall time as exceeding the grace period and did not expose enough evidence to distinguish them. It now records command return code, wall time, raw progress, every container's status/exit/OOM flag and FinishedAt, and project-filtered daemon SIGTERM/die events. Event intervals use only daemon timestamps, avoiding subtraction between host and VM clocks. **Both the original command-under-10-seconds assertion and the unchanged 10-second Compose grace period remain.** The gate also asserts signal-to-die under 10 seconds. Missing event evidence fails; exit statuses print before event-query failure can obscure them. Regression tests reject 12.930-second commands even when container exits are quick and clean (`tests/unit/test_docker_shutdown_gate.py:23`).

   The student's 62.90, 11.788 and 12.930-second command times are still recorded as exceeding the expectation. Clean exits do not retroactively pass timing. This review encountered default-CLI timeouts and one HTTP 500 response. `/usr/local/bin/docker` and the normal Compose plugin resolve into `/Volumes/Docker`; explicitly using the installed `/Applications/Docker.app` CLI and plugin completed verification. One installed-CLI image inspection took 0.371 seconds. This identifies a workable invocation and an environment concern; it does **not** prove why the historical student commands were slow. No global installation change or acceptance-criterion change was made.

3. **P3 — Training-state validation hid which invariant failed; fixed diagnostics, original observation not diagnosed.** `scripts/check_artifacts.py:109`. The exact old message means JSON had parsed and the combined state condition was false; it does not itself establish a truncated JSON file or corrupt checkpoint. Controlled tests publish complete valid data between the helper's reads: (a) new features/training state can exceed its captured feature-row count; (b) new training state can reference a checkpoint published after its captured checkpoint list. Both fail one snapshot and pass the next without repair (`tests/integration/test_smoke_helpers.py:86`). The helper now prints the offending checkpoint reference or row count and snapshot bounds; malformed state remains a failure. Boolean counts are rejected rather than accepted as Python integers. These are demonstrated possible mechanisms, not a diagnosis of the student's `117.0s left` observation. Stable stopped-writer validation remains required. Atomic publication or a consistent snapshot protocol would be broader work and was not introduced.

## Approved-plan review

- **Packaging:** one shared image, exactly five service commands; native ARM64; no forced platform, fixed container names, or automatic restart. Runtime-only build context and classroom attribution retained.
- **Paths:** explicit `base` still selects `base/data`; runtime `DATA_ROOT` resolution handles unset/blank, relative, absolute and tilde cases. Dashboard uses the shared helpers without forcing the project root. Frozen config and native Make workflow retained.
- **Storage:** one project-scoped named volume; common absolute mount/root override; dashboard read-only and workers read/write; only localhost dashboard publication. No student/host data bind mounts.
- **Health:** empty dashboard HTTP health is tested separately from missing pipeline artifacts; worker status and linked output are independent checks. AppTest exercises actual application rendering. HTTP alone is not readiness.
- **Helpers:** existing tests cover invalid IDs/probabilities/labels, missing checkpoint/metrics/state/markers/quality, manifest traversal and symlink escape, baseline overwrite refusal, changed/missing files, bounded polling and genuinely new prediction IDs. Persistence save still requires stopped writers and compares before/after snapshots; verification checks original hashes before restarting writers.
- **Shutdown:** existing cooperative signal tests cover all workers, SIGTERM/SIGINT during iterations, handler restoration, exception propagation and waking a 60-second poll. No worker implementation change was needed in this review. Long active iterations can still exceed the grace period.
- **Documentation:** native commands and Docker Make targets retained; prior plan, student evidence, Builder evidence, and classroom attribution preserved. New evidence is appended separately.

## Actual verification

| Check | Actual result |
|---|---|
| Pre-edit baseline, `make test` | 72 passed in 8.94s |
| Final full suite, `make test` | 90 passed in 16.38s, exit 0 |
| Environment override suite before the final event-query regression was added | 89 passed in 11.36s; `/tmp/dashbite-review-unused-root-01a0f59b` was not created |
| Initial Docker attempt | NOT VERIFIED: `docker version` timed out after 15s; Make exit 2; no service resources created |
| Default-CLI retry, `dashbite-test-463887592e89` | Built, passed configuration, empty HTTP/readiness separation, linked artifacts and aarch64 runtime; subsequently failed on `docker info` after 180s. Gate failure retained, not counted as a pass. |
| Separate stop of that review-owned project using installed CLI | All five exited 0, no OOM; wall 3.317s; signal-to-die 0.826–1.001s |
| Final installed-CLI gate, `dashbite-test-5a1b6f022deb` | PASS, exit 0; custom root `/tmp/dashbite-verify-data`, localhost port 62359 |
| Image/runtime and service configuration | linux/arm64, aarch64; all five services same image; default/custom root checks passed |
| Empty-volume dashboard | Healthy and host HTTP 200 while artifact check failed, as expected |
| Stable stopped-writer data | 5 raw files / 250 rows; 5 feature files / 250 rows; 4 prediction files / 250 rows; 5 checkpoints; 5 quality records |
| Persistence | 31 original files unchanged after down and dashboard-only recreation |
| Resumed output | 2 new raw files, 1 feature file, 1 checkpoint, 1 prediction file; 50 new prediction rows |
| Rendering | Container AppTest rendered Model Pulse without exception; native AppTests verified empty/zero/actual-failure states |
| Diff hygiene | `git diff --check` passed |

During regression-test development, the first 75-test run had 74 passes and one failure because the new test queried the wrong Streamlit chart element name (`arrow_vega_lite_chart`). Inspection showed this installed version emits `vega_lite_chart`; the test was corrected while retaining the requirement that an actual failure chart renders. Subsequent complete runs passed (82, 89, then 90 tests).

Final successful project's shutdown results:

| Stop group | Command wall time | Daemon SIGTERM-to-die | Exit/OOM |
|---|---:|---|---|
| simulator | 0.505s | 0.304s | 0 / false |
| preprocess, train, infer | 0.789s | 0.395s, 0.620s, 0.586s | all 0 / false |
| dashboard before recreation | 0.719s | 0.597s | 0 / false |
| final five services | 0.754s | dashboard 0.593s; infer 0.501s; preprocess 0.342s; simulator 0.360s; train 0.631s | all 0 / false |

Native Python 3.13.2 / pytest 9.1.1; container Python 3.12. Docker Engine 29.7.2, Desktop 4.88.1, Compose 5.4.0. Container versions: pandas 3.0.6, NumPy 2.5.3, scikit-learn 1.9.1, joblib 1.6.0, Streamlit 1.64.0, Altair 6.3.0. Image build reused cached dependencies; this review does not claim a fresh dependency download/wheel-resolution test.

The successful project's containers, volume and image tag were removed by the gate. The failed review project `dashbite-test-463887592e89` remains stopped with its volume for diagnosis. No global prune was run.

## Limitations and targeted student rerun

The original student smoke tests are complete and remain valid historical evidence. Historical shutdown latency and the exact cause of the transient training-state message cannot be reconstructed from the supplied observations. This review did not reproduce a 12.930-second stop, inspect either retained student volume, or perform a new human browser inspection. Shared files still lack atomic publication and crash-safe exactly-once guarantees; live readers can observe different generations, and individual reads/work iterations are not preempted by a polling deadline. Growing history, occasional unsuitable random training batches, and open dependency lower bounds remain known constraints. No broader redesign is proposed here.

For new **personal** evidence of the corrected wording and timing, use a fresh project; do not reuse either original student project. The following temporary CLI selection matches the successful automated run and does not alter global Docker settings. Run in a new terminal with Docker Desktop running:

```bash
cd '/Users/chenliu/Desktop/data engineering/IDS706-DashBite-AI-Workflow'
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
export DOCKER_CONFIG="$(mktemp -d /tmp/dashbite-review-cli.XXXXXX)"
printf '%s\n' '{"cliPluginsExtraDirs":["/Applications/Docker.app/Contents/Resources/cli-plugins"]}' > "$DOCKER_CONFIG/config.json"
export DOCKER_HOST=unix:///Users/chenliu/.docker/run/docker.sock
unset DOCKER_CONTEXT COMPOSE_FILE COMPOSE_PROFILES DOCKER_DEFAULT_PLATFORM
make test
make docker-verify
```

Record each exit status; do not proceed if either gate fails. `make docker-verify` chooses its own unique project and prints wall time, daemon-event intervals and every exit status. It does not replace a personal browser check. For that check, continue in the same terminal:

```bash
export COMPOSE_PROJECT_NAME="dashbite-review-student-$(date +%Y%m%d%H%M%S)-$$"
export DATA_ROOT=/tmp/dashbite-review-student-data
export DASHBOARD_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
export TRAIN_EVERY_N_EVENTS=50 BATCH_SIZE=50 POLL_INTERVAL_SECONDS=2
export CORRUPT_BATCH_RATE=0 RANDOM_SEED=42
printf 'New personal review project: %s\n' "$COMPOSE_PROJECT_NAME"
make docker-build
docker compose up -d dashboard
open "http://localhost:${DASHBOARD_PORT}"
```

Allow startup and personally verify the empty-state message says no preprocessing results yet. Then:

```bash
make docker-up
docker compose exec -T dashboard python scripts/check_artifacts.py --wait 120
docker compose ps -a
open "http://localhost:${DASHBOARD_PORT}"
```

Require artifact PASS and all workers running. Allow the 15-second refresh; personally verify the field panel says preprocessing completed with no field failures, without blaming a field. The actual-failure state already has automated rendering coverage. Save a screenshot if personal evidence is needed.

Capture final shutdown without suppressing return codes or exits:

```bash
review_since=$(docker info --format '{{.SystemTime}}')
time docker compose stop
review_stop_rc=$?
printf 'Compose stop exit code: %s\n' "$review_stop_rc"
docker compose ps -a
docker compose ps -aq | xargs docker inspect --format '{{.Name}} status={{.State.Status}} exit={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} finished={{.State.FinishedAt}}'
review_until=$(docker info --format '{{.SystemTime}}')
docker events --since "$review_since" --until "$review_until" --filter type=container --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --format '{{json .}}'
```

Save wall time and event output. Any nonzero exit, OOM kill, wall time at least 10 seconds, or signal-to-die interval at least 10 seconds remains a failed criterion requiring investigation. After saving evidence, `docker compose down` removes only this new project's containers/network and retains its data. Do not add `--volumes` to commands for either historical student project. Exit the new terminal to leave the temporary CLI environment.

## Dashboard shutdown follow-up — 2026-10-01

### Confirmed personal failure and coverage correction

The student subsequently reported that project
`dashbite-review-student-20261001114554-29245` passed both personal wording checks
(empty and completed-zero-field-failure), but dashboard shutdown failed with an
active real browser session. The supplied event log was read from
`/Users/chenliu/.codex/attachments/fd3ab6ed-bdc2-4c31-8879-99d08839c0a6/Pasted text.txt`.
It records dashboard SIGTERM at timeNano `1790870265059908218`, SIGKILL at
`1790870275102601000` (**10.042692782s later**), and die/exit **137**. Read-only
inspection of the still-stopped containers confirmed dashboard exit 137,
OOMKilled=false, and all four workers exit 0. Dashboard logs show `Stopping...`;
a health probe then encountered connection refused. No student container was
restarted, removed, or modified; no student volume was mounted.

**P2 — confirmed application shutdown bug, fixed in this follow-up.** The earlier
Docker PASS did not cover this lifecycle: its HTTP probe did not execute a
browser session and its separate AppTest explicitly disabled auto-refresh.
That historical PASS is retained, but must not be interpreted as active-browser
shutdown evidence. This new failure is forced termination, not just CLI latency.
It does not establish the cause of earlier observations where all exits were 0.

### Reproduction and cause

Only new review project `dashbite-test-browser-7b97e1df48` was used for reproduction.
A real in-app Chromium browser showed Model Pulse with Auto-refresh (15s) checked.
An untimed stop happened late in the refresh interval and passed (1.707s wall,
1.448s signal-to-die). To test the vulnerable phase deterministically, a copy of
the old app **inside that disposable container only** logged entry into its
unchanged 15-second sleep and scheduled a faulthandler stack dump two seconds
later. The host stopped it immediately after the browser-triggered sleep began.
This produced **10.539s wall**, SIGKILL about **10.037s after SIGTERM**, exit **137**,
and OOMKilled=false. The added diagnostic log/stack dump did not shorten or extend
the sleep, replace signal handlers, or modify repository application code.

The stack captured the script thread at the `time.sleep(15)` line and the main
thread in Python's `threading._shutdown`. Streamlit uses a non-daemon script thread
and processes script stop requests at its execution yield points (normally
Streamlit calls). SIGTERM stopped the server, but the sleeping script thread
could keep Python alive beyond Docker's unchanged 10-second grace. A stop late
in the sleep could finish in time; a stop early in it could not. This directly
explains the reproduced active-browser failure and why an arbitrary single stop
can pass. No claim is made to have a stack dump from the student's original run.

### Narrow fix and regression coverage

- `pipeline/dashboard/app.py:144` and `:190`: render Model Pulse in a periodic
  `st.fragment`, using `run_every=15` when checked and `None` when unchecked.
  The script finishes between updates; the browser's active-session timer
  initiates refreshes. Removed `time.sleep`/`st.rerun` from the app. Loaders,
  metrics, charts, read-only data access and the 15-second cadence are preserved.
- `requirements.txt:5`: Streamlit minimum raised from 1.28 to **1.37**, the first
  stable fragment release. This is the API floor for this fix, not a dependency
  upgrade claimed as the shutdown fix. The reproduced and fixed images both
  used Streamlit **1.64.0**. See the official [fragment documentation](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
  and [1.37 release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2024#version-1370).
- `tests/integration/test_dashboard_failure_states.py`: real AppTest now runs with
  default auto-refresh enabled and must finish within **five seconds**, then
  toggles off/on. The old 15-second loop cannot satisfy this check. Existing
  empty/zero/actual-failure render tests remain.
- `tests/docker_verify.py` and `Makefile`: added **`make docker-verify-browser`**,
  an observer-assisted mode requiring an actual browser to stay open through
  shutdown before and after recreation. The observer must see two automatic
  updates and enter `browser-verified` at each prompt. EOF, wrong confirmation
  and a 180-second observation timeout fail; regression tests cover those cases.
  This is explicitly observer-assisted rather than unattended browser automation.
  The gate also runs a bounded auto-enabled AppTest now. Plain `docker-verify`
  explicitly says active-browser shutdown is NOT VERIFIED.

No SIGKILL/exit-137 result is suppressed, no worker or Compose shutdown setting
changed, and the command-under-10-seconds and signal-to-die-under-10-seconds
assertions remain. Longer data-loading or chart work could still exceed the
grace period; this fix removes the unconditional 15-second sleep, not all possible
sources of latency.

### Actual follow-up verification

- Fresh pre-fix baseline: **90 passed in 10.75s**.
- Full suite after fix and gate regression additions: **95 passed in 8.43s**.
- Actual browser, fixed image, empty data: **1.467s** stop, exit **0**,
  OOMKilled=false; daemon interval **1.258s**.
- Actual browser, fixed image, populated data: observed automatic feature-count
  changes **550 → 1,250** without reload; all-service stop **2.683s**, all exits
  **0**, no OOM kills; dashboard daemon interval **2.316s**.
- New full browser-assisted gate project: `dashbite-test-89a9efbb1de3`, custom
  data root and localhost port 64331. First live browser observation showed
  **1,700 → 2,800 → 3,950** feature rows without reload. The pre-recreation
  dashboard stop passed at **0.993s** wall, **0.866s** daemon interval, exit **0**.
  **545 original files** survived recreation unchanged. The final stop result
  is recorded below after its second live-browser observation.

All of these follow-up checks are Reviewer/agent observations, not a claim that
the student personally tested the fragment fix. The original student failure
and successful wording observations remain preserved.

Final browser-assisted gate result: **FAIL**, gate exit 1 (Make exit 2). The
second observed feature-count sequence was **5,600 → 7,800 → 8,950**, without
reloading between observations and with auto-refresh checked. The final stop
command took **1.550s**. Dashboard exited **0**, OOMKilled=false, and its daemon
SIGTERM-to-die interval was **0.722s**. Simulator, preprocess and train also exited
0. **Inference had already exited 1 with `EOFError` inside `joblib.load` at
`pipeline/infer.py:36`, during the browser observation period.** The gate printed
all statuses and failed; this run is not an overall acceptance PASS.

This is a separate outstanding shared-file handoff failure. Checkpoints are
written directly to their published filenames (`pipeline/train.py`,
`write_checkpoint`) while inference selects the newest filename. The traceback
is consistent with a partially published checkpoint. Fixing publication semantics
would be additional scope; it was not silently added to the dashboard patch.
The failed review project `dashbite-test-89a9efbb1de3` is stopped with its volume
preserved for diagnosis. Dashboard-specific shutdown checks passed both empty
and populated live-browser cases, but the full-stack gate remains failed on this
independent worker error. The student projects remain untouched.

### Short targeted personal rerun for this dashboard fix

In a terminal where the installed Docker CLI/plugin already work, run:

```bash
cd '/Users/chenliu/Desktop/data engineering/IDS706-DashBite-AI-Workflow'
export COMPOSE_PROJECT_NAME="dashbite-dashboard-rerun-$(date +%Y%m%d%H%M%S)-$$"
export DATA_ROOT=/tmp/dashbite-dashboard-rerun-data
export DASHBOARD_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
docker compose build dashboard
docker compose up -d dashboard
open "http://localhost:${DASHBOARD_PORT}"
```

Personally verify Model Pulse appears, leave **Auto-refresh (15s) checked** and
the browser tab open for at least 30 seconds. Then, with the tab still open:

```bash
review_since=$(docker info --format '{{.SystemTime}}')
time docker compose stop dashboard
review_stop_rc=$?
printf 'Compose stop exit=%s\n' "$review_stop_rc"
docker compose ps -aq dashboard | xargs docker inspect --format '{{.Name}} status={{.State.Status}} exit={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}'
review_until=$(docker info --format '{{.SystemTime}}')
docker events --since "$review_since" --until "$review_until" --filter type=container --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --format '{{json .}}'
```

Expect Compose exit 0, dashboard exited/0, no OOM, no SIGKILL, and stop wall time
under 10 seconds. Repeat by running `docker compose up -d dashboard`, reloading
the browser, and stopping shortly after it renders with refresh still checked.
Save the outputs; `docker compose down` then removes this new project's containers
while preserving its volume. This dashboard-only rerun deliberately isolates the
shutdown fix; it does not pass or replace the separate full-stack acceptance gate.
For full-stack testing, `make docker-verify-browser` creates a different unique
project and requires the two observations described above; the inference handoff
failure may need separate investigation before that gate is reliable.

The plan, transcripts, earlier README/report observations, and stopped student
container states were checked unchanged. No commit or push was performed.

A final one-shot artifact check against the failed review project's stopped data,
using the dashboard service's read-only mount, passed and loaded all saved
checkpoints. That supports a transient read/publication problem rather than
persistent unreadable checkpoints, but does not erase inference's exit 1 or
turn the full gate into a pass. The pre-fix reproduction's diagnostic source,
stack dump and Docker events, the student's supplied events/state, native test
log, fixed browser stop logs and failed full-gate log are saved with this report's
output bundle. The successful dashboard-only investigation project's containers,
volume and image tag were removed; the failed full-gate project remains stopped.
