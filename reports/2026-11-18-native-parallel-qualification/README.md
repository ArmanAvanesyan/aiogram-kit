# Parallel native performance follow-up

This phase implements package-specific fixes through separate agents, plus an
independent safety audit and a benchmark-reliability audit. All four Rust
companions remain unpublished. The unchanged original performance protocol is
identified by hash in `experiment-declaration.json`.

The controlled qualification will apply the same explicitly recorded CPU affinity
to every measured profile. This controls CPU migration; it does not reserve a
physical core or isolate background work. New telemetry is observational and runs
outside measured scopes. Thresholds, samples, workloads and GC policy are unchanged.
Earlier measurements and failures remain in the adjacent qualification reports.

Package changes and final functional/qualification evidence will be recorded here
after verification. No performance or release-readiness result is claimed yet.


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
