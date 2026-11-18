# Compiled profiles and optional CPU engines

The default engine is Python. Installing a native module never changes engine
selection. Existing live configurations and translators are evaluated on every
call, preserving dynamic translation behavior.

For repeated menus, explicitly compile a snapshot:

```python
from aiogram_cmds import CommandScopeManager, compile_config

snapshot = compile_config(
    config,
    config_revision="menus-v2",
    translator=translator,
    translation_revision="catalogs-v7",
)
manager = CommandScopeManager(bot, compiled=snapshot)
result = await manager.apply_profile(42, "member", language="ru", language_code=None)
```

Compilation copies configuration and resolves translations immediately. The
snapshot is immutable; returned BotCommand models and configuration objects are
independent copies. Changing application configuration or catalogs does not alter
an existing snapshot. Compile a new snapshot with new revisions when either
changes. Revisions are application-owned labels, not automatic cache keys. A
translator requires an explicit translation revision. Unknown snapshot profiles
or uncompiled locales fail before Telegram operations.

`ProfileRequest` and `build_profile_batch(snapshot, requests)` resolve ordered
menus and fingerprints without network calls. `ResolvedPayload.bot_commands()`
returns fresh SDK objects. Duplicate commands and ordering remain significant.
`manager.build_batch(requests)` additionally checks that each bot identity matches
its manager. Batch application still reports partial success; Telegram has no
transactional multi-menu API. A matching caller-owned confirmed fingerprint skips
sending, and only literal Bot API `True` confirms a new fingerprint.

## Native candidate

The separate `aiogram-cmds-native` companion contains a Rust resolved-profile and
fingerprint CPU core. It has no dependency on this Python package. It is a
candidate, not an advertised dependency extra or published installation promise.
The pure Python wheel needs no Rust compiler, Redis, navigation or native module.

Developers can build the candidate with `uv pip install ./native`, then select
`engine="rust"` on `compile_config`, `CommandScopeManager`,
`build_profile_batch` or `payload_fingerprint`. A manager binds its compiled
snapshot once. Native ABI/version mismatches and missing modules raise
`NativeEngineError` before effects; the library never silently falls back after
an explicit request. Rust receives resolved strings, never translators, async
callbacks, Telegram clients or application business logic. The supported native
ABI is 1 and candidate companion version is 0.3.1. Snapshot capabilities include
`resolve_one` and `resolve_batch`; incomplete companions are rejected before
translation or delivery effects.

A compiled single-target delivery validates its aiogram scope once, then resolves
the immutable rows and exact canonical fingerprint without constructing a batch
or parsing the scope's own JSON. The native single-target cache compares borrowed
request strings before allocating a new key. At most 256 derived fingerprint
entries are retained per snapshot (a last-request entry plus up to 255 batch
entries), each admitted request bounded to 4096 encoded input bytes. Oversized
requests are resolved without retention. Every key includes profile, locale, bot,
scope and language slot; a new snapshot has a separate cache. These entries never
represent successful delivery or caller confirmation. Command models remain
fresh, and a confirmation hit constructs none. Mutable live configuration and
translator callbacks retain their uncached behavior.

## Reproducible evidence

Run `python benchmarks/run.py --engine python --output result.json` against an
installed wheel. Use `--engine rust` for an installed companion. The same driver
runs against published 0.2.0 without source-path injection. New compiled APIs are
marked `new_only`, not presented as baseline-comparable features. An orjson
comparator shows how a general serializer compares with the custom engine.

`--quick` is exploratory and cannot qualify publication. Reports include raw CPU
and wall samples, nearest-rank p95, RSS and effect/translation call counts. Realistic
operation p95 uses individual menu calls, separately from batch CPU samples. Fake
network latency is explicitly named and is not a Telegram performance claim.
`benchmarks/pyperf_suite.py` uses pyperf's subprocess runner; native Criterion
benchmarks run with `cargo bench --manifest-path native/Cargo.toml`.

Native publication requires serial matched measurements showing at least 20%
CPU improvement and no greater than 5% realistic p95 regression. No such result is
claimed merely because correctness tests pass. Seven native platform wheels and
Python 3.10–3.14 runtime CI are separate from the pure Python package. Native
release tags use `aiogram-cmds-native-v*`; base tags use `aiogram-cmds-v*`.

The original serial ABBA native gate failed (selected compiled batch CPU was
56.7% slower, with dynamic confirmation-hit p95 regressions). Native publication,
native tags and a dependency extra are withheld. Buildable source is retained;
the Python 0.3.0 package can release independently. Supplemental compiled manager
workloads retain the original failed gate and include deferred SDK construction.


### Live tiny menus and retained qualification diagnostics

Live delivery validates the selected engine and ABI once before translator
callbacks. Its internal fingerprint boundary reuses that validation; menus with
at most ten freshly rendered commands use CPython's JSON/SHA implementation
without an additional native boundary. Larger live menus retain the explicit
native path, and an unexpected native failure is never retried in Python. The
standalone public fingerprint function retains its own eager validation.
No configuration, translator output or confirmation is cached by live delivery.

The controlled follow-up run 44210106073 still failed qualification. The
compiled-confirmation/10 repeat-spread failure was in the Python baseline
(14,487 ns versus 15,950 ns, about 10.10%); Rust was 13,896 ns versus 13,845 ns
(about 0.37%). Before/after driver telemetry recorded no generation-two
collections, but cannot attribute particular tails to lower-generation GC or
host scheduling. The package report
`reports/2026-11-18-confirmation-tail-analysis.json` retains sample-window
summaries and exact input hashes. This is diagnostic evidence, not a reason to
waive a failed gate or rerun unchanged code until it passes.


### Declared individual-latency sample counts

`benchmarks/run.py --individual-latency-samples N` declares the number of
individual observations for each delivery/confirmation workload before the run.
The historical defaults remain 1,000 for full runs and 100 with `--quick`; an
explicit positive integer overrides either. The driver retains every raw
observation and records the requested and actual counts. No outliers are removed.

The next qualification experiment declares 3,000 observations. This is a new
sampling declaration, not an unchanged rerun of the failed 1,000-observation
reports. Workloads, command counts, targets, operation semantics, five warmups
and 31 CPU trials remain unchanged. CPU-only workloads do not gain extra loops.
The CPU/p95/repeat-spread thresholds remain unchanged, and this sample-size
change makes no claim that a previously failed gate now passes.
