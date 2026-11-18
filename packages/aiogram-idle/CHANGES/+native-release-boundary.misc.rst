Optimize optional native lease release transport while preserving complete guards, lossless opaque tokens, arbitrary integer generations, and scalar subclass behavior. Correct native typing metadata and iterable mapping-pair fingerprint parity. Native publication remains gated.
Avoid a queue-view/lock reference cycle that retained ephemeral backend codecs and derived caches until cyclic garbage collection.
Release revoked codec and owner-task references from copied contexts while preserving task-scoped revocation and nested scope restoration.
Rearm owned native deadline jobs in place with fresh generation and insertion order, avoiding repeated hash-table removal/insertion while preserving leases, counters and heap compaction.
Add opt-in fresh-fixture latency windows to benchmark evidence, retaining all observations, explicit boundaries and correct pooled-count denominators; default fixture count remains unchanged.
