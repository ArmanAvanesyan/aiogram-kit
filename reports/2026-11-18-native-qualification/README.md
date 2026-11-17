# Native qualification follow-up — 18 November 2026

PR [#86](https://github.com/ArmanAvanesyan/aiogram-kit/pull/86) merged as
`b4c0e00aebc023f5472e72738a42eaccb652c365` after all required checks passed.
This follow-up preserves the existing 20% CPU improvement, maximum 5% individual
p95 regression and maximum 10% repeat-spread gates. No package publication,
release tag, gate waiver or dependency/version change is part of this work.

## Retained changes

- Sentinel uses borrowed single-lookup map entries with explicitly keyed
  `std::collections::hash_map::RandomState`; it does not switch to an unkeyed
  hasher. Debounce constructs/encodes its composite identity once in Python,
  retaining legacy colon aliases, custom string formatting and surrogate support.
  The final candidate borrows cached CPython UTF-8 for string keys rather than
  allocating a Python bytes object on every hot-path call. Surrogate encoding
  occurs before the native mutex and any business mutation. A shared validator
  also stops importing its error class per call and fast-paths ordinary valid
  integers; both Python and Rust use the same improved validation. Thin LTO and
  one codegen unit remain portable release settings; no host-specific CPU flags
  or unsafe hashing changes are used.
- Idle avoids a second native job snapshot after successful scheduling/release.
  Preserving a claimed job remains distinct from removing a deadline. Ownership
  errors still propagate before Python's key index changes. Printable ASCII
  tokens have a lossless inverse transport fast path; escapes, non-ASCII strings,
  subclasses and invalid encodings still use the original JSON decoder.
- Cmds and Nav keep their existing runtime implementations. Their previously
  failed gates are not reclassified as successful because helper benchmarks pass.

Regression tests cover key isolation/reset, composite-key helper interactions,
ASCII/Unicode/surrogate transport, malformed JSON, subclass accessors and queue
preserve/remove/release semantics without redundant job reads.

## Rejected traversal experiment

`exploratory/` retains raw measurements and source diagnostics for an experiment
moving canonicalization and JSON freeze/thaw traversal into Rust. Python's JSON
formatter remained authoritative, and native work was scoped to the actual backend
lock owner to prevent child-task engine leakage. The first 134 targeted tests
passed, but installed-wheel full CPU measurements did not justify retaining it:

| Workload | Python CPU/update | Rust CPU/update | Rust/Python |
| --- | ---: | ---: | ---: |
| Nav `memory-track/50` | 584.32 µs | 623.345 µs | 1.067 |
| Idle `memory-activate-touch/50` | 356.675 µs | 350.585 µs | 0.983 |

These are single exploratory runs, not qualification or a controlled before/after
comparison to the retained candidate. They ran serially on the development Mac,
which had unrelated background activity. The SDK/native wheel hashes are in
`exploratory/artifact-sha256.json`; exact wheels are backed up locally under
`/Users/armanavanesyan/oss/own/aiogram-native-qualification-2026-11-18/exploratory`.
The rejected source patch, common Rust traversal and task-scope module are retained
as diagnostics only; none is installed or imported by the final source tree.

The result argues against adding FFI crossings around small Python-owned records.
Nav and Idle need a separately reviewed, coarser native ownership boundary before
claiming the required end-to-end CPU improvement; rewriting a hash or JSON helper
alone is insufficient. Never slow the Python baseline or omit workloads to make a
native candidate qualify.

## Evidence runs

The unchanged protocol is copied into each run's directory. Runs use fresh local
wheels installed outside the workspace, Redis 7 in a disposable instance, and
Python–Rust–Rust–Python order. The controller verifies installed artifact contents
and hashes. Failed attempts are retained. Development-host noise is not evidence
that a failing result should pass.

- `local/`: first complete repeated attempt, Sentinel single-lookup change only
  (`c3634b1` equivalent runtime); before the subsequent debounce/Idle bridge changes.
  Installed wheels are backed up under the sibling `baseline` directory.
- Linux initial candidate: [run 44182873006](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44182873006), source `c3634b1`.
- Linux final runtime candidate: [run 44183752278](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44183752278), source `3280e52`.

- Linux owned-buffer candidate: [run 44185088670](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44185088670), source `39c928a`; Sentinel alone, failed debounce CPU (ratio 0.82877), rate CPU 0.76818, middleware p95 0.90050. All raw data are in `linux-owned-buffer/`.
- Linux final borrowed-text candidate: [run 44186483527](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44186483527), source `d54e64f`; Sentinel alone, identical predeclared workload selection.

Local artifact backups and JSON checksums establish test provenance, not a
publication manifest. Changed SDK/native code needs subsequent patch-version
alignment and the existing exact-artifact/platform review before a release;
never overwrite the already-published base versions.

## Functional verification

Installed-wheel suites on CPython 3.12 / aiogram 3.32.0 / redis-py 7.4.1:

| Suite | Passing tests |
| --- | ---: |
| Sentinel final text-key candidate | 384 |
| Cmds | 312 |
| Nav, including real Redis | 452 |
| Idle, including real Redis, recovery and FSM | 763 |
| Existing Sentinel/Cmds performance suites, unchanged budgets | 13 + 11 |
| Independent Nav/Idle native-wheel tests | 90 |

Rust unit tests and Clippy with warnings denied pass for all four crates (5/2/5/8
unit tests). Ruff and strict Pyright pass for changed SDK code. Base wheels were
built from their sdists; all four native sdists were created. Fresh separate environments
pass dependency checks and import their standalone base wheels with Redis, every
native companion and optional Nav/Idle peer absent; Idle also opens a memory
session with its standalone artifact. XML results and logs are in `functional/`.

An initial combined test invocation omitted Babel from the test environment and
overlapped a Cargo build with Cmds' legacy setup-size timing assertion. Both
failures are retained in `functional/initial-*`; installing the declared test
dependency and running the unchanged performance suite separately passed. This
retry is unrelated to native qualification: no failing benchmark attempt was
discarded and no threshold changed.

Main's two native macOS jobs could not acquire hosted ARM runners (runs
44178921941 and 44178921620). Their annotations explicitly report runner capacity;
failed jobs were resubmitted without replacing the platform or weakening checks.
Both reruns succeeded; all 14 main workflows at `b4c0e00` now pass, as recorded
in `main-checks-snapshot.json`.
PR platform checks remain a separate gate from local correctness/performance.
Strict ABI3 audits pass for all four local companion wheels. Temporary local Redis
containers are removed after their test runs; no application database is used.

Final gate and release decisions follow below.
All four Rust companions remain unpublished throughout qualification.

The additional Sentinel attempts are retained too:

- `linux-text-final/`, source `d54e64f`: rate CPU ratio 0.76326, debounce
  0.80184, middleware p95 0.89800. Debounce fails the 0.8 gate; rounding does not
  turn it into a pass.
- `linux-lto-final/`, [run 44188005318](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44188005318),
  source `a313e6e`: rate 0.73942, debounce 0.81202, middleware p95 0.93479;
  debounce still fails. The local extension size falls from 595,084 to 565,956
  bytes with Thin LTO; a smaller binary does not establish qualification.
- Final shared-validation candidate: [run 44189765647](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44189765647),
  source `ec151ef`. Both engines use the updated validator and fresh SDK wheels.
  The diagnostic in `exploratory/shared-validation.json` measures the helper only
  (0.107285 versus 0.025560 CPU seconds for 200,000 calls); it is not an
  end-to-end gate result.

Every follow-up follows an actual candidate source change. Earlier failed
attempts are not silently retried until a winner appears. Cmds' CPU result
includes its bounded native snapshot-hash cache; it is an implementation
comparison, not proof that Rust alone accounts for the improvement.

## Final decision

The unchanged gate qualifies **Sentinel's performance candidate only**. No native
companion is published and this is not a release-artifact approval.

| Package | Selected CPU result, Rust versus improved Python | Remaining performance gates |
| --- | --- | --- |
| Sentinel (`ec151ef`) | rate 0.51290, debounce 0.62465 (48.7% / 37.5% less CPU) | **Pass**; middleware p95 0.92139, all repeat checks pass |
| Cmds (`3280e52`) | compiled batch 0.52898 (47.1% less CPU) | confirmation p95 and repeat spread |
| Nav (`3280e52`) | memory track 1.05464 (5.5% more CPU) | CPU, memory/Redis-track p95 |
| Idle (`3280e52`) | activate/touch 1.07551 (7.6% more CPU) | CPU, activity/claim/noop p95, claim repeat spread |

Raw final Sentinel data are in `linux-validation-final/`. The combined lookup in
`readiness.json` links each package to its own complete paired evidence; it does
not splice samples from different candidates into a fabricated successful run.
The final shared validator passes Sentinel's complete 397-test suite, including
real Redis and the 13 unchanged performance tests. A fresh standalone base-wheel
check also passes with native and Redis absent.

**Remaining work, not reported as fixed:**

1. Cmds needs stable end-to-end tail evidence on a controlled runner, with the
   confirmation fast paths profiled separately from scheduler/GC effects. The CPU
   win does not waive small-payload latency failures. Retain prior failures and
   keep all current latency workloads; do not silently rerun until one passes.
2. Nav and Idle need a coarser native ownership boundary. Python-owned immutable
   model validation, canonical JSON and coordinator crossings still dominate;
   per-helper Rust conversion cannot establish the required full CPU gain. Review
   a fused transition/model-result boundary before another port, keep clocks,
   callbacks and effects in Python, and run existing state/wire/FSM/recovery parity
   suites against any replacement. The rejected traversal prototype is evidence
   against shipping additional complexity without a measured workload benefit.
3. Sentinel can proceed to **release preparation**, not publication: align its
   future SDK/companion patch versions, verify the full platform matrix and review
   the exact release artifacts/manifests. Current wheels are development evidence
   with existing checkout versions; they must not overwrite published SDK versions.

PR [#87](https://github.com/ArmanAvanesyan/aiogram-kit/pull/87) remains a draft while
platform CI completes and the remaining performance failures stay visible. No
native tags, PyPI upload or GitHub release is created. Temporary local Redis
containers and their anonymous volumes are removed, and Docker is returned to its
previous stopped state.
