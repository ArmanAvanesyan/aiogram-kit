# aiogram-idle 0.3.2

Keep standalone inactivity handling, optional Redis and optional Nav integration. Long-lived memory backends retain native queue/codec execution. Ephemeral Redis reducers use the audited Python executor to avoid unused native allocations; Redis remains authoritative and engine availability is validated before use.

Python is the default. This SDK has no mandatory native dependency or native extra. Explicit Rust selection requires the independently installed `aiogram-idle-native==0.3.2` companion (ABI 1). Missing or incompatible companions fail before effects.

Standalone SDK wheels and source archives are verified separately. SDK and companion versions, tags, checksums and releases remain independent.

Exact artifacts and workload scope are recorded in the qualification report and SHA256SUMS.
