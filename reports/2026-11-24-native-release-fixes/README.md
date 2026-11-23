# Changed native release candidates — unpublished

This follow-up retains the November 18/24 reports and their failed measurements.
The earlier PR #88 head passed 250 checks after a one-job retry of the existing
filesystem settings-load smoke test (1.11 seconds against its 1-second bound).
No timing limit was changed. Source changes below require fresh CI and declared
shipping-artifact qualification before any readiness promotion.

## Sentinel/Nav source reconciliation

The original qualification manifest and raw data remain unchanged. A separate
`source-reconciliation.json` alongside that report retains the exact original
TOML, current digest and unchanged SDK wheel digest for Sentinel/Nav. Verification
checks the original bytes against the immutable manifest before comparing parsed
TOML. Only non-distributed dependency groups and comments/formatting may differ.
Published metadata, runtime dependencies, extras, build-system and tool settings
must still match. Runtime/native source has no exemption. Tests exercise rejected
metadata changes, substituted original/current hashes and SDK digest changes.
Both original publisher preflights now pass with their original artifacts;
qualification staging uses the same constrained check, with reconciliations
included inside the reviewed staging manifest's checksum.

## Changed candidates

- Cmds borrows Python string storage within the existing GIL-held native
  fingerprint call instead of allocating owned strings for every command row.
  No reference escapes or enters a cache; the API and hashes are unchanged.
  The serial old/new/new/old diagnostic used 1.295/1.120/1.122/1.299 CPU seconds.
  This is a diagnostic, not a p95 or release qualification result.
- Idle preselects the Python executor for ephemeral Redis scratch reduction,
  which otherwise allocated a native queue and codec at each read. Redis owns
  scheduling and CAS; the scratch executor needs no persistent native queue.
  Public engine configuration and eager companion validation remain intact;
  long-lived memory backends keep native execution. No transport/ownership error
  causes fallback. Existing formats, replay evidence and fencing are unchanged.

A direct command-model native boundary was tried and rejected after its local
diagnostic was slower (1.119 versus 0.800 CPU seconds for tuple input). Its raw
observations are retained, but the prototype is removed. The initially attempted
borrowed lifetime signature failed to compile and was corrected by retaining
Python string objects for the duration of borrowing. No failed prototype is
shipping or being counted as a successful benchmark.

A second direct-model prototype used interned attribute keys and borrowed
strings. Its isolated CPU cost was near the borrowed-tuple boundary, but full
dynamic delivery did not show a reliable latency benefit. It too was removed;
the raw dynamic observations and diagnostic script are retained. These probes
observed no GC collections, so no GC attribution is asserted. Neither prototype
was submitted as shipping qualification or used to replace a failed gate.

Local tests include **853 Idle tests with real Redis 7**, the native queue/domain
vectors, the command/native parity and error corpus, and strict Rust Clippy/tests.
An initial sandboxed test invocation could not open loopback sockets; the full
corpus was rerun with required network access and passed. It is not a library
Redis outage or a passing result for that denied invocation.

`experiment-declaration.json` records unchanged gates and sampling before timing.
Exact input artifacts and platform CI will be bound before dispatch. Host-built
diagnostic wheels cannot qualify the shipping release. The existing Cmds/Idle
performance holds remain until the changed shipping candidates actually pass.
All four companions remain unpublished; publisher/environment configuration and
the final separate publishing instruction remain required.
