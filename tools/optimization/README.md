# Optimization evidence tools

These tools measure installed distributions and evaluate evidence. They do not
publish packages, change application configuration or deploy anything.

## Verify the tools

```sh
uv run --no-project --python 3.12 --with pytest --with pytest-asyncio \
  --with redis --with tomli pytest -q \
  -o asyncio_default_fixture_loop_scope=function tools/optimization/tests
uvx ruff check tools/optimization
```

The CI matrix runs CPython3.10,3.12 and3.14. The release artifact verifier requires
`tomli` on Python3.10; newer interpreters use `tomllib`.

## Installed-artifact measurements

Build and review the candidate base and native wheels in their owning repository.
Install the exact local artifacts into a fresh environment outside the checkout.
Keep their SHA256 manifests: qualification provenance uses the installed PEP610
archive digest and must match those independently reviewed release assets.
For local uv installs that omit the digest, the controller hashes the local wheel
only after matching every installed archive member against that wheel.
An index-only install without an archive digest can still be measured, but its
results cannot qualify a native release through this gate.

```sh
python3 tools/optimization/run_benchmarks.py \
  --python /tmp/candidate/bin/python --profile optimized \
  --package aiogram-nav --output-dir /tmp/nav-python-a \
  --redis-url redis://localhost:6379/0 \
  --driver-arg=--ages --driver-arg=50 --driver-arg=--skip-registry
```

Use `--profile native` for the matching companion; Python is the default engine.
Run at least twice per engine, serially, in a prespecified balanced order. Freeze
the drivers and all helper modules before the first run. The controller rejects
editable/source-shadowed packages, preimports the verified installed base/native
packages in an isolated interpreter, clears Python path overrides, fingerprints
all benchmark helper sources and checks reported engine/package/version. Every
result receives a unique run ID and artifact/driver provenance. No report alone
proves absence of host noise: review repeat spread and competing load.

`--quick` is exploratory. Run representative CPU workloads with at least10
independent samples and end-to-end latency workloads with at least100 individual
operations. Select CPU workloads before measuring rather than selecting a winning
subset afterward. Redis benchmarks use only dedicated test instances and owned
random prefixes; review each repository driver's options.

```sh
python3 tools/optimization/compare_results.py \
  --python /tmp/nav-python-a/aiogram-nav.json \
  --python /tmp/nav-python-b/aiogram-nav.json \
  --rust /tmp/nav-rust-a/aiogram-nav.json \
  --rust /tmp/nav-rust-b/aiogram-nav.json \
  --cpu-workload memory-track/50 \
  --latency-workload redis-dispatch-noop/50 \
  --latency-workload redis-dispatch-track/50 --output /tmp/nav-native-gate.json
```

The comparator requires matching base artifacts, native artifacts within the Rust
profile, driver hashes and runtime/host identities. Duplicate paths, contents or
run IDs, zero/fractional/infinite sample counts and non-finite metrics fail closed.
CPU improvement must reach20%; individual-operation p95 must not regress by more
than5%, and repeat spread over10% withholds qualification. Historical reports
without new provenance remain readable but cannot qualify through the current
stricter gate. Earlier Sentinel/Cmds reports already failed the CPU gate and no
native companion was published from them.

## State growth and artifact verification

`benchmark_state_growth.py --help` describes standalone Nav, standalone Idle and
combined public-API workloads. Instrumentation separates client calls and computed
RESP request bytes from Lua-internal commands. Tracemalloc is off by default;
traced profiles are separate diagnostics, not CPU comparisons. Defaults preserve
library capacity settings; `--receipt-limit` is an explicit stress-test override.
Hot state and retained cold evidence are reported separately.

`verify_native_artifacts.py --help` verifies an exact companion release directory:
matching project/version/tag, exact wheel-platform allowlist, ABI3, distribution
metadata, module placement and independent checksums. The legacy `publish-native.yml` remains a template; the active
package-specific publishers are `.github/workflows/publish-aiogram-*-native.yml`. Functional platform CI, clean wheel/sdist installs,
independent review and measured qualification remain separate required gates.

## Render the consolidated figures

```sh
uv run --no-project --with matplotlib python tools/optimization/render_summary.py \
  --output reports/2026-11-11-optimization-program/figures
```

This produces PNG/SVG and chart-data.json with input digests. Storage plots show
measured hot state and total retained JSON separately; old workloads are never
extrapolated beyond their measured checkpoints. The CPU chart does not substitute
for the latency, functional or artifact gates.

## Run the complete native qualification serially

`qualify_native.py` runs the four prespecified workload groups without parallel
builds/tests. Supply an isolated environment containing the reviewed local base
and companion wheels plus their declared Redis dependencies (`redis>=5.0.8,<8`).
Never install an unconstrained Redis client over those extra requirements.

```sh
python3 tools/optimization/qualify_native.py \
  --python /tmp/candidate/bin/python \
  --redis-url redis://127.0.0.1:6379/0 \
  --protocol reports/2026-11-17-native-qualification/protocol.json \
  --output /tmp/native-qualification
```

The output must be empty. The runner retains each attempt, freezes the protocol,
uses Python–Rust–Rust–Python order and returns nonzero when any performance gate
fails. Use `--package aiogram-cmds` to repeat the same predeclared workloads after
changing only that candidate. Keep the earlier failed evidence. Do not run builds
or other tests while timing, silently retry noisy runs or publish from CPU results
alone. Installed-wheel provenance, functional/platform tests and independent
release review remain required.

The runner validates the version-1 protocol before starting: known package IDs,
unique fixed Python-Rust-Rust-Python labels, nonempty CPU/latency workload lists,
and threshold/sample metadata matching the enforced comparator. It reserves the
output directory with an exclusive owner file so concurrent attempts cannot
reuse it. Comparator process errors or contradictory reports withhold qualification
and cannot produce a successful summary.

## Controlled scheduling and observational host evidence

Qualification can explicitly select a scheduling condition with
`--cpu-affinity auto` (Linux), or fixed comma-separated CPU IDs. Auto resolves
**once before any paired run**, selecting the lowest available physical-package,
core and CPU tuple when topology is exposed; otherwise it chooses the first
allowed CPU. Every Python/Rust subprocess receives the same resolved CPU set.
Unavailable/duplicate CPU IDs, missing scheduling support and an empty available
set fail before measurements. The parent controller's affinity is unchanged.
This pins the measured process; it does **not** reserve a physical core, move
Redis, isolate an SMT sibling, or exclude host/hypervisor competition.

The workflow input `cpu_affinity` defaults to `none`, preserving inherited
scheduling. A controlled experiment must explicitly select `auto` or CPU IDs,
retain the original protocol and declare that host condition before running.
`host-controls.json` records the request, deterministic selection and available
CPU set. Historical unpinned failures remain evidence; a newly pinned result
cannot erase their instability or by itself authorize publication.

Each driver also writes `<package>.host.json`: observations before/after the
whole driver of GC state/counts, process CPU/context switches/page faults, load,
CPU affinity/frequency and available Linux CPU pressure/cgroup counters. No
observer runs inside timed operations, and the controller does not disable GC,
change its thresholds, alter sample counts, filter observations, or tune clocks.
Unavailable OS counters are `null`; root cgroup counters may include other work
and are diagnostic observations, not proof that contention was absent.

The result and manifest distinguish host CPU count from effective affinity CPU
count. Qualification compares strict `measurement_controls` across every paired
run, including the controller source hash, actual affinity, enabled automatic GC
and unchanged GC thresholds. A changed affinity during a driver, missing controls, incompatible control
sets or changed controller source withhold qualification. Time-varying telemetry
is retained separately and is not falsely required to be identical. Historical
results without these controls remain readable but cannot qualify through the
hardened evaluator. Exact artifact and driver-provenance checks remain intact.

Cmds retains its already-collected individual latency observations alongside the
summary. When raw observations are present, the evaluator verifies their count,
positive finite values and exact p95 before evaluating the unchanged thresholds.
It does not trim tails, resample, or substitute batched latency for operations.

### Explicit stronger-sampling experiment

Historical qualifier defaults remain 10 Nav/Idle CPU repetitions, one additional
latency window and 1,000 Cmds individual latencies. An explicitly predeclared run
may select `--cpu-samples 30 --latency-windows 10
--individual-latency-samples 3000`. These are **increased** sample counts; they
supersede the earlier unchanged-count experiment only when selected explicitly.
The original protocol still requires its unchanged minima, balanced order and
20% CPU / 5% p95 / 10% repeat-spread limits.

Nav/Idle CPU and claim samples retain 100 operations per fresh fixture; additional
Redis and combined windows also use 100 operations each. Receipt age remains
50→150 within each applicable fresh window, rather than growing one fixture to
age1,050. All observations and end-exclusive window boundaries are retained;
failed or incomplete windows cannot be skipped or retried. `calls=100` remains
the CPU-window normalizer; `total_calls` and raw observation count report the
pooled operations separately. Cmds retains its stateless target/configuration
and unchanged 31 CPU trials; only its individual operation count increases.

`--redis-container-id` explicitly identifies the job's owned disposable Redis.
It requires client affinity and configures Redis once on a disjoint allowed
logical CPU, preferring a different exposed physical core. With unavailable or
shared topology, the logical-only fallback is recorded without an exclusive-core
claim. No available disjoint logical CPU fails before timing. Only selected
Docker identity/image/PID/CPU fields are inspected, never container credentials.
Configured CPU set and actual process affinity are verified before/after every
driver; identity or affinity changes fail rather than choosing another CPU.

The workflow's `robust_sampling` input defaults to `false`. Set it to `true`
with explicit `cpu_affinity=auto` (or IDs) to select 30/10/3,000 plus disjoint
Redis control. `host-controls.json` and schema-two paired measurement controls
record the selected counts and service condition. The evaluator verifies those
requests against actual CPU vector lengths, raw latency counts, fresh-window
bounds/ages and complete fixtures; all four equally undersampled reports cannot
qualify merely because their headers agree. Missing/duplicate/partial windows,
unequal observed sample counts, changed service controls and fabricated p95
summaries withhold qualification. Historical attempts remain retained; stronger
sampling and service pinning do not turn their failures into successes.

### Sentinel's independent latency phase

For a newly declared run, `--latency-windows 10` now also requests ten fresh Sentinel
middleware fixtures of **1,000 operations each**. Its default remains one. The
original full Sentinel CPU phase stays **15 × 50,000** operations; the latency
phase is explicitly separate, so its ten windows must not be confused with the
fifteen CPU samples or use a 1,000-call CPU normalizer. The observed-plan validator
binds both phases independently, checking the complete 10,000-observation vector,
distinct fixtures, 0→1,000 state windows and unchanged CPU dimensions. All first
observations and tails remain; an incomplete or failed fixture fails the run.
There is no new warmup, sleep, GC change, adaptive count or winning-window filter.

The workflow choice `native_package=sentinel-cmds` qualifies just those two
independent projects and labels its artifact accordingly. It does not rerun or
claim new measurements for already-qualified Nav/Idle artifacts. Existing reports
remain retained with their original controller/source hashes and conditions.

## Exact release qualification and publication guard

`prepare_release_qualification.py` validates a separately hashed, versioned
manifest under reports. It binds package source hashes, completed platform CI,
artifact/run ownership, exact files and all seven native targets before staging
the glibc x86_64 release wheel. It supports independent package subsets; it does
not rebuild native code or publish. The manual qualification workflow accepts
`release_manifest_path` and `release_manifest_sha256` for this mode.

`verify_release_readiness.py` rechecks the exact native set and SDK/native source,
verifies raw evidence hashes and recomputes the unchanged performance gate. Native
publishers invoke it before and after artifact handoff, bound to immutable source
SHA and their own versioned report. An unqualified companion cannot reach the
upload job merely by supplying a valid checksum. Python SDK publication remains
independent of the optional companion's gate.
