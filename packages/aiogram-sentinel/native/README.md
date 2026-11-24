# Paired 1.3.2 release candidate

This candidate requires `aiogram-sentinel==1.3.2` when used with the SDK.
It is unpublished. See the monorepo paired-release readiness report for exact
artifacts, compatibility checks and publication gates. Historical findings below
remain provenance; they do not describe the current candidate qualification.

# aiogram-sentinel-native

Optional ABI1 synchronous memory kernels for aiogram-sentinel 1.3.1. The base
library remains a pure Python wheel. Build this companion from source only when
evaluating `engine="rust"`; the default Python engine does not require it.
Rust performs no asynchronous I/O or application callbacks. Its memory state is
local to the process; Redis remains authoritative for distributed deployments.

Publication remains withheld. Earlier candidates failed CPU qualification; the
follow-up linked below records the latest per-gate outcome. The core remains
available from source, with no native release or base `[native]` extra. See
[the original measured decision](BENCHMARKS.md); functional compatibility alone
does not imply a performance improvement.

The [18 November qualification follow-up](../../../reports/2026-11-18-native-qualification/README.md)
retains all repeated-run outcomes, rejected experiments and current release blockers.
No companion is published by the qualification workflow.
