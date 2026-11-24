# Extended repeatability qualification for 0.3.3

Declared before timing: 10x more observations, with identical artifacts, workload shapes, fixed ages, GC, raw-tail retention, ABBA order and gates. This tests whether the initial short windows were insufficient for stable p95 estimates; it does not invalidate or discard their failures.

CPU <=0.80, individual p95 <=1.05, repeat spread <=10%. All initial failed evidence and the passing Idle qualification remain in `../2026-11-24-url-patches-0.3.3/`. Results pending; no publication.

Nav run [45334009819](https://github.com/ArmanAvanesyan/aiogram-kit/actions/runs/45334009819) passed and was independently recomputed from retained raw data. CPU ratio is 0.761; Redis p95 ratios are 1.023 (no-op) and 0.992 (track). The previously failed Redis repeat spreads are now 0.18–3.36%, below the unchanged 10% gate. Each Redis workload retains all 10,000 observations per engine profile.

Cmds run 45334006147 failed `confirmation_hit/100` latency and repeatability gates; all 30000 observations per workload/profile remain retained. The other previously failed workloads pass. The targeted follow-up is declared in `../2026-11-24-cmds-isolation-0.3.3/`. Idle retains its independent passing qualification in the original report.
