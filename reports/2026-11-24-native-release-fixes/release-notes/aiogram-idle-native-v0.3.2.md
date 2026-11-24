# aiogram-idle-native 0.3.2

Optional Rust companion for `aiogram-idle==0.3.2`, ABI 1. It has no SDK, Redis or navigation dependency of its own; installing it alone never selects Rust inside the SDK.

Keep standalone inactivity handling, optional Redis and optional Nav integration. Long-lived memory backends retain native queue/codec execution. Ephemeral Redis reducers use the audited Python executor to avoid unused native allocations; Redis remains authoritative and engine availability is validated before use.

Targets: regular CPython 3.10–3.14 through the CPython 3.10 stable ABI; Linux glibc/musl x86_64 and aarch64, macOS Intel/Apple Silicon, and Windows AMD64. Retained source archives include Cargo.lock. PyPy and free-threaded CPython are not advertised native targets.

Draft release notes: use only the reviewed seven-wheel/source set and its SHA256SUMS. Performance results describe the recorded workload scope, not a universal speedup. Publication remains separate from preparation and qualification.
