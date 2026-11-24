# Cmds runner isolation qualification

Declared before timing; same artifacts, 30000 latency observations, ABBA order, GC and gates. Move other owned runner threads off the client physical core, and use normal CFS nice -20 for the benchmark. No real-time scheduler or dropped observations. Both previous experiments remain retained, including the localized Rust-a latency spike and correlated host pressure. Results pending.
