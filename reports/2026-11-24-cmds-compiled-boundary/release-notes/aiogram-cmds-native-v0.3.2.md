# aiogram-cmds-native 0.3.2

Optional Rust companion for `aiogram-cmds==0.3.2`, ABI 1. It has no SDK, Redis or navigation dependency of its own; installing it alone never selects Rust inside the SDK.

Use compiled immutable snapshots for native batch resolution. Live translators remain uncached. Resolved native fingerprint hashing borrows Python strings without changing canonical digests or caller-owned confirmations.

Targets: regular CPython 3.10–3.14 through the CPython 3.10 stable ABI; Linux glibc/musl x86_64 and aarch64, macOS Intel/Apple Silicon, and Windows AMD64. Retained source archives include Cargo.lock. PyPy and free-threaded CPython are not advertised native targets.

The release consists of the reviewed seven-wheel/source set and its SHA256SUMS. Performance results describe the recorded workload scope, not a universal speedup. Publication remains separate from preparation and qualification.

Compiled single-target resolution retains only its last immutable payload for either engine, with no cached delivery confirmation or mutable SDK command models. Managers reuse their validated engine binding; direct APIs still validate explicit engine selection before effects.
