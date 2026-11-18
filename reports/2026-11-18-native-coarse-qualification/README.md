# Coarse native qualification follow-up

All four Rust companions remain unpublished. No performance threshold or workload
has been changed. The exact protocol is retained with each run.

## Initial candidate: bdafaa1

[Run 44201860631](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44201860631)
uses installed artifacts, balanced serial Python/Rust/Rust/Python profiles, at
least 10 CPU repeats and 100 individual latency observations. Raw results,
artifact checksums and per-run provenance are under `linux-initial/`.

| Package | Fixed CPU Rust/Python | Outcome |
| --- | ---: | --- |
| Sentinel | rate 0.512; debounce 0.669 | measured gate passes |
| Cmds | 0.558 | confirmation p95/spread failures |
| Nav | 0.822 | CPU benefit under 20%; Redis p95 failures |
| Idle | 0.785 | claim and combined memory-track p95 failures |

These results authorize no publication. They show materially better CPU results
than the earlier small native boundaries, but three packages still fail the
complete performance gate. Failed measurements are retained rather than replaced.

## Follow-up candidate: 1e8794d

Adds portable thin LTO for Nav/Idle, preserves the runtime integer digit-limit
behavior in memoization, and projects admitted Idle claims in one native call.
[Run 44203774605](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44203774605)
completed with failures; raw data is under `linux-followup/`.

| Package | Fixed CPU Rust/Python | Remaining failures |
| --- | ---: | --- |
| Sentinel | rate 0.505; debounce 0.616 | none |
| Cmds | 0.487 | confirmation_hit/100 repeat spread |
| Nav | 0.831 | CPU benefit under 20%; both Redis p95 checks |
| Idle | 0.777 | deadline-claims, memory-track and Redis-track p95 |

A third candidate avoids copying a Nav intent already owned by that backend,
borrows Idle jobs during lease validation, and holds the same task-owned lock
without creating an unused JSON scope for queue-only operations. Nested ownership
and cross-backend scope suppression remain enforced. This is a distinct candidate;
unchanged Cmds/Sentinel measurements cannot erase their earlier failures.

## Functional verification

Local ordinary suites: Nav 493 passed, Idle 805 passed, Cmds 313 passed. The Rust
Idle format-three core corpus passed 343 tests against isolated real Redis;
Nav's Rust Redis recovery/dispatcher corpus passed 12 tests. Strict Pyright passed
for all three packages. Clippy and Rust unit tests passed for the modified native
cores. Additional native suites passed: Nav 141, Idle 46; combined Rust/Rust profile
127. Both standalone Python wheel installs and strict ABI3 audits passed. Qualification uses Linux artifacts; local tests
use separately built macOS artifacts and do not qualify Linux wheel correctness.

See [boundary design](../../docs/design/native-coarse-boundaries.md) for cache,
ownership, fallback and ABI constraints. Full platform CI remains a separate gate.
Wheel binaries are backed up outside Git under
`/Users/armanavanesyan/oss/own/aiogram-native-coarse-qualification-2026-11-18/`;
`linux-initial-retention.json` records every retained file and checksum.


## Third candidate: 568a847

[Run 44205487691](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44205487691)
is retained under `linux-third/`. All three selected CPU workloads now meet the
20% benefit requirement, but the complete gates still fail:

| Package | CPU Rust/Python | Remaining performance failures |
| --- | ---: | --- |
| Sentinel | rate 0.503; debounce 0.640 | none |
| Cmds | 0.517 | compiled confirmation/100 repeat spread |
| Nav | 0.763 | Redis no-op p95 1.145; memory and Redis repeat spreads |
| Idle | 0.757 | deadline-claims p95 1.115 |

Idle's earlier claim p95 regression fell from about 39% to 11%. This timing
candidate nevertheless has a separate Unicode defect: coarse claim projection
rejected surrogate-bearing opaque tokens. Platform CI caught it. The exact failed
log is retained as `unicode-regression-ci.log.gz` with a raw checksum. It is not
a releasable candidate, irrespective of timings.

## Unicode correction: 741cd73

Raw Python strings now cross the claim boundary losslessly. Ordinary URL-safe
tokens use the native encoder; exceptional strings use CPython's ASCII JSON
encoder before mutation. Materialized claims retain the original opaque token.
49 targeted tests passed, including the original surrogate-identity regression.

[Idle-only run 44206310842](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/44206310842)
measures the corrected artifact separately. It also failed; raw measurements and
exact artifacts are retained under `linux-unicode-fix/`. CPU ratio is 0.775777
(22.4% lower CPU); remaining failures are claim p95 1.128397, combined memory-track
p95 1.209590, and Redis-track repeat spread over 10%. Redis activation and no-op
p95 ratios are 1.008204 and 1.030666; Redis-track p95 is 0.973729, but that does
not waive its spread failure. Cmds and
Sentinel have unchanged code across these later candidates, so repeated
measurements do not erase their earlier instability or authorize publication.

Latest local verification additionally passed 471 native format-three core and
combined tests on real Redis, plus task-scoped queue-only lock regressions. The
Unicode-only correction was then checked with the 49-test native regression
corpus. Strict typing, lint, documentation and ABI3 audits passed. Full CI and
measured-host timing qualification remain distinct from these local checks.


## Final disposition

The implementation materially improves the selected CPU workloads, but it has
**not resolved all release gate failures**. All four companions remain unpublished;
no tags, native releases or publication jobs were created. PR #87 remains a draft.
No threshold, sample count, workload or evaluator was weakened.

Remaining work is end-to-end latency and reproducibility: Cmds compiled-confirmation
spread, Nav Redis no-op overhead/spread, and Idle claim/release plus combined-track
tails. Two instrumented local claim profiles are retained only as diagnostics;
they include fixture setup and must not be compared as qualification timings.
They identify the remaining per-claim Python/native transport and task-lock work;
they do not justify weakening ownership checks or replacing secure entropy.

Correctness is a separate gate: the Unicode regression was fixed and tested.
Latest platform CI must finish before merge or any claim of cross-platform
readiness. The local functional checks above are not a substitute for that CI.
