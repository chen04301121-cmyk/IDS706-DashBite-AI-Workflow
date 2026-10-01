# DashBite — Simple Stage-by-Stage ML Pipeline

## Final submission status — 2026-10-01

Chen Liu (`cl787`), IDS706 Repository B, Option 1.

The earlier dated sections below are the development record, including genuine
failed checks. Current source includes the subsequent checkpoint-publication fix:
training writes a hidden temporary file and publishes the complete checkpoint by
same-directory atomic replacement. Metrics are published before the checkpoint;
training state, raw batches, feature batches, and prediction CSVs use the same
publication helper. Microsecond checkpoint names and an overwrite check avoid
replacing a checkpoint already visible to readers. The native suite is **99 passed**.
The final browser-assisted Docker gate **passed**: 352 unchanged files, 300 new
predictions after restart, all exits 0/no OOM, final stop 1.513 seconds.

See [final verification and remaining submission items](docs/final-verification.md).

### Role contributions and student decisions

- **Architect:** inspected the classroom application and appended the reviewed
  containerization plan; kept one shared image, five services, and isolated storage.
- **Builder:** implemented Compose, configurable paths, inspection helpers, tests,
  and graceful worker shutdown after the student's observed exit-137 failures.
- **Tester:** independently reviewed the implementation, fixed misleading dashboard
  states, improved shutdown evidence, and reproduced the active-browser shutdown
  bug; replaced the blocking refresh loop with periodic Streamlit fragments.
- **Final integration follow-up:** fixed the checkpoint publication race exposed
  by the Tester and completed further verification. This is subsequent integration
  work, not a rewritten claim about the earlier independent review.

Accepted recommendation: separate HTTP health from artifact readiness and check
persistence before restarting writers. Changed recommendation: replace lengthy
inline smoke-test Python commands with two inspectable helper scripts. Kept the
original 10-second stop criterion instead of hiding failed shutdowns by extending
its timeout. The student's manual results are preserved in the dated sections,
including 479 unchanged files and 850 new predictions in the worker-fix rerun.
Later assistant-observed checks are explicitly separate from personal student tests.

Classroom foundations and attribution remain below. Full role-chat exports are
being completed; the existing transcript excerpts must not be described as complete.


Teaching demo of a modular data + ML application. **DashBite** predicts whether a food-delivery order will be **late**.

Run natively or with the Docker Compose workflow below. Stages are separate Python modules that share folders under `data/` by default. Training and inference are **independent processes** coupled only by timestamped checkpoints in `data/models/`. Inference always uses the **newest** checkpoint.

## Stages

| Stage | Module | What it does |
|-------|--------|----------------|
| 0 | `pipeline.config`, `pipeline.paths` | Shared config + data folders |
| 1 | `pipeline.simulator` | Writes timed CSV batches to `data/raw/` (“new orders arrived”) |
| 2 | `pipeline.preprocess` | Drops bad rows, adds `hour` / `is_peak` → `data/features/` |
| 3 | `pipeline.train` | Retrains when ≥ `TRAIN_EVERY_N_EVENTS` new labeled rows; writes checkpoints |
| 4 | `pipeline.infer` | Scores unscored rows with newest checkpoint → `data/predictions/` |
| 5 | `pipeline.dashboard` | Streamlit: **Model Pulse** |

## Setup

```bash
make install
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Makefile shortcuts

```bash
make help          # list targets
make test          # full pytest gate
make run           # start all stages in background + dashboard
make stop          # stop background pipeline
make clean-data    # wipe runtime CSVs/checkpoints under data/
```

Foreground single stages: `make simulator`, `make preprocess`, `make train`, `make infer`, `make dashboard`.

Agent demo prompts (independent Architect / Implementer / Reviewer chats): `make prompts` → http://localhost:8502

GitHub Pages (static copy of the board): https://kedar-v.github.io/TestingAndContainerisationDemo/  
Rebuild after editing prompts: `make prompts-static`

## Testing gate (required after every stage)

After each stage you implement or change, run the **full** suite:

```bash
pytest
```

That runs **unit**, **regression**, and **integration** tests together so new work cannot break older stages.

```bash
pytest -m unit
pytest -m regression
pytest -m integration
```

Layout:

```
tests/
  unit/
  regression/
  integration/
  fixtures/
```

## Run the pipeline (background stack)

Classroom default — durable background jobs:

```bash
make run                 # simulator + preprocess + train + infer + Model Pulse
make status              # confirm each stage is UP
open http://localhost:8501
make stop
```

Logs: `.logs/*.log` · PIDs: `.logs/pids/` · Poll default: `POLL_INTERVAL_SECONDS=15`

Foreground single stages (one terminal each): `make simulator`, `make preprocess`, `make train`, `make infer`, `make dashboard`.

## Config (environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `TRAIN_EVERY_N_EVENTS` | `2000` | Retrain after this many **new** labeled rows |
| `BATCH_SIZE` | `50` | Orders per simulator tick |
| `POLL_INTERVAL_SECONDS` | `15.0` | Sleep between polls/ticks |
| `RANDOM_SEED` | `42` | Training seed |
| `CORRUPT_BATCH_RATE` | `0.25` | Fraction of batches that include NaNs / bad types |

Preprocess logs per-batch **throughput** and **field-level failures** to `data/quality/batch_quality.csv`. Model Pulse shows these live.

## Design notes for class

- Intake uses **batch CSV files** under the hood; logs say “new orders arrived”.
- Train **only writes** `data/models/checkpoint_*.joblib`.
- Infer **only reads** that folder and never imports train.
- Dashboards read `data/features/` and `data/predictions/` — test the metric helpers with `pytest`, not the browser UI.


## IDS706 extension: local Docker Compose

The shared-image architecture and Dockerfile/Compose foundation come from
[the classroom container guide](docs/docker-k8s-guide.md), Part 1. The role handoff
and personal smoke test follow [the classroom development cycle](docs/dev-cycle.md).
The approved [IDS706 plan](docs/plan.md#ids706-final--repository-b-option-1-extend-and-containerize-dashbite)
is preserved, including its earlier classroom section. This extension implements
compatible path selection, five-service packaging, isolated persistent storage,
HTTP availability monitoring, artifact/persistence checks, and regression coverage.
It adds no Kubernetes, replicas, ML redesign, or student-authored observations.

Install and start Docker Desktop with Compose, then run from this repository:

```bash
docker version
docker compose version
docker compose config
make docker-build
make docker-up
make docker-status
open http://localhost:8501
make docker-logs          # Ctrl-C exits log following; containers keep running
make docker-stop         # stops containers; data stays
make docker-up
make docker-down         # removes containers/network; data stays
```

Exactly five services (`simulator`, `preprocess`, `train`, `infer`, `dashboard`)
use one image. `docker-build` builds that shared image once through the simulator
service. Docker chooses the native platform; Apple Silicon should report
`aarch64` from `docker compose exec -T simulator uname -m`. Only the dashboard
publishes a port, on `127.0.0.1`. The dashboard mount is read-only; workers share
read/write access. There is no automatic restart policy, so inspect `ps -a` and
logs for crashes. Keep one instance per service.

### Configuration and persistence

| Setting | Direct Python default | Make / Compose demo default |
|---|---|---|
| `TRAIN_EVERY_N_EVENTS` | 2000 | 50 |
| `BATCH_SIZE` | 50 | 20 |
| `POLL_INTERVAL_SECONDS` | 15 | 15 |
| `RANDOM_SEED` | 42 | 42 |
| `CORRUPT_BATCH_RATE` | 0.25 | 0.25 |
| `DATA_ROOT` | `<project>/data` | native: same; Compose: `/app/data` |
| `DASHBOARD_PORT` | native dashboard 8501 | Compose: 8501 |

Export overrides in the terminal before running Compose/Make. `DATA_ROOT` is
resolved at each call: explicit Python `base` means `base/data` and wins over the
environment; otherwise a nonblank `DATA_ROOT` is the data directory itself.
Native relative values are relative to the project, `~` expands, and blank values
fall back to the project default. The frozen Python config schema is unchanged.

For Compose, use an **absolute Linux container path**, e.g.
`export DATA_ROOT=/tmp/dashbite-smoke-data`, never a Mac host path, whitespace-only
value, or relative path. The environment and mount target use the same override.
The five shared subdirectories include quality logs, preprocessing markers and
training state as well as raw/features/models/predictions. No host `data/` is mounted.

Compose scopes the `dashbite-data` named volume to its project. Use the same
`COMPOSE_PROJECT_NAME` and root on recreation to retain history and processing
state; use a new project for an isolated run. The shared image tag is project-scoped.
`stop` and `down` preserve data. Volumes are not backups. Only deliberately run
`docker compose down --volumes` for a known disposable project after saving evidence;
never use global pruning or native `make clean-data` for this workflow.

### Health versus readiness

Docker's dashboard-only HTTP probe requests `/_stcore/health` every 10 seconds
(timeout 3 seconds, start period 20 seconds, three retries). An empty dashboard can
be healthy. This proves HTTP availability, **not** rendered charts, model readiness,
valid predictions, or healthy workers, and unhealthy status does not restart it.
Inspect the browser and separately validate pipeline artifacts:

```bash
docker compose exec -T dashboard python scripts/check_artifacts.py --wait 120
docker compose ps -a
```

The helper prints paths, row counts and sample predictions and exits nonzero on
invalid output/timeout. Without `--wait` it checks once. The existing “Samples
scored” dashboard metric counts feature rows; use prediction checks for inference
evidence. The dashboard refresh remains 15 seconds regardless of pipeline polling.

The two inspection helpers neither run stages nor control containers. Before
`check_persistence.py save`, stop **all four writers** and pass the one-shot artifact
check. Save uses a one-off simulator-service container for writable access, rejects
an existing `smoke-manifest.json`, and checks that artifacts did not change during
validation. The caller must confirm stopped workers; a file snapshot cannot prove
process state. Recreate **dashboard only**, run `check_persistence.py verify`, and
only then restart writers and use `check_artifacts.py --new-since smoke-manifest.json
--wait 120`. Follow the exact ordered commands in the plan. All manifest paths
are relative and checked for traversal/symlink escape. Checkpoint loading is for
this run's generated artifacts, not untrusted downloaded models.

### Builder automated verification (separate from student smoke test)

```bash
make test                 # complete native suite; no Docker daemon required
make docker-verify        # explicit Docker gate; uses host Python stdlib
```

The Docker gate chooses a unique `dashbite-test-*` project, unused localhost port,
custom container root and disposable volume; it uses batch/threshold 50, polling
2 seconds, corruption 0 and seed 42, independent of normal demo overrides. It
validates resolved default/custom Compose configurations, builds the image, checks
empty-dashboard health separately from readiness, waits up to 120 seconds for
handoffs while rejecting exited workers, records architecture/dependency versions,
and checks that all five containers use the same image. It checks actual stopped
container states (exit 0, no OOM kill, elapsed stop under the unchanged 10-second
grace period), including the final all-service stop. It stops writers, saves
checksums, recreates dashboard only, verifies history, executes a bounded Streamlit
AppTest render, then requires new artifacts and new prediction IDs within 120
seconds after restart. Build has a separate 600-second limit. Success removes only
its own disposable containers, volume and image tag. Failure prints status/logs,
stops its containers and preserves its volume; recover the printed project name
before inspecting or deliberately cleaning up. Missing Docker is reported as
**NOT VERIFIED** with nonzero exit, never as a pass. A port-allocation race is
possible; rerun with a fresh isolated project if another process takes the port.

Builder verification on 2026-09-30 (America/New_York), starting at clean HEAD
`fe1b3e6` with approved plan commit `83c308c`:

| Automated command/check | Actual result |
|---|---|
| Baseline `make test`, before edits | **32 passed** |
| Full suite after path/dashboard stage | **40 passed** |
| Full suite after helpers/packaging and final implementation | **56 passed** |
| `DATA_ROOT=/tmp/dashbite-unused-environment-sentinel make test` | **56 passed**; sentinel directory not created |
| Initial `make docker-verify` (before shutdown follow-up) | **PASS**, exit 0; project `dashbite-test-1f9422aed495`, custom root `/tmp/dashbite-verify-data`, localhost port 53700 |
| Resolved configuration | Default and custom roots passed; five service commands, one shared image, scoped volume, localhost-only publication, dashboard-only healthcheck |
| Build / runtime | Native **linux/arm64**, `uname -m` = **aarch64**; five containers shared the same image ID |
| Health separation | Empty dashboard became healthy and host HTTP returned 200 while artifact check correctly failed |
| Stable artifacts with writers stopped | 10 raw files / 500 rows; 10 feature files / 500 rows; 8 prediction files / 500 rows; 9 checkpoints; 10 quality records |
| Persistence after down / dashboard-only up | **58 original files unchanged**, including markers, quality and state |
| Output after restarting writers | **100 new prediction rows**; 3 new raw files, 3 feature files, 2 checkpoints and 2 prediction files |
| Container Streamlit AppTest | **PASS**, actual Model Pulse execution without exceptions, refresh disabled for one bounded render |
| Diff checks | `git diff --check` passed; approved plan and Architect transcript unchanged |

Native tests used Python **3.13.2** on macOS arm64 and pytest **9.1.1**. The image
uses Python **3.12** slim. Both environments resolved pandas **3.0.6**, NumPy
**2.5.3**, scikit-learn **1.9.1**, joblib **1.6.0**, Streamlit **1.64.0**, and Altair
**6.3.0**. Container dependency installation used ARM64 wheels. Docker Engine
**29.7.2**, Docker Desktop **4.88.1**, Compose **5.4.0**. No dependency constraints
or atomic-publication changes were needed to pass the approved gates.

A preceding isolated Docker run also passed (79 unchanged files, 150 new prediction
rows). During that run, **Builder browser inspection** observed Model Pulse with
700 feature rows, 0% drop rate, 54% late-flag rate, and rendered volume/late-flag
charts without an exception. This is agent verification, **not student evidence**.
The final gate reran after strengthening new-file prediction checks and adding
host HTTP verification. Both successful projects' disposable containers, volumes
and image tags were removed.

Initial setup attempts were blocked by dependency-network and Docker cache/socket
permissions; those were resolved before the passing runs. Live polling sometimes
caught training state changing between reads and retried within the fixed deadline;
checks with writers stopped passed. This is consistent with the documented
non-atomic handoff limitation, not proof of crash safety. AppTest and Builder browser
inspection do not replace the student's personal demonstration.

### Initial student manual smoke test — functionality passed; shutdown failed

The student personally completed the approved manual smoke test before Tester.
The following are **student-reported observations**, separate from Builder's
agent verification above:

- All five services started; dashboard was healthy; runtime was `aarch64`.
- The dashboard rendered data and prediction charts. Artifact validation passed.
- With writers stopped, there were **10,550 feature rows and 10,550 prediction rows**.
- The baseline saved **1,221 artifact checksums**. After removing containers and
  recreating only the dashboard, verification reported:
  `PASS: 1221 original files survived container recreation unchanged`.
- After restarting workers, the check found **3 new raw files, 3 new feature files,
  1 new checkpoint, 1 new prediction file, and 50 new prediction rows**.
  Both artifact validation and the new-prediction check passed.
- Containers were subsequently stopped and removed, **retaining the data volume**.

**Functionality and persistence passed; clean worker shutdown did not.** During
`docker compose stop`, all four workers took approximately 10 seconds and exited
with **137**, while dashboard exited with **0**. Successful data checks do not
make these forced worker exits acceptable. The original Builder Docker gate above
did not inspect stopped-container exit codes, so its historical PASS is not
shutdown evidence. The Builder follow-up below reproduced and addressed this separately.
The student's retained smoke-test volume and original manifest must be preserved;
do not overwrite that baseline or run `down --volumes` against that project.

**Open issue for independent Tester — dashboard wording (not fixed here).** With
zero field failures after preprocessing completed, the student saw
“order_id causes the most preprocess failures” and “waiting for preprocess”.
Inspection points to `pipeline/dashboard/app.py`: `_failure_claim` treats a
nonempty all-zero ranking as a leading failure, and `main` uses the same waiting
message for both no quality records and completed batches with no failures.
Tester should distinguish those two states, check accurate zero-failure wording,
and verify that actual nonzero failure rankings still work. This note records the
issue; the independent Tester stage has **not** started.

### Builder shutdown follow-up and student recheck

The cause was Python running directly as **PID 1 without a SIGTERM handler** in
each worker. Container PID 1 does not take the ordinary default termination action
for that unhandled signal. Docker sent its normal stop signal, waited the existing
10-second grace period, then forced termination with SIGKILL (exit 137). This was
not an out-of-memory kill; dashboard already handled shutdown itself.

The small fix adds `pipeline/shutdown.py` and uses it in the four existing worker
loops. SIGTERM/SIGINT only set a stop flag; the active iteration finishes normally,
no next iteration starts, and polling checks the flag at most 0.1 seconds apart.
Handlers are restored when the loop exits. No signal handler raises through file
writes, and real worker exceptions still propagate. Compose's 10-second grace,
direct commands, storage, and dashboard behavior are unchanged. An iteration that
itself exceeds the grace period can still be killed; verification must report that
failure. This does not add atomic writes or crash-safe processing.

Builder's actual follow-up verification (separate disposable projects):

| Check | Actual result |
|---|---|
| Unchanged native baseline | `make test`: **56 passed** |
| Pre-fix reproduction, `dashbite-test-e415aed9b341` | All four workers were Python PID 1 with no caught SIGTERM; all exited **137**, `OOMKilled=false`; dashboard exited **0**. Whole Compose stop took **12.799s**, including CLI overhead around the 10-second grace timeout. |
| Fixed full suite | `make test`: **72 passed**; includes signals during in-progress iterations, real subprocess SIGTERM with a 60-second poll, handler restoration, and exception propagation |
| Fixed Docker gate, `dashbite-test-9de4c6a965b7` | **PASS**, `aarch64`; default/custom configuration, HTTP health, artifacts, rendered AppTest and same-image checks retained |
| Timed simulator stop | **0.450s**, exit **0**, no OOM kill |
| Timed preprocess/train/infer group stop | **1.704s**, each exit **0**, no OOM kill |
| Timed dashboard stop before recreation | **0.861s**, exit **0**, no OOM kill |
| Restart persistence and resumed output | **28 original files unchanged**; **200 new prediction rows** (5 new raw files, 4 feature files, 3 checkpoints, 3 prediction files) |
| Timed final five-service stop | **1.488s**, all exit **0**, no OOM kill |

The two disposable projects were removed with only their own volumes/image tags.
The student's retained project/volume was never mounted, modified or deleted by
this investigation. Architect transcript, approved plan and classroom attribution
are preserved. No changes have been committed or pushed, and Tester has not begun.

### Post-fix student manual smoke-test rerun — completed

The student personally completed the rerun after the shutdown fix, using project
**`dashbite-smoke-shutdown-20260930232346-29245`**. These are **student-reported
observations**, not another Builder automated run:

- All five services started; dashboard was healthy.
- After stopping writers, artifact checks passed with **4,250 feature rows and
  4,250 prediction rows**.
- Saved **479 artifact checksums**. After container recreation, verification
  reported: `PASS: 479 original files survived container recreation unchanged`.
- After restarting workers, verification found **18 new raw files, 18 new feature
  files, 15 new checkpoints, 15 new prediction files, and 850 new prediction rows**.
  Both artifact validation and the new-prediction check passed.
- The check initially printed `Waiting: invalid training state (117.0s left)`
  before succeeding. This is an observation for Tester to investigate, **not a
  confirmed diagnosis** of its cause.
- The final five-service stop took **12.930 seconds wall-clock**. All five
  containers reported **`status=exited, exit=0, OOMKilled=false`**.
- Containers were removed afterward **without deleting the volume**.

**Functionality, persistence, resumed output, and clean final exit statuses passed
in this rerun.** This differs from the initial run's four worker exits of 137.
However, the final wall-clock stop duration exceeded the previous under-10-second
expectation; the rerun must not be described as passing that timing expectation.
The Builder's shorter automated timings above are separate evidence and do not
replace the student's measurements.

### Remaining observations for independent Tester

- **Shutdown timing:** earlier worker-stop commands took **62.90 seconds** and
  **11.788 seconds wall-clock**, despite shorter Compose progress timings. The
  final five-service stop took **12.930 seconds**, with all exits 0 and no OOM kills.
  Investigate the difference between command wall-clock time, Compose progress
  timings, and container shutdown/grace-period timing. Review the Docker gate's
  whole-command under-10-second assertion against these measurements. The cause
  of the discrepancy is **unconfirmed**; clean exits do not resolve it.
- **Temporary training-state validation message:** investigate the exact
  `Waiting: invalid training state (117.0s left)` output before eventual success.
  Do not treat the message alone as proof of a race, corrupt state, or another
  specific cause. Preserve the successful final validation result alongside it.
- **Dashboard wording:** the dashboard showed a field-failure claim despite
  **zero field failures**. The earlier “order_id causes the most preprocess
  failures” / “waiting for preprocess” issue remains open as described above.

The post-fix personal rerun is **complete**, not pending. These review items remain
open; the independent Tester stage has **not** started. Both student smoke-test
volumes and their manifests must be preserved. This update records observations
only: no code changes, additional smoke-test run, commit, push, or transcript edits.

Existing limitations remain: shared CSV/checkpoint writes are not atomic, a crash
can leave partial files/state, and exactly-once processing is not guaranteed.
Training rereads growing history; there is no retention. Random live batches can
occasionally be unsuitable for training. The tests use fixed two-class data;
the manual demo uses batch/threshold 50. Dependency lower bounds remain open-ended;
resolved verification versions are evidence, not a lockfile.

### Independent Tester/Reviewer evidence — 2026-10-01

The independent review is documented in [docs/reviewer.md](docs/reviewer.md),
including severity-ranked findings, source references, limitations, and exact
fresh-project rerun commands. This is **automated Reviewer evidence**, separate
from the completed student smoke tests above; no subsequent personal test is claimed.

- Baseline: **72 passed**. Final full suite: **90 passed**. An environment-override
  run before the last event-query regression had **89 passed**, without creating
  the unused root.
- Fixed dashboard wording for empty results, completed zero failures, and actual
  failures; added real Streamlit render tests. Improved training-state diagnostics
  and reproduced two valid-write/read-snapshot interleavings; neither establishes
  the cause of the historical student message.
- The Docker gate now records stop return codes, raw progress, all exit/OOM states,
  and daemon SIGTERM-to-die intervals separately from command wall time. The
  original **under-10-second command criterion and 10-second grace remain**.
- Default CLI verification encountered timeouts, including a 180-second
  `docker info` failure in `dashbite-test-463887592e89`. That project was separately
  stopped cleanly and its volume retained. These failures are not counted as passes.
- Using the installed `/Applications/Docker.app` CLI/plugin through temporary
  configuration, `dashbite-test-5a1b6f022deb` **passed** the full Docker gate:
  native ARM64, shared image, health/readiness separation, valid handoffs, rendered
  AppTest, **31 unchanged files**, and **50 new prediction rows**. Final stop was
  **0.754s**, all exits **0**, no OOM kills; daemon intervals **0.342–0.631s**.
  Its disposable resources were removed. This invocation does not resolve the
  historical timing discrepancy or change global Docker settings.

The plan, Architect/Builder transcripts, classroom attribution, and all earlier
README observations are preserved. Neither student smoke-test volume nor manifest
was mounted, changed or deleted. No changes were committed or pushed.

### Student active-browser shutdown failure — superseding the earlier coverage claim

The student subsequently tested project
`dashbite-review-student-20261001114554-29245` in a real browser with auto-refresh.
The empty and completed-zero-field-failure wording checks **passed personally**.
Shutdown **failed**: four workers exited 0, but dashboard received SIGTERM and
then SIGKILL **10.043s** later, exiting **137**, with `OOMKilled=false`.
Reviewer read-only inspection of the still-stopped containers confirmed those
states. The attached event log provides direct forced-termination evidence;
this failure is not explained away as CLI overhead.

The earlier automated PASS remains a record of what was actually tested, but
it **did not cover shutdown with an active browser/auto-refresh session**. HTTP
health did not start a script session, and the old AppTest disabled auto-refresh.
The Reviewer reproduced exit 137 in a separate disposable project and captured
the script thread blocked in the dashboard's `time.sleep(15)` while Python waited
for that thread during shutdown. A stop late in that sleep passed, explaining
why an untimed stop can miss the defect. This does not diagnose the older,
clean-exit wall-clock observations.

The fix uses `st.fragment(run_every=15)` for Model Pulse while auto-refresh is
checked, or no periodic rerun when unchecked. It releases the script thread
between refreshes rather than sleeping through shutdown. Streamlit's minimum
version is now 1.37, which introduced the stable fragment API; no timeout,
exit-code assertion, or Compose grace period was relaxed. Native regression
coverage now requires an auto-enabled render to complete within five seconds
and exercises the checkbox off/on.

Use **`make docker-verify-browser`** for browser-session shutdown coverage. It
runs the existing isolated gate and pauses twice with a URL: open/reload it in a
real browser, keep Auto-refresh checked, observe two automatic updates, and type
`browser-verified` within 180 seconds. Leave the tab open through each stop.
This is an observer-assisted check, not a claim that HTTP or AppTest proves a
browser lifecycle. Missing/expired confirmation fails. Plain `make docker-verify`
retains its automated checks and explicitly reports active-browser shutdown as
NOT VERIFIED. The gate's AppTest now also runs with auto-refresh enabled.

The follow-up automated results and targeted personal rerun are recorded in
[the review follow-up](docs/reviewer.md#dashboard-shutdown-follow-up--2026-10-01).
All earlier observations/transcripts are retained; no student volume was mounted
or changed. No personal test of this latest fragment fix has yet been claimed.

Follow-up actual results: native baseline **90 passed**, final full suite
**95 passed**. Real-browser dashboard stops passed with empty data (**1.467s**)
and populated data during a five-service stop (**2.683s**); all exits in those
checks were 0, with no OOM kills. The new browser-assisted full gate in
`dashbite-test-89a9efbb1de3` verified **545 unchanged files**, resumed predictions,
and live automatic updates before and after recreation. Dashboard stops were
**0.993s** and **1.550s**, exit 0/no OOM. **That overall gate nevertheless FAILED**:
inference independently exited 1 with `EOFError` while loading a checkpoint
during the browser observation. All exit statuses were exposed and the failed
review project/volume retained. This additional shared-file issue is recorded
in the report; no checkpoint redesign or relaxed criterion was added to this
small dashboard fix. The dashboard-only investigation project was cleaned up.
