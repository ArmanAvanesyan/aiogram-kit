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

## Fresh Linux verification and publication decision

The read-only [manual run 44054131749](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44054131749)
completed every build and all four paired benchmark groups. All nine downloaded
wheel hashes match the uploaded manifest. Its failed status is the correct
performance-gate result, not a build/infrastructure failure. Raw results are in
`linux-44054131749/`; the exact source commit, artifact ID and ZIP digest are in
`linux-run.json`. This run measures its recorded source commit; subsequent review fixes are
listed below and are not covered by these timings. Do not combine its Linux
samples with macOS.

| Companion | Linux Rust/Python CPU ratio | Publication decision |
|---|---:|---|
| Sentinel | 0.802 rate / 0.819 debounce | Withhold: both exceed 0.8; latency repeat spread |
| Cmds | 0.499 compiled batch | Withhold: compiled fake-I/O p95 +5.57%, confirmation repeat spread |
| Nav | 1.053 tracking | Withhold: CPU target missed |
| Idle | 1.058 activation/touch | Withhold: CPU and multiple latency targets missed |

`publication-verdict.json` is the consolidated decision. **None is ready to
publish.** Cmds is the closest candidate: the batching benefit is reproducible,
and small-call conversion overhead is corrected, but the remaining failures are
still failures. Sentinel's 19.79%/18.07% improvements must not be rounded into a
20% pass. Nav and Idle need larger useful native work per boundary crossing;
removing recovery, authorization or ownership validation is not an optimization.

The diagnostic cProfile files under `diagnostic-profiles/` explain the remaining
Nav/Idle CPU costs. They are explicitly not qualification timings. Nav still
spends substantial time in canonicalization, immutable JSON freezing and key/
coordination normalization outside the native helpers. The next native design
should batch validated state work while preserving exact fingerprints and full
backend/FSM recovery parity. Idle's claim latency also needs boundary-level work.
No ABI redesign or broader rewrite is approved for publication by these results.


## Review corrections — 2026-11-17

The review found and fixed five issues without relaxing publication gates:

1. Protocol metadata/order was not validated. Unknown package paths, repeated
   labels and thresholds/sample claims inconsistent with the actual comparator
   are now rejected before writing output or starting any benchmark.
2. Two processes could both observe an empty output directory and overwrite the
   same attempt. An exclusive owner file now reserves the directory atomically;
   a regression test forces the concurrent empty-check interleaving.
3. Comparator process status was ignored. Malformed/contradictory reports and
   process errors now withhold qualification and cannot produce a successful
   summary, even if a partial report says `qualified: true`.
4. Idle's fast encoder dispatched overridable methods on accepted `str`
   subclasses. The fast path now accepts exact built-in strings only; subclasses
   retain the original JSON encoding. Regression tests cover overridden methods
   and concatenation, alongside the existing Unicode cases.

5. An existing Cmds unit test enforced a 100 ms wall-clock budget while running
   under coverage. CI reproduced a 104 ms failure on Intel macOS. The same 100 ms
   wall-time budget now runs in the existing coverage-free performance suite using
   a monotonic clock. Unit tests check result independence deterministically.
   The native CPU/p95/stability thresholds are unchanged.

All nine completed paired comparisons were replayed from their retained raw
results. Every input hash, numeric comparison and failure list matches the
original verdict (`review-evidence-replay.json`). This is an arithmetic/evidence
verification, not a fresh timing run. **All four companions remain withheld.**
The reviewed Idle change needs fresh performance qualification before any release;
the original measurements remain attached to their exact original artifacts.
