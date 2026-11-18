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
