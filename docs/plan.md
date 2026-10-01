# DashBite — living plan

Classroom handoff for Architect → Implementer → Reviewer. Stages are appended below; do not wholesale-overwrite earlier sections.

## Wrap-up — Run the full stack

### Goal
Run simulator, preprocess, train, infer, and Model Pulse as durable background jobs via the Makefile.

### Architecture / boundaries
- Public interface: `make run`, `make status`, `make stop`
- Implementation helper: `scripts/pipeline_bg.sh` (nohup + PID files + log redirection)
- Foreground single stages remain: `make simulator|preprocess|train|infer|dashboard`
- Default poll cadence: `POLL_INTERVAL_SECONDS=15`
- Dashboard: http://localhost:8501 (Model Pulse only)

### Manual Smoke Test

#### What we're proving
The full pipeline stays up in the background, writes through `data/raw` → `data/features` → `data/predictions`, and Model Pulse updates on :8501.

#### Terminal
```bash
make run
make status
# optional live logs:
tail -f .logs/simulator.log .logs/preprocess.log .logs/train.log .logs/infer.log
# or open http://localhost:8501
```

#### Watch for
- `make status` shows UP for simulator, preprocess, train, infer, dashboard
- New files under `data/raw/`, then `data/features/`, then `data/predictions/`
- Model Pulse at http://localhost:8501 (volume / scores / failures)
- Logs under `.logs/`; PIDs under `.logs/pids/`

#### Stop
```bash
make stop
make status   # expect DOWN
```

---

## IDS706 Final — Repository B, Option 1: Extend and Containerize DashBite

### Status and goal

**Approved for Builder implementation.** The student has approved the containerization plan, including the two small verification helpers and the student-operated manual smoke test. Implementation, automated testing, and the student's manual smoke test are still pending. Repository inspected at commit `64e3a1f18b6766a9c5aea39fc8d37696908aa5c8`. This section proposes future work; no container files, application changes, or tests have been implemented or executed at this stage. Preserve the classroom plan above.

Run the existing five-stage application locally on an Apple Silicon Mac with Docker Desktop, using one image and one persistent shared volume. Keep the native Python workflow working. No Kubernetes, cloud deployment, extra infrastructure, multiple replicas, or ML redesign.

Handoff: student approval complete → Builder/Implementer (pending) → student performs the manual smoke test below (pending) → Tester/Reviewer (pending). The classroom `docs/dev-cycle.md` calls the final role Reviewer; the student's Tester stage should receive the same plan and smoke-test evidence.

### Repository findings: existing behavior versus proposed changes

Inspected `README.md`, this plan, `docs/dev-cycle.md`, `docs/docker-k8s-guide.md`, `Makefile`, `requirements.txt`, `pytest.ini`, `scripts/pipeline_bg.sh`, all pipeline stage modules, dashboard loaders/metric helpers, and the unit, regression, integration tests and their fixture interfaces.

| Area | Existing behavior | Proposed change |
|---|---|---|
| Launch | `make run/status/stop` uses background host processes, PID files and `.logs/`; no Dockerfile or Compose configuration | Add separate `docker-*` Make targets and five Compose services; preserve native targets |
| Paths | `pipeline.paths.data_root(base)` returns `(base or PROJECT_ROOT) / "data"`; stage functions accept an optional project `base` | Resolve `DATA_ROOT` centrally without changing explicit `base` semantics |
| Dashboard | Loaders already use shared path helpers, but `main()` explicitly passes `PROJECT_ROOT`; refresh is 15 seconds | Remove the explicit root from normal loader calls so the environment applies; retain loader `base` arguments for tests |
| Configuration | Python defaults: threshold 2000, batch 50, poll 15 seconds, seed 42, corruption 0.25; Makefile overrides threshold to 50 and batch to 20 | Preserve Python defaults and frozen config shape; Compose defaults match the Makefile demo, with documented overrides |
| Handoffs | Raw `orders_*.csv` → `features_*.csv` plus `.done_*` markers and `quality/batch_quality.csv` → model/checkpoint → predictions | Keep names, schemas, markers and module boundaries; move their common root only |
| Training/inference | Train writes timestamped `checkpoint_*.joblib`, `metrics_*.json`, `train_state.json`; infer selects newest checkpoint by filename and skips previously scored IDs | Preserve independent processes and existing state behavior across container recreation |
| Monitoring | Streamlit Model Pulse reads features, predictions and quality; existing “Samples scored” metric actually counts feature rows | Add dashboard HTTP availability check; verify prediction files separately and do not treat that metric as proof of inference |
| Tests | Existing tests mainly use `base=tmp_path`; dashboard integration checks metric helpers rather than actual application loaders | Add environment-path coverage, actual loader coverage, full handoff verification and an explicit Docker verification gate |

### Requirements and acceptance criteria

1. **Small local stack:** `docker compose config` resolves exactly `simulator`, `preprocess`, `train`, `infer`, `dashboard`; all use the same built image, each with its own existing entry-point command. One instance per service; native ARM64 build on the student's Mac, without forcing `linux/amd64` emulation. Record actual build/runtime architecture during implementation verification.
2. **Correct paths:** when neither `base` nor `DATA_ROOT` is supplied, all helpers retain `<project>/data`. Explicit `base=tmp_path` still means `tmp_path/data` even when the environment is set. With no explicit `base`, every stage and dashboard loader uses the chosen environment root, including quality, marker and training-state files. No accidental extra `/data` suffix.
3. **Persistent and isolated storage:** one Compose-project-scoped named volume mounts at the same absolute `DATA_ROOT` in all five services. A root override changes both the environment and mount target. `down` followed by `up` with the same project name/root retains old artifacts and processing state. No host `./data` bind mount or fixed global volume name.
4. **Usable dashboard:** bind Streamlit to `0.0.0.0:8501` inside its container; publish only dashboard HTTP to `127.0.0.1:${DASHBOARD_PORT:-8501}` on the Mac. Docker reports dashboard `healthy` when its HTTP probe succeeds; a browser shows Model Pulse without an exception and reads the shared data.
5. **End-to-end evidence:** within a bounded smoke-test window, fresh raw and feature rows, a loadable model checkpoint, metrics/state, quality records, and nonempty valid predictions exist. Predictions reference feature order IDs and saved checkpoints. After restart, old artifacts are unchanged and new output appears. Dashboard health alone does not satisfy this criterion.
6. **Regression safety:** the complete existing pytest suite plus added path/loader/handoff tests passes. Docker build, shared-image configuration, availability and persistence checks are separate explicit acceptance gates; absent Docker must be reported as not verified, never counted as a pass.
7. **Reproducible instructions:** README describes native versus container workflows, configuration/default differences, setup/build/start/logs/status/stop, isolated smoke testing, health limitations, persistence and deliberate cleanup. Make targets expose the same commands. Report actual commands/results and any limitations; do not claim this proposal has passed them.

### Design decisions and interfaces

**Central path contract.** Keep `pipeline.paths` as the single resolver, evaluated when called rather than cached at import. Precedence: explicit `base` → `base / "data"`; otherwise nonblank `DATA_ROOT` → that data directory itself; otherwise `PROJECT_ROOT / "data"`. Treat unset/empty/whitespace-only values as the default. Expand `~`; interpret relative environment paths relative to `PROJECT_ROOT` for stable native behavior across working directories. Compose requires an absolute Linux container path (such as `/app/data` or `/tmp/dashbite-smoke-data`), not a macOS host path. Document that distinction. Preserve `Config`/`DEFAULT_CONFIG.to_dict()` as-is: a second root stored in `Config` would create two sources of truth and break the frozen-config regression unnecessarily.

**Packaging.** Use the guide's Python 3.12 slim starting point and a single-stage image, `/app` working directory, the existing requirements, `PYTHONPATH=/app` and unbuffered Python logging. Copy only needed application code, dependency metadata, and the two planned smoke-test helpers listed below into `/app/scripts/` so the documented commands run in the shared image. Exclude `.git`, `.venv`, host `data/`, `.logs`, caches, secrets such as `.env`, and test artifacts with `.dockerignore`; do not bake models or generated data into the image. Initially retain the existing dependency file (including pytest) to avoid an unrelated dependency split. Its open-ended lower bounds and Streamlit/Altair API compatibility are build risks: record resolved versions, verify ARM64 wheels, and propose narrowly justified constraints if the build or suite exposes a problem.

**Compose.** Add `docker-compose.yml` as in the guide, share the build/image/environment/mount configuration, and use these commands:

| Service | Command |
|---|---|
| simulator | `python -m pipeline.simulator` |
| preprocess | `python -m pipeline.preprocess` |
| train | `python -m pipeline.train` |
| infer | `python -m pipeline.infer` |
| dashboard | `streamlit run pipeline/dashboard/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true` |

Use an image tag scoped to the Compose project, e.g. `${COMPOSE_PROJECT_NAME:-dashbite}:local`, shared by every service. Allow Docker to select the native platform. Keep volume key `dashbite-data` without an explicit global `name` or `external` setting, so the project name isolates smoke runs. Use `${DATA_ROOT:-/app/data}` consistently for environment and mount destination. Pass all five existing numeric settings explicitly with documented defaults (threshold 50, batch 20, poll 15, seed 42, corruption 0.25), alongside `DATA_ROOT`. Do not add a top-level fixed project name or container names that defeat isolation.

No dependency-order chain is required: polling stages already tolerate missing inputs, and inference waits for its first checkpoint. Starting the dashboard does not require a trained model. Prefer no automatic restart policy for this small assignment so crashes remain visible; this deliberately differs from the guide's simulator `unless-stopped` example. Use direct process commands with normal Compose stop behavior and a modest stop grace period. Mount the dashboard's data volume read-only because its loaders only read; the four pipeline stages share read/write access.

**Health check.** Define a dashboard-only Compose healthcheck using Python's standard-library HTTP client against `http://127.0.0.1:8501/_stcore/health` (no extra curl package in the image). Proposed interval 10 seconds, timeout 3 seconds, start period 20 seconds, retries 3. Success means Streamlit responds successfully; it does not prove script rendering, fresh data, model readiness, prediction correctness, or worker health. Browser inspection and artifact checks remain required. A worker crash may coexist with a healthy dashboard, and unhealthy status alone does not restart a container. Endpoint reference: [Streamlit Docker guide](https://docs.streamlit.io/deploy/tutorials/docker).

**Make interfaces.** Add `docker-build`, `docker-up`, `docker-status`, `docker-logs`, `docker-stop`, `docker-down`, and `docker-verify` to `.PHONY` and help. Map to Compose build, detached up, ps -a, logs -f, stop, down without volumes, and the bounded container verification respectively. Docker targets must not depend on native `install`, `run`, `stop`, or `clean-data`. Honor `COMPOSE_PROJECT_NAME`, `DATA_ROOT`, `DASHBOARD_PORT` and existing tuning variables. Preserve existing native targets and make defaults. Do not add a broad destructive cleanup shortcut; document deliberate project-specific cleanup separately.

**Alternatives and risks.**

- Named volume chosen over host bind mount: protects existing data and avoids Mac host-path/permission coupling, at the cost of inspecting files through a container. Data is persistent but is not a backup; `down --volumes` or volume pruning can destroy it. [Docker down reference](https://docs.docker.com/reference/cli/docker/compose/down/).
- One image chosen over five: smaller maintenance surface and identical dependencies, at the cost of shipping ML dependencies to the dashboard too.
- Shared CSVs retain known concurrent read/write hazards even with one process per stage; writes are not atomic in the classroom implementation. Restart can encounter a partially written CSV/checkpoint or partially completed marker/quality update. This plan does not promise crash-safe exactly-once processing. Exercise orderly stop/restart; if reproducible races block that acceptance gate, report them and review a small atomic-publication fix rather than silently expanding scope.
- Training rereads accumulated features and data grows without retention. Keep demonstrations short; no retention service or database is proposed. Random live batches are not deterministic (the simulator ignores the training seed for generation) and unusually small/single-class samples can fail training. Use batch 50/threshold 50 for smoke testing; use fixed two-class fixtures for automated tests.
- Preserve polling and the dashboard's independent 15-second refresh; do not promise every chart changes each 2-second smoke-test tick. No GPU, scaling, scheduler or orchestration platform is needed.

### Relevant files for the later Implementer

| File/interface | Intended later work |
|---|---|
| `pipeline/paths.py` | Implement documented root resolution and preserve all helper signatures |
| `pipeline/dashboard/app.py` | Stop forcing `PROJECT_ROOT` in `main()`; test actual loaders with an environment root |
| `pipeline/config.py` | Preserve defaults and serialized shape; no duplicate data-root configuration |
| `pipeline/simulator.py`, `preprocess.py`, `train.py`, `infer.py` | Audit their existing helper calls; retain schemas, loops and train/infer independence |
| `Dockerfile`, `.dockerignore`, `docker-compose.yml` | New packaging, five service commands, shared image/volume, dashboard healthcheck |
| `Makefile`, `README.md` | Add Docker workflow and verification targets/docs while retaining native behavior |
| `tests/unit/test_stage0_config.py`, `tests/integration/test_stage0_paths.py` | Add resolver semantics/precedence/isolation cases |
| `tests/integration/` | Add environment-only full handoff and actual dashboard loader coverage |
| `tests/regression/`, `tests/fixtures/` | Retain existing golden/config/schema checks and deterministic fixtures |
| `scripts/check_artifacts.py`, `scripts/check_persistence.py` | Two small helpers for artifact validation and persistence evidence, specified below; implement later, reuse in `docker-verify` where useful, no general framework |
| `docs/docker-k8s-guide.md`, `docs/dev-cycle.md` | Classroom reference and workflow; no Kubernetes implementation |

Only `docs/plan.md` is authorized to change in this Architect stage. The table is a future-work map, not a statement of modifications already made.

### Automated testing and regression checks (after approval)

- **Unit:** unset/blank/absolute/relative/tilde root behavior; explicit `base` beats environment; all five subdirectories use the same root; repeated directory creation is safe. Test runtime environment changes to prevent import-time caching. Use `tmp_path` and `monkeypatch`, not the repository's real data.
- **Regression:** keep the frozen config dictionary, seeded generator fixture, preprocessing golden CSV, quality schema, checkpoint selection, probability bounds, train/infer import boundary, dashboard metric calculations, already-processed and already-scored no-op behavior. Preserve explicit-base behavior with an unrelated `DATA_ROOT` set.
- **Integration:** under a fresh environment root and without passing `base`, write a deterministic two-class raw batch, preprocess, train and infer using existing callable interfaces. Assert actual artifact locations, row/ID handoffs, quality/state, loadable checkpoint, matching checkpoint IDs, finite probabilities in [0,1], and no output at a sentinel default root. Call the dashboard's real feature/prediction/quality loaders against that root; metric-helper tests alone would miss the current `main()` issue. Cover the main loader wiring with a bounded Streamlit AppTest or mocked one-render path with auto-refresh disabled, avoiding its sleep/rerun loop.
- **Docker verification:** `docker compose config --format json` validates the resolved five commands, common image/mount/environment, localhost-only port and dashboard-only healthcheck. Build on ARM64. Launch a unique test project/volume/port, poll up to 120 seconds for valid artifacts, and fail on exited workers. Assert a loadable checkpoint and linked predictions, dashboard HTTP success and a rendered browser smoke check. Stop writers before recording checksums; perform down/up, assert old artifact checksums before restarting writers, then require newly generated output. Verify custom `DATA_ROOT` (not only the default). On an empty isolated volume, starting dashboard alone should still become healthy while pipeline readiness remains false. Do not force pipeline state into the dashboard probe.
- **Safety of the Docker helper:** unique `dashbite-test-*` project, no bind mounts or global volume names; timeout returns failure and prints service status/logs. Cleanup only resources created by that helper, never global prune or native `make clean-data`. Clearly report skips when Docker is unavailable. Keep normal pytest runnable without a Docker daemon.
- **Gates/evidence:** run `make test` (the full unit/regression/integration gate) after each changed implementation stage per README; later run `make docker-verify` separately. Record commands, versions, platform, pass/fail counts and limitations. The student performs the manual smoke test before Tester/Reviewer; neither helper existence nor successful HTTP alone constitutes end-to-end verification.

### Planned smoke-test helpers — Builder implements later

Move the reusable inline Python checks into exactly two small, clearly named scripts. These are proposed interfaces, **not existing scripts**. Use the existing Python dependencies and standard library; no new test framework, services or orchestration layer. Both run inside the shared image, use the configured `DATA_ROOT`, and print the resolved root, concrete file names, counts and readable PASS/FAIL messages. Exit zero only on success; return nonzero on failure. They must not start/stop containers, generate pipeline data, repair files or delete anything. The student controls each lifecycle step below. `docker-verify` may reuse these checks, but neither that target nor pytest replaces the manual smoke test.

| Planned helper command (inside container) | Contract and visible output |
|---|---|
| `python scripts/check_artifacts.py --wait 120` | Poll for at most 120 seconds for all required artifacts; validate their contents and relationships; print file/row counts, example paths, sample prediction rows and `PASS: artifacts and handoffs verified` |
| `python scripts/check_artifacts.py` | Same validation once, without waiting; use after writers stop for a stable inspection |
| `python scripts/check_persistence.py save` | Save relative paths and SHA-256 checksums of all existing artifact files under `DATA_ROOT` to `smoke-manifest.json`, excluding the manifest itself; print `PASS: saved N artifact checksums` |
| `python scripts/check_persistence.py verify` | Require a nonempty manifest; verify every saved file still exists with the same checksum; print `PASS: N original files survived container recreation unchanged` |
| `python scripts/check_artifacts.py --new-since smoke-manifest.json --wait 120` | In addition to normal validation, require new raw, feature, checkpoint and prediction files absent from the saved manifest; require nonempty new predictions with order IDs not present in the baseline prediction files; print new file/row counts and `PASS: new predictions appeared after restart` |

Preserve the original validation substance: nonempty raw and feature rows; `hour`, `is_peak` and order IDs in features; nonempty predictions with unique IDs drawn from features, finite probabilities in [0,1], binary labels and checkpoint IDs; a loadable checkpoint for each referenced ID with matching bundle ID and callable model interface; matching metrics JSON, valid training state referring to an existing checkpoint, preprocessing markers and nonempty quality records with positive output counts. Load only this run's generated checkpoints. Print representative prediction rows so the student can inspect actual output, not just a success label.

`save` is allowed only after writers have stopped and stable artifact validation passed. Refuse to overwrite an existing manifest rather than silently replacing the baseline. `verify` is read-only and must run before any writers restart. Treat manifest paths as relative to the selected root and reject paths escaping it. `--new-since` reads the baseline; it does not rewrite it. Mutable quality/state files may change after writers restart; their old checksums are checked only during the dashboard-only persistence step. All helper reads stay inside the selected root; no fallback to host project data.

Bounded polling must use a deadline, show what it is waiting for and never reset the deadline on a retry. A waiting check may retry incomplete live output within its deadline; a one-shot check must report an error immediately. Helpers do not certify worker process health: the student separately inspects `ps -a` and logs. On failure, stop advancing the smoke test, preserve evidence and diagnose; do not regenerate the baseline, delete data, or treat dashboard health as a substitute for a failed check.

| Example failure message | Student action |
|---|---|
| `FAIL: timed out after 120s waiting for predictions under <root>` | Inspect service status and infer/train logs; record failure rather than waiting indefinitely |
| `FAIL: invalid predictions in <file>: <reason>` or `FAIL: cannot load checkpoint <file>` | Preserve the named file and logs for Builder/Tester |
| `FAIL: manifest already exists` | Keep the original baseline; use a fresh isolated project for a new smoke run |
| `FAIL: missing or empty manifest` | Check project name, root and whether the save step succeeded; do not save a replacement after recreation |
| `FAIL: saved artifact missing: <path>` or `FAIL: checksum changed: <path>` | Do not restart writers; record a persistence failure |
| `FAIL: timed out after 120s waiting for new predictions since smoke-manifest.json` | Inspect restarted workers and retain the baseline and logs |

### Manual Smoke Test — student run after implementation, before Tester

**Run only after the Builder implements the Compose configuration and helper scripts.** The Builder must keep these commands aligned with the delivered interfaces. This is a student-operated live demonstration, not a pytest invocation. Run the numbered steps in order; continue only when each check succeeds. Allow at most 120 seconds for initial readiness and at most 120 seconds for resumed output. If a worker exits, record failure immediately even if the dashboard stays healthy.

#### 1. Prepare isolated data and personally start the stack

From the repository root, start Docker Desktop and use one terminal throughout. Keep its environment for recreation and cleanup. Port 18501 avoids the usual native dashboard port; choose another unused port if necessary. Never use host `data/` as a bind mount or run `make clean-data` or a global prune command.

```bash
docker version
docker compose version
export COMPOSE_PROJECT_NAME="dashbite-smoke-$(date +%Y%m%d%H%M%S)-$$"
export DATA_ROOT=/tmp/dashbite-smoke-data
export DASHBOARD_PORT=18501
export TRAIN_EVERY_N_EVENTS=50 BATCH_SIZE=50
export POLL_INTERVAL_SECONDS=2 CORRUPT_BATCH_RATE=0 RANDOM_SEED=42
printf 'Keep this project name: %s\n' "$COMPOSE_PROJECT_NAME"
docker compose config
make docker-build
make docker-up
make docker-status
```

**Expect:** exactly five services with one shared image; a project-scoped `dashbite-data` volume mounted at `/tmp/dashbite-smoke-data` in all services; host binding `127.0.0.1:18501`. This tests a nondefault root without touching existing native data. Services stay running; dashboard transitions from starting to healthy. Verify native ARM64:

```bash
docker compose exec -T simulator uname -m
```

**Expect:** `aarch64`. Build failures, an unexpected architecture or exited services are failures to investigate before proceeding.

#### 2. Personally inspect logs and generated output

```bash
docker compose logs --tail=30 simulator preprocess train infer dashboard
docker compose exec -T dashboard python scripts/check_artifacts.py --wait 120
make docker-status
```

**Expect:** logs for arriving orders, preprocessing, a trained checkpoint and scored orders. Initial `no checkpoint available yet — waiting` is normal. Read the helper's concrete file names, nonzero row counts and sample predictions. Expect `PASS: artifacts and handoffs verified` within 120 seconds and all five services still running. This validates raw data, features, quality, markers, model/metrics/state and predictions, not merely file existence.

For failure diagnosis, use:

```bash
docker compose ps -a
docker compose logs --tail=60 simulator preprocess train infer dashboard
```

Do not advance after a timeout, invalid artifact or exited worker. Keep these outputs for the Builder/Tester; no cleanup is required to diagnose a failure.

#### 3. Personally open and inspect the dashboard

```bash
curl --fail --show-error --max-time 5 "http://localhost:${DASHBOARD_PORT}/_stcore/health"
open "http://localhost:${DASHBOARD_PORT}"
```

**Expect:** successful HTTP response and DashBite / Model Pulse rendered without an exception, with feature volume and a late-flag chart after predictions arrive. Allow its 15-second refresh. Corruption is disabled for this smoke run, so zero drop rate/no field failures is expected. The existing “Samples scored” metric counts features; the helper's prediction rows provide separate inference evidence. A successful HTTP probe does not prove rendering or pipeline health. If the dashboard is still unavailable after the initial 120-second readiness window, record failure and inspect its logs instead of retrying indefinitely.

#### 4. Stop writers and save the persistence baseline

Personally stop incoming data, give downstream stages 10 seconds to catch up, then stop the remaining writers. Keep dashboard running for read-only inspection.

```bash
docker compose stop simulator
sleep 10
docker compose stop preprocess train infer
docker compose ps -a
docker compose exec -T dashboard python scripts/check_artifacts.py
```

**Expect:** four stopped workers, dashboard still running, and stable artifact validation PASS. The 10 seconds is a bounded catch-up allowance, not proof of correctness; the one-shot validation must still pass.

Save the checksums using a one-off container with the simulator service's writable mount:

```bash
docker compose run --rm --no-deps -T simulator python scripts/check_persistence.py save
```

**Expect:** `PASS: saved N artifact checksums`, with N greater than zero. This command runs only the helper, not the simulator loop. It writes only the manifest in the isolated volume; dashboard remains read-only. Do not run save again to overwrite the baseline.

#### 5. Remove and recreate containers; verify old files before restarting writers

```bash
make docker-down
docker compose ps -a
docker compose up -d dashboard
docker compose ps -a
docker compose exec -T dashboard python scripts/check_persistence.py verify
open "http://localhost:${DASHBOARD_PORT}"
```

**Expect:** no service containers immediately after down; only dashboard running after recreation; `PASS: N original files survived container recreation unchanged`. Historical data should still appear in the browser. Use the same project name and root and **do not add `--volumes`**. If the browser is starting, retry its health request within 120 seconds, not indefinitely.

**Do not restart writers until checksum verification passes.** This ordering proves that the original raw/features/model/prediction files, quality log, state and markers survived; new pipeline output cannot disguise data loss. A missing manifest, missing file or checksum mismatch is a failed smoke test.

#### 6. Personally restart writers and confirm new predictions

```bash
make docker-up
docker compose logs --tail=30 simulator preprocess train infer
docker compose exec -T dashboard python scripts/check_artifacts.py --new-since smoke-manifest.json --wait 120
make docker-status
```

**Expect:** new raw, feature, checkpoint and prediction files within 120 seconds; printed new prediction rows/IDs and `PASS: new predictions appeared after restart`; all five services running. Revisit the browser and observe refreshed data. The helper must show new predictions, not count the old ones again. Quality/state files may legitimately change now, so do not rerun the old full checksum comparison after restarting writers. Dashboard HTTP can remain healthy during worker failure and cannot override a failed artifact check.

#### 7. Stop, save evidence and optionally remove disposable data

```bash
make docker-stop
docker compose ps -a
make docker-down
docker compose ps -a
```

**Expect:** stop shows exited containers; down removes them and the project network while retaining the volume. Save the project name, architecture, log excerpts, artifact counts/sample rows, persistence PASS, new-predictions PASS and a Model Pulse screenshot for Tester. Automated pytest results are separate evidence and do not replace these personal observations. Host project `data/` was never mounted or modified by this workflow.

Optional **destructive cleanup of this disposable smoke project only**, after saving evidence, in the same terminal:

```bash
case "$COMPOSE_PROJECT_NAME" in
  dashbite-smoke-*) docker compose down --volumes ;;
  *) printf 'Refusing cleanup: not a smoke-test project\n' ;;
esac
unset COMPOSE_PROJECT_NAME DATA_ROOT DASHBOARD_PORT TRAIN_EVERY_N_EVENTS BATCH_SIZE
unset POLL_INTERVAL_SECONDS CORRUPT_BATCH_RATE RANDOM_SEED
```

Do not use `--volumes` for normal stop/restart or data you intend to keep. If the terminal was lost, recover the recorded exact project name and configuration before acting; do not guess or prune globally. On any earlier failure, the stop/down commands above can stop this isolated stack while preserving its volume for diagnosis.

### Classroom attribution and demonstration of additional work

`docs/docker-k8s-guide.md`, Part 1, already supplies the architecture: shared Python image, separate stage commands, configurable data root, shared named volume, Compose shape and single-writer caveats. The proposed Dockerfile structure and Compose service layout derive from it. `docs/dev-cycle.md` supplies the append-only plan, independent roles and manual smoke-test handoff; README supplies the full-suite regression gate. Present these as classroom foundations, not original design inventions.

The student's additional work will be demonstrated by the actual implementation and reviewable diff: completed container packaging; compatible root precedence including the dashboard's explicit-root fix; native Apple Silicon verification; consistent environment/mount overrides; dashboard-only availability healthcheck; isolated persistent-volume workflow; meaningful resolver/loader/end-to-end tests; Makefile/README integration; and recorded manual evidence of data, checkpoints, predictions, browser access and restart persistence. The extension implements and validates the guide's local proposal; it does not claim Kubernetes/scaling work or a novel ML algorithm.

### Approved decisions and implementation boundaries

The student has accepted the shared-image/five-service design, backward-compatible explicit-base and `DATA_ROOT` behavior, project-scoped persistent volume, and dashboard-only health check with separate end-to-end verification. The student has also approved the two small verification helpers and the student-run smoke-test instructions. Builder is the implementation role referred to as Implementer elsewhere in this plan.

Approved plan decisions: preserve explicit `base` precedence and the frozen config schema; use a project-scoped named volume rather than host data; use demo defaults in Compose while preserving native Python defaults; use dashboard-only HTTP health plus separate pipeline verification; expose dashboard only on localhost; and leave automatic restart disabled to make assignment failures visible. Retain the documented tradeoffs, particularly volume inspection through containers and the existing non-atomic file-write limitation. Dependency locking or atomic-write hardening should be justified by concrete verification findings, not added as an unbounded redesign.

**Plan approved; stop after this documentation update.** Only `docs/plan.md` has changed. Builder implementation, automated testing, and the student-operated manual smoke test remain pending. This approval record does not start implementation.
