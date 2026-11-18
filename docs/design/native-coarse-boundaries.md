# Coarse native boundaries (development candidate)

All four native distributions remain unpublished. This work changes internal
optional-engine capabilities; it does not change public Python imports, storage
formats, authentication, lock ownership or delivery semantics. Performance
qualification is separate from functional and platform qualification.

## Cmds

Immutable compiled snapshots resolve a single target directly with `resolve_one`;
larger batches retain `resolve_batch`. This avoids allocating and crossing the
native boundary with a one-element request list. Python still invokes translators,
constructs fresh aiogram objects, sends Telegram requests and records confirmations.
Mutable configurations and dynamic translator results are never implicitly cached.
A strict native capability check happens before effects. Confirmation fingerprints
retain their existing exact canonical bytes.

## Nav and Idle

One native call traverses supported inputs, encodes canonical JSON and hashes it.
Another fuses immutable JSON copying, validation and encoded-size accounting.
The encoder preserves CPython float representation, unbounded integers, Unicode,
Enum normalization and each library's existing dataclass normalization. Unsupported
application container/subclass shapes select the Python validator before native
traversal invokes application methods. Unexpected native failures propagate.

Each memory backend owns a codec fork. It memoizes only derived encodings of
privately copied immutable JSON and exact approved frozen SDK records whose fields
are recursively immutable. Arbitrary mapping proxies are detached before reuse;
readonly access does not prove their backing dictionary immutable. Application
subclasses and mutable records are never cached. Arbitrary-size integers are not
memoized, preserving changes to Python's runtime integer-string digit limit.

The derived cache is bounded to 128 objects and 1 MiB of serialized/encoded byte
accounting per codec, plus bounded object/interpreter overhead. Strong references
prevent address reuse. Eviction and backend close discard only derived values;
receipts, state, claims and recovery evidence are unaffected. Cache correctness
assumes callers respect frozen SDK records and private immutable snapshots rather
than bypassing them through reflection. This is an optimization, not a sandbox.

Codec selection has actual-task ownership and revocation. Copied contexts and child
tasks cannot borrow it. Nav's backend lock remains non-reentrant; Idle preserves
its existing task-owned reentrancy. These scopes grant no FSM/coordinator authority.
Application validators, adapters, session authority and network calls remain
outside the codec scope. Pure model construction is scoped synchronously only for
an exact supported memory repository; custom and combined repositories preserve
their existing extension behavior.

Idle's built-in policy digests use bounded caches keyed by exact scalar types and
current values. Custom policy classes retain the reference implementation. Runtime
initialization skips repeated local bootstrap only after successful initialization;
authoritative configuration and format-manifest checks still run for updates.

Idle additionally projects admitted deadline claims to SDK objects in one native
call. Python supplies cryptographically random tokens and holds the existing
backend lock; Rust makes scheduling/lease decisions. Claim ownership, expiry,
renewal, reconciliation and crash recovery retain the same rules. Queue-only work
acquires the same task-owned lock without creating an unused JSON codec scope;
reentrancy and suppression of a foreign backend codec are tested. Lease validation
borrows native jobs rather than cloning them. Nav retains an already-owned immutable
intent instead of copying it a second time. Both companions
use portable thin LTO and one code-generation unit, without host-specific flags.

## Verification and publication hold

The fixed protocol remains CPU ratio <= 0.80, individual p95 ratio <= 1.05 and
repeat spread <= 10%, balanced Python/Rust/Rust/Python order. Failed runs are
retained, never replaced with a selected successful repeat. Installed wheel hashes,
source commit and benchmark-driver provenance accompany each qualification.
See [retained qualification](https://github.com/ArmanAvanesyan/aiogram-kit/blob/perf/native-gates-followup/reports/2026-11-18-native-coarse-qualification/README.md).

Native capability changes require matched, verified SDK/companion artifacts before
any future release. Source version numbers here identify development candidates;
they authorize neither publication nor installing an older incompatible companion.
Standalone Python installs require no Rust, Redis or optional peer integration.
