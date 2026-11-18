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
