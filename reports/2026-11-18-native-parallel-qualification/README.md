# Parallel native performance follow-up

This phase implements package-specific fixes through separate agents, plus an
independent safety audit and a benchmark-reliability audit. All four Rust
companions remain unpublished. The unchanged original performance protocol is
identified by hash in `experiment-declaration.json`.

The controlled qualification will apply the same explicitly recorded CPU affinity
to every measured profile. This controls CPU migration; it does not reserve a
physical core or isolate background work. New telemetry is observational and runs
outside measured scopes. Thresholds, samples, workloads and GC policy are unchanged.
Earlier measurements and failures remain in the adjacent qualification reports.

Package changes and final functional/qualification evidence will be recorded here
after verification. No performance or release-readiness result is claimed yet.
