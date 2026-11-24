# Paired URL patch releases 0.3.3

Package source is frozen at `6bf56eb5ced318b3ca0f9d92bb6ab161bdcf2223`.
All 0.3.2 release artifacts and measurements remain unchanged. No gates are weakened.

## Artifact and installation verification

- Six independent distributions, 30 exact artifacts; all metadata/Twine checks pass.
- Seven platform wheels per native distribution; all 21 pass strict ABI3 audits.
- All 24 wheel archives pass CRC and RECORD hash/size checks.
- All 15 isolated SDK wheel/source/minimum, native-only and paired profiles pass.
- Exact candidate Nav/Idle wheels pass 156 memory integration, FSM, isolation and recovery tests across all four Python/Rust engine combinations. Redis cases are covered separately by full source CI.
- Source CI at `320a55207b5ff6ea0b022673bbcdae8fcdd9740d` passed all 14 workflows (250 successful checks, five intentional skips).
- `final-artifact-index.json` binds every filename/checksum, independently of the publishing allowlist.

## Performance qualification

The experiment declaration and exact CI artifact manifest were committed before timing.
All raw results, including failures, are retained. No unchanged candidate is rerun to select a pass.

Cmds run [45329822396](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/45329822396) is **held**: CPU ratio 0.555 and all Rust/Python latency ratios pass, but three latency workloads fail the unchanged 10% repeatability gate. The raw evidence remains under `shipping-qualification/native-qualification/aiogram-cmds/`.

Nav run [45330137949](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/45330137949) is **held**: CPU ratio 0.740 and all latency ratios pass, but Redis dispatch no-op and track workloads fail the unchanged 10% repeatability gate. All raw inputs are retained.

Idle attempt 1 failed a GitHub artifact metadata API request before timing. Its failed infrastructure job was retried with the original candidate and no discarded measurements. Attempt 2 **passed** all unchanged gates; the exact publisher verifier independently recomputed the pass. Both attempt artifacts are retained.

**Release decision: all six distributions remain unpublished.** Cmds and Nav need valid, repeatable qualification before their pairs can publish. Idle is qualified but blocked by the required Nav-before-Idle publication order. PR #92 remains a draft; no release tags were created. `readiness.json` remains fail-closed. No 0.3.3 tags or packages have been published.

The first Nav dispatch was cancelled by GitHub before timing because all packages shared a workflow concurrency group. The workflow now separates groups by package; the replacement Nav run is 45330137949. No measurements were discarded or repeated.
