# Cmds runner isolation qualification

Declared before timing; same artifacts, 30000 latency observations, ABBA order, GC and gates. Move other owned runner threads off the client physical core, and use normal CFS nice -20 for the benchmark. No real-time scheduler or dropped observations. Both previous experiments remain retained, including the localized Rust-a latency spike and correlated host pressure. The final controlled experiment passed.

Run 45337425850 stopped during scheduling setup before taking observations. A protected same-UID thread requires the runner scheduling privilege; the corrected setup rechecks ownership and verifies explicit sudo taskset results. The setup log and artifact digest are retained in `setup-failure.json`. The measured run is 45337896111.

Run [45337896111](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/45337896111) passed and the publisher independently recomputed the raw-data gate. CPU ratio 0.5153; maximum latency ratio 1.0081; maximum latency repeat spread 2.494%. All four profiles record nice -20 and fixed client CPU 0. See `../2026-11-24-paired-0.3.3/` for the combined release decision.
