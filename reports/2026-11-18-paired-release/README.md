# Paired release preparation — unpublished

Candidates: Sentinel SDK/native 1.3.2; Cmds, Nav and Idle SDK/native 0.3.2.
No package, tag, GitHub release or PyPI publisher is created by this preparation.
The changes are on PR #88. Python remains the default; no native runtime
requirement or unimplemented extra is added. Redis and navigation stay optional.

## Verified so far

- PyPI versions were checked before selecting the next patch versions; all four
  native project URLs returned 404. Candidate versions are not reserved/published.
- Exact SDK/Rust project/Cargo/runtime versions and ABI 1 agree. Missing and
  previous companions are rejected; older published SDKs reject the new companion.
- 20 isolated installed-artifact profiles pass: SDK wheel/source with no native,
  Redis or peer; native-only with no SDK; paired and mismatched-version tests;
  and independent native source rebuild/install. Four reverse-version checks pass.
- Nav/Idle public Python and Rust memory-lifecycle probes pass, including replay,
  draft isolation, expiry, claims and stale-owner fencing.
- Four complete CI native sets pass strict seven-wheel/one-source identity,
  version, tag, namespace, platform and independent manifest validation. All 28
  wheels pass strict ABI3 audits; all 32 distributions pass Twine metadata checks.
- Versioned runtime/platform CI at `1bd593c` passed 250 checks with 5 intentional
  skips. This includes Redis, shared coordination and optional integration tests.
- Root integration 66 tests pass; optimization tooling 239 pass with 1 local
  Linux-only skip. Strict documentation builds pass.

## Exact artifact qualification

`ci-artifact-manifest.json` binds GitHub artifact IDs and source commits to exact
archive digests, SDK wheel digests and source-file hashes. The preparation tool
checks completed successful platform CI, artifact ownership, all eight files per
companion and the complete native release verifier before selecting the glibc
x86_64 shipping wheel. SDK wheels must match the reviewed digests. Native code is
not rebuilt in this release qualification path.

`release-experiment-declaration.json` declares the single shipping-artifact run
before timing. CPU <= 0.80, individual p95 <= 1.05, repeat spread <= 10%, ABBA order,
complete raw observations and robust state-age windows remain unchanged.

The earlier host-built experiment 44231208251 qualified Nav/Idle but failed
Sentinel/Cmds repeatability. It used different companion builds and cannot qualify
the release wheels. Complete raw data and failed gates remain under
`host-build-qualification/`, with original-content hashes and binary backup
mappings in `host-build-retention.json`. No failure or tail is discarded.

Shipping-artifact run 44234194460 completed. Complete evidence is under
`shipping-qualification/`; `shipping-retention.json` preserves original hashes and
binary locations. Independent recomputation and exact SDK/native input checks
pass in `shipping-artifact-audit.json`. The measured results are:

| Pair | Version | SDK packaging/standalone | Native performance | Selected CPU Rust/Python |
| --- | --- | --- | --- | --- |
| Sentinel | 1.3.2 | pass | pass | rate 0.516; debounce 0.653 |
| Cmds | 0.3.2 | pass | **hold** | 0.558 |
| Nav | 0.3.2 | pass | pass | 0.777 |
| Idle | 0.3.2 | pass | **hold** | 0.786 |

Cmds' dynamic `confirmation_hit/100` p95 ratio is 1.213 (21.3% regression);
repeat spread also fails for dynamic confirmation sizes 1 and 100. Its compiled
rows pass, but that does not waive the complete gate.

Idle's Redis activation/touch p95 ratio is 1.155 and dispatcher no-op ratio 1.153;
both exceed the 5% regression limit and fail repeatability. Claim p95 is 0.961,
and its CPU target passes, which does not waive the Redis rows. Available
observations do not establish the cause of either library's failures.

All four SDK artifacts are prepared. Sentinel and Nav native companions are
technically qualified on the recorded Linux/Python 3.12 workload scope, with the
full functional platform matrix passing. Cmds and Idle native companions are
**not release-ready**. No unchanged shipping candidate is resampled to erase
these failures. All eight distributions remain unpublished.

Native publisher verification now independently recomputes the fixed gates from
retained raw samples, checks the exact artifact and SDK digests and verifies
source-file hashes before an upload job can run. The same verification repeats
after immutable artifact handoff. `publisher-gate-verification.json` confirms
Sentinel/Nav allow and Cmds/Idle reject, without invoking publication. Each
publisher selects its own versioned report, preserving independent releases.

Additional 16 profiles using actual CI macOS shipping wheels/source archives and
final SDK source archives pass (`shipping-install-verification.json`), alongside
the initial 20 isolated profiles and 4 reverse-version checks.

## Publication prerequisites

Even a successful shipping-artifact gate does not authorize publication:

1. Review and merge PR #88 and verify the release source/main CI.
2. Add the four explicit native tag patterns to GitHub's `pypi` environment;
   inspection found only the six existing SDK tag patterns.
3. Verify four native Trusted Publishers against repository
   `ArmanAvanesyan/aiogram-kit`, workflow `publish-aiogram-<name>-native.yml`,
   environment `pypi`; also retain/verify the SDK publishers. Native PyPI
   publisher settings have not been authenticated or changed in this task.
4. Approve the final exact-artifact manifests and a separate publishing action.

Eight draft release-note files are in `release-notes/`. Tags and releases are
independent. Publish the SDK before its exact companion, and Nav before Idle.
Verify public-index downloads and standalone/paired installs afterward.

## Local artifacts and reproducibility

Binary backups are retained outside Git at
`/Users/armanavanesyan/oss/own/aiogram-paired-release-candidates-2026-11-18/`.
`reviewed-release-artifacts/` contains the full CI native release sets;
`artifacts/` and `release-artifacts/` retain local SDK/native build evidence.
SDK/native checksum manifests are retained with each set. The canonical upload
candidates are under `release-candidates/<distribution>/` in that backup.
`final-artifact-index.json` lists all 40 artifacts across 8 distributions and their
independent checksum manifests; readiness holds still apply. Build-output scratch
files such as uv's `.gitignore` are excluded from strict publishing directories.

The verification scripts and JSON records are retained alongside this report.
Initial scratch-harness errors (cached-module substitution and an unsupported
Idle constructor keyword) were corrected; final negative tests target the actual
extension and public Rust selection. These were harness defects, not accepted
incompatible versions or library regressions.
