# aiogram-idle-native

Optional deterministic Rust implementation for aiogram-idle 0.3.1. Maturin builds a
CPython abi3-py310 wheel. This distribution has no dependency on the base library.
The base defaults to Python; explicitly selecting Rust requires this exact 0.3.1
companion with API_VERSION 1 before mutation, with no fallback after a failure.

**Release status: source-only, unpublished.** The original 0.3.0 serial CPU
gate failed. The current coarse-boundary candidate meets the selected CPU target,
but claim/combined latency and repeatability still block qualification. Historical
failed runs remain recorded; functional/parity CI does not establish performance
qualification or authorize a native release. Keep Python as the default.

Rust owns the lifecycle transition table, activity/session/claim guard decisions,
exact supplied-byte SHA256, receipt duplicate/conflict/capacity decisions, and an
authoritative generation-checked deadline heap with scheduling, claims, renewal,
conditional release/completion, compaction and bounded reconciliation. Python owns
model construction, clocks, random tokens, locks, I/O and all application effects.
The supported canonical traversal, immutable JSON copying/size accounting and
fingerprints execute in coarse calls, preserving Python numeric formatting,
Unicode escapes and durable operation identity across engines. Unknown native
failures propagate rather than triggering a Python retry.

Build `uvx maturin build --release --manifest-path native/Cargo.toml`; test
`cargo test --manifest-path native/Cargo.toml`; benchmark
`cargo bench --manifest-path native/Cargo.toml --bench core`. The native companion
can be published separately by aiogram-idle-native-v* tags, never by the base Python-only workflow.
No native tag or PyPI distribution is released for this version.
An sdist install requires Rust/Cargo. Cargo.lock is retained for reproducibility.
Native microbenchmarks do not establish end-to-end Redis/Telegram speedups. The
performance gate is qualified separately on a labelled host and may reject use of
the optional engine when the >=20% CPU / <=5% real-p95-regression gates are not met.

The low-level extension uses canonical hexadecimal strings for revisions/generations
and receipt counters, backed by Rust BigUint rather than lossy machine integers.
The base library's typed adapter keeps ordinary Python integer/model APIs. Opaque
identities crossing the extension boundary are ASCII JSON strings, preserving
low-level opaque Python codepoints; they are compared, never interpreted by Rust.
Public persistent identifiers and JSON parameters reject surrogate code units early,
using the same strict UTF-8 Unicode scalar contract for both engines.

The [18 November qualification follow-up](../../../reports/2026-11-18-native-qualification/README.md)
retains all repeated-run outcomes, rejected experiments and current release blockers.
No companion is published by the qualification workflow.

### Raw lease release boundary

The SDK supplies ordinary exact `str` tokens and positive `int` generations to
`DeadlineCore.release_values`. The native boundary performs lossless ASCII-JSON
transport and integer conversion before the authoritative key/token/generation/
lease check. It does not cache a successful authorization. Opaque surrogate-bearing
tokens and arbitrarily large integer generations remain lossless. Scalar subclasses
and unusual fabricated SDK claims deterministically retain the original Python
JSON/`format(..., "x")` adapter before effects; there is no retry after native errors.
The original low-level string-wire `release` method remains available.

The packaged typed surface includes the exact engine version, `Canonicalizer`,
`InvalidJson`, coarse claim projection and raw release method. It imports no SDK,
Redis or navigation package. Current timing evidence is retained in the
[coarse-boundary qualification report](../../../reports/2026-11-18-native-coarse-qualification/README.md).
