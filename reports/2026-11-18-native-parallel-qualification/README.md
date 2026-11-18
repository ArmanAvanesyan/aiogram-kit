# Parallel native performance follow-up

This phase implements package-specific fixes through separate agents, plus an
independent safety audit and a benchmark-reliability audit. All four Rust
companions remain unpublished. The unchanged original performance protocol is
identified by hash in `experiment-declaration.json`.

The controlled qualification will apply the same explicitly recorded CPU affinity
to every measured profile. This controls CPU migration; it does not reserve a
physical core or isolate background work. New telemetry is observational and runs
outside measured scopes. The first experiment preserves thresholds, samples,
workloads and GC policy; later declared sampling revisions are recorded below.
Earlier measurements and failures remain in the adjacent qualification reports.

Final results below qualify all four exact candidates on the measured host and
workloads. This is performance qualification, not authorization to publish.


## First controlled candidate: f4567d1

[Run 44210106073](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44210106073)
used matched affinity CPU0 (one logical CPU from a four-CPU host), unchanged GC,
and the unchanged thresholds, samples and workload selection. Exact artifacts,
raw samples and pre/post telemetry are retained under `linux-initial/`.

| Package | CPU Rust/Python | Measured gate |
| --- | ---: | --- |
| Sentinel | rate0.527; debounce0.657 | pass |
| Cmds |0.562 | dynamic confirmation/1 p95 1.072; compiled/10 repeat spread |
| Nav |0.786 | pass |
| Idle |0.777 | deadline-claims p95 1.072 |

Cmds' compiled/10 spread failure was in Python (14,487 vs15,950ns, about10.10%);
Rust spread was about0.37%. Identical per-engine GC totals and low observed CPU
pressure do not establish full/heavy GC as the cause. No threshold is waived.
The next code candidate removes duplicate internal engine validation for dynamic
commands and redundant warmed imports for every Idle release.

Separate lifetime review found unused deferred Nav codecs self-retained through
bound methods and Idle lock/view cycles. Revoked copied contexts also retained
codec/owner references. GC-disabled weakref regressions are being added and these
issues will be fixed before any readiness claim, irrespective of these timings.
All four companions remain unpublished. Earlier failed measurements remain intact.


## Lifetime and tiny-call follow-up candidate

The follow-up removes Nav's self-bound cold-dispatch cycles, Idle's lock/view
cycle and inactive copied-context engine/task retention in both libraries.
Actual Nav lock ownership is tracked separately until release; clearing a revoked
codec record cannot prevent rightful release or authorize foreign tasks.
GC-disabled weakref tests prove immediate cleanup of scratch Redis engines,
unused/initialized codecs, cached keys and completed owner tasks.

Idle hoists a pure component-deadline dependency instead of importing it per
release (eight redundant imports in each claim batch). Cmds retains eager ABI
validation before callbacks but passes the resolved engine internally rather
than repeating validation and tiny-payload selection. Dynamic configuration,
translation and public malformed-input behavior remain tested and uncached.

Package checks before integration: Cmds352 ordinary tests; Nav508 ordinary,201
native/codec and12 native Redis tests; Idle116 targeted plus344 real-Redis core
profile tests. These counts overlap. Typing/lint are green; qualification of the
combined updated candidate is pending, with the same predeclared host controls.


## Second controlled candidate: 0c4e2a4

[Run 44212572066](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44212572066)
is retained under `linux-lifetime/`. All selected CPU ratios pass (Cmds0.555,
Nav0.790, Idle0.792), but this is still a failed qualification: Cmds has repeat
spread failures and fakeTelegram/100 p95 ratio1.100; Nav has Redis repeat spread
failures despite acceptable p95 ratios; Idle claim p95 is1.051464 with claim and
Redis no-op spread failures. Sentinel passes its measured gate. No rounding or
exception turns the marginal Idle failure into a pass.

Additional telemetry shows one Cmds profile's CPU pressure grew5.33seconds versus
about59milliseconds in its peer. This is host-queue evidence, not proof that
Redis or the library caused it. Default100-observation Redis rows are also sparse.

## Explicit stronger-observation revision

`robust-experiment-declaration.json` is declared before the next timing run. It
changes observation counts upward, transparently revising the earlier unchanged-
count experiment:30 fresh CPU/claim windows;10 fresh Redis/combined windows of
100operations each;3000 Cmds individual observations while keeping31 CPU trials.
Original state-age windows, workloads, thresholds, minimum10/100 requirements
and GC policy stay intact. All raw samples and window boundaries are retained,
including slow tails. Missing, failed, duplicate or undersampled windows cannot
qualify. CPU batch calls100 and pooled transport total_calls1000 are distinct.

The disposable Redis service is assigned a logical CPU disjoint from the client,
preferably a different exposed core. Actual masks, Docker/image/PID identity and
topology are checked before/after each profile. This claims no exclusive hardware
isolation and cannot eliminate hypervisor/background interference.

The same candidate also rearms owned native Idle jobs in place, reducing repeated
hashing/allocations without changing guards or cryptographic entropy.600compaction
cycles and4000mixed-operation reference traces preserve complete job/heap/counter
state. Corrupted internal identities now fail before mutation. No unsafe FFI or
insecure hasher was added.

Functional window/sampler tests use deterministic clocks/transports, not timing
claims. Root evaluator tests passed193 with1platform skip (Linux-only affinity
case onmacOS), with the same result from the owning agent onPython3.10/3.12/3.14.
Independent review verified actual-count/age binding and fail-closed service
controls. The stronger candidate remains unqualified until its own run finishes.


## First stronger-observation result: 0448d0b

[Run 44217592129](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44217592129)
is retained under `linux-robust/`, with disjoint verified client/Redis affinities
and every raw window. Nav and Idle pass all CPU, individual-p95 and repeatability
checks. Nav CPU ratio0.791572; Idle0.773369. Idle claim p95 is0.956376, versus
its original roughly1.39 regression. The independent native job-rearm optimization
therefore meets the claim gate without relaxing it.

Cmds CPU ratio0.501540 and all compiled/other latency rows pass, but live
confirmation/1 p95 ratio1.069504 and repeat spread fail. Its medians differ by
about1.6%; native-a has transient clusters, and available aggregate observations
do not establish their cause. A manager-owned validated engine binding is being
implemented to remove remaining repeated live-selection work, preserving public
engine reassignment and direct-API validation.

Sentinel CPU ratios0.488333/0.655300 and latency ratio0.721864 pass, but reference
repeatability fails: Python p9516.761→10.553microseconds versus native10.034→9.683.
The original1000-observation middleware phase spans onlyabout10–13milliseconds.
The next explicit declaration adds10fresh1000-operation Sentinel latency windows
while retaining its separate15×50000 CPU phase. No extra warmup or GC change
is introduced; cold samples and tails remain in every raw vector.

No package is published. Independent package qualification evidence is retained
for the exact Nav/Idle0448d0b artifacts; they are not resampled merely to replace
failed historical measurements. Remaining qualification focuses on Cmds/Sentinel.


## Final Sentinel/Cmds supplement

`sentinel-cmds-experiment-declaration.json` supplements the stronger protocol before
timing. Nav/Idle qualified artifacts remain unchanged. The Cmds live manager now
binds a validated engine/module pair at construction or validated reassignment;
failed reassignment is atomic, and public direct APIs keep eager ABI checks.
Configuration, translators, menus and confirmations are not implicitly cached.
379 installed-wheel tests passed before integration.

Sentinel adds10fresh1000-operation middleware latency fixtures. The existing
15×50000 CPU phase stays separate, with its own denominator and data. Every cold
observation and tail is retained; there is no new warmup, sleep, GC policy or
selection. Both old1000-observation and new10000-observation raw results remain
available. The latest helper/evaluator tests passed209 with1Linux-only platform
skip on each localPython3.10/3.12/3.14; separate Sentinel sampler tests passed2.
Independent review found no new effect, freshness or denominator blocker.

The same source update fixes Nav artifact-test helper staging and Cmds package
formatting, with preserved-input workflow-generator tests so regeneration cannot
restore the omission. Installed SDK tests still run without copying SDK source.

## Final measured result

[Run 44222753653](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44222753653)
qualifies Sentinel and Cmds at source `498fae6`. Complete raw observations,
host controls, provenance and gate reports are retained in `linux-sentinel-cmds/`;
the sibling retention manifest maps exact binary backups and original hashes.
Nav and Idle retain their independently qualified `0448d0b` artifacts from
run44217592129. No unchanged candidate was resampled to replace a failure.

| Package | Selected CPU Rust/Python | All required latency and repeatability gates |
| --- | ---: | --- |
| Sentinel | rate0.535; debounce0.666 | pass; middleware p950.937 |
| Cmds |0.508 | pass; worst required p951.036 |
| Nav |0.792 | pass |
| Idle |0.773 | pass; claims p950.956 |

The fixed thresholds remain CPU<=0.80, individual p95<=1.05 and repeat
spread<=10%. Increased observation counts were declared before timing; every
cold observation, tail and failed earlier run remains available. No GC change,
threshold waiver, favorable subset or automatic performance retry was used.

These are development candidates with paired SDK/native capability changes.
All four companions remain unpublished. Publication still needs a separately
authorized release with fresh matching versions, exact reviewed artifacts and
the complete platform/distribution gates. These results cover the recorded
Linux/Python3.12 host, not every supported platform or application workload.

## Final CI and packaging checks

The final workflow-only follow-up adds a missing `sentinel-cmds` selection guard
and a bounded60second pip-audit socket timeout after three checks failed on
PyPI read timeouts. Audits retain their ordinary failing exit status and scan
targets; no vulnerability ignores or fail-open retries were introduced. Workflow
regeneration preserves these changes and helper staging. Root integration tests
passed61; strict MkDocs build and root lint/format checks passed. Package-specific
installed-artifact and standalone verification records accompany this report.
No measured runtime/benchmark source changed after the qualifying artifacts.
