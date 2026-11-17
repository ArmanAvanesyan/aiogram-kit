# Native performance qualification — 2026-11-17

No native companion is approved for publication by the local evidence below.
The thresholds remain unchanged: at least 20% CPU improvement, no individual
operation p95 regression above 5%, and no repeat spread above 10%.

## Corrections

- **Sentinel:** frozen PyO3 classes avoid redundant borrow checking while the
  existing Rust mutexes continue to protect state. An experimental Python key
  cache was discarded because its overhead and retention were not justified.
- **Cmds:** immutable native snapshots retain up to 256 deterministic fingerprints,
  with an input-size bound. Keys include profile, locale, bot, scope and language.
  No delivery confirmations or mutable application state are cached. Loaded
  extension validation is cached once per process. Single payloads of up to ten
  commands use CPython's existing JSON/hash path to avoid conversion overhead;
  Rust is still required and verified before effects, and native failures never
  trigger fallback. Larger compiled batches use the Rust snapshot.
- **Nav:** a typed state/history boundary eliminates JSON serialization and
  reconstruction solely for crossing the extension boundary. Opaque history
  entries retain their ownership; counters preserve Python integer range.
- **Idle:** printable ASCII identifiers avoid general JSON encoding; Unicode,
  control characters and unpaired surrogates retain their original encoding.
- **Cmds/Nav/Idle:** fixed-size SHA256 hexadecimal encoding avoids general-purpose
  formatting without changing durable fingerprints or receipt identity.

These are local unreleased candidates. SDK versions and public storage formats
have not changed. Base-package changes require a new SDK patch release before
publication; existing PyPI versions must never be replaced.

## Local results

| Companion | Rust/Python CPU ratio | Result |
|---|---:|---|
| Sentinel | 0.862 rate / 0.929 debounce | CPU target missed; latency repeat spread |
| Cmds | 0.361 compiled batch | CPU target met; repeat spread and one fake-I/O p95 regression |
| Nav | 1.047 tracking | CPU target missed; latency/stability failures |
| Idle | 0.932 activation/touch | CPU target missed; claims/no-op latency and stability failures |

A ratio of 0.8 or less is required. Cmds' batch improvement includes memoization;
it is not evidence that Rust intrinsically outperforms an equivalently memoized
Python implementation. Small-call selection is explicit and size based.

`local-verdict.json` lists every failed gate. The complete paired results and
raw individual latency samples are retained under `attempt-1/` and `attempt-3/`.
`attempt-1` contains all four companions; `attempt-3` repeats Cmds after fixing
small-call regressions. `attempt-2` was cancelled after a preflight typing issue
and cannot qualify anything. It is retained rather than overwritten.

`protocol.json` fixes the original CPU and required latency workloads before the
full measurements. All additional individual latency workloads emitted by the
drivers are checked too. `artifacts.json` and `candidate-sources.json` describe
attempt 1; the corresponding `attempt-3-*.json` files describe the revised Cmds
candidate. Exact installed wheels, not editable sources, were measured serially
in Python–Rust–Rust–Python order against a disposable Redis 7 primary. The driver
also verifies installed files against wheel contents and records their hashes.

The first exploratory Redis test environment accidentally installed redis-py 8,
which is outside the declared `<8` range. Those failures are excluded. The
supported redis-py 7.4.1 reruns are recorded in `functional-tests.json`: Sentinel
395, Cmds 322, Nav 452 and Idle 743 tests passed. Native Nav's 88 boundary tests,
all four Rust unit suites, Clippy and strict source typing also passed locally.
The manual CI benchmark mode uses the declared Redis range explicitly.

## Reproduce and qualify on a dedicated host

Use `tools/optimization/qualify_native.py` as described in the shared tools
README. Output directories must be empty; previous evidence is never overwritten.
The **Shared optimization evidence tools** workflow has a manual
`native_package` selection. Choose `all` or a companion to build exact candidate
wheels, finish all builds before timing, and run the same protocol serially on a
fresh Linux runner. Failed gates keep the job failed and retain artifacts/results.
This workflow has no publishing permissions or publication step.

A faster CPU sample alone does not approve a release. Stable host evidence,
functional/platform CI, final versioned artifacts, isolated installs and the
independent release review remain required. Never lower thresholds, remove slow
workloads, hide failed attempts, or trade recovery/ownership checks for speed.
