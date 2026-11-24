# Paired Cmds, Nav and Idle 0.3.3 release qualification

All three pairs pass the original CPU <=0.80, individual p95 <=1.05 and repeat spread <=10% gates. No thresholds, workloads, GC policy or ABBA order changed. All shipping artifacts are the original reviewed files from source `6bf56eb5ced318b3ca0f9d92bb6ab161bdcf2223`.

| Pair | CPU Rust/Python | Qualification |
| --- | --- | --- |
| Cmds | 0.515 | [Controlled runner proof](../2026-11-24-cmds-isolation-0.3.3/) |
| Nav | 0.761 | [Longer fixed-age window proof](../2026-11-24-repeatability-0.3.3/) |
| Idle | 0.779 | [Original passing proof](../2026-11-24-url-patches-0.3.3/) |

Cmds required removing owned runner-thread contention from the client core and normal CFS nice -20, after localized tail spikes correlated with host CPU pressure. All four measured profiles confirm priority -20 and fixed client CPU 0; housekeeping threads use CPUs 2/3. Its worst latency repeat spread is 2.50% and maximum Rust/Python p95 ratio is 1.009. Nav's previously failing Redis spreads are at most 3.37% after increasing fresh fixed-age windows from 10 to 100. These are results for the recorded hosts/workloads, not universal speedup claims.

All earlier failed measurements, including the extended Cmds failure, are retained. The two unmeasured infrastructure/setup failures have retained log/artifact hashes. There were no unchanged reruns to select passing measurements. Each changed experiment was committed before timing.

## Artifact and install verification

- 30 artifacts across six distributions, correct versions and monorepo URLs.
- All 21 native wheels pass strict ABI3 audits; all 24 wheels pass CRC and RECORD checks.
- All 15 isolated minimum/latest SDK, SDK source, native-only and paired install profiles pass.
- All three native source archives independently build and install without SDK/aiogram dependencies.
- 156 optional Nav/Idle memory, FSM, isolation and recovery tests pass across all four Python/Rust engine combinations; full source CI covers real Redis separately.
- All 14 project URLs resolve; no Redis or navigation dependency is introduced into standalone profiles.

The per-package publishing workflows point to the matching independent report in `release-readiness.json`. Each publisher recomputes the gate from retained raw data and checks exact source and shipping artifact digests before OIDC publishing. SDKs publish before their native companions, and the complete Nav pair publishes before Idle. Final PR and release-source CI are still required before publishing.

Historical initial holds in the earlier reports describe those experiments; this rollup supersedes their overall release decisions without rewriting raw evidence.
