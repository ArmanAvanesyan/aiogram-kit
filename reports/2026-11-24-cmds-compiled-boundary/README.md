# Cmds compiled-boundary follow-up — unpublished

The first changed Cmds shipping run 45291905439 passed every selected CPU and
latency ratio, but failed repeatability for `compiled_confirmation_hit/100`:
Rust p95 values were 9,946 and 11,710 ns, a 17.7% spread. The Python repeats were
14,377 and 14,358 ns. Rust-b's later windows contain the divergence; this does
not establish GC, hypervisor or library causality. The complete failed run and
all artifacts remain in the preceding report and external backup.

This SDK candidate changes the affected compiled path. A snapshot retains only
its last immutable resolved payload, for either Python or Rust, with a maximum
4096-character key. Every request still validates identity/profile/locale/scope;
scalar subclasses and oversized keys are not retained. Snapshot rebuilds reset
the entry. No mutable command models, live translators, authorization decisions,
delivery results or confirmations are cached. Every send constructs fresh SDK
models and a failed send still needs a successful Bot API response later.

Compiled manager operations also capture the eagerly validated engine binding,
as live manager operations already do. Direct public APIs retain eager native
validation. Selected batch CPU workloads and all benchmark controllers, sampling,
state-age windows, GC policy and thresholds remain unchanged.

The exact Rust binary is unchanged from platform run 45289854108. The new SDK
wheel and its source commit must be recorded separately from that native CI
commit: independent distributions need not be rebuilt merely to give them a
shared Git SHA. Runtime source hashes and exact SDK/native artifact hashes still
bind the pair; final SDK/platform/integration CI must pass before release.

`experiment-declaration.json` precedes timing. This is a changed SDK candidate,
not a retry or relabelling of the prior failed run. It must pass fresh shipping
qualification before publication; no package has been published.
