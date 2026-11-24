# Paired release refresh — unpublished

For subsequent provenance fixes and new shipping measurements, see the
[native release follow-up](../2026-11-24-native-release-fixes/README.md). The
table below records the earlier checkpoint, not current publication approval.

Refresh of draft PR #88 after PRs #69 and #89 merged. Candidate versions remain
Sentinel SDK/native **1.3.2**, and Cmds/Nav/Idle SDK/native **0.3.2**. This work
does not publish, create tags/releases, change publisher permissions, or merge
the release PR.

## Verification

- Main `4ce836c`: **all 14 workflows passed**. Sentinel's macOS Python setup
  initially failed with DNS `ENOTFOUND raw.githubusercontent.com`; its affected
  job was retried and passed. No library workaround or check bypass was needed.
  `main-ci.json` retains the run IDs and retry cause.
- The release branch merges main `4ce836c` without rewriting history. Refreshed
  package/build input commit: `8b2eb74`.
- Workspace lock verification passes. Root integration and optimization tooling:
  **318 passed, 1 platform-specific skip**. Ruff and strict documentation pass.
- Four SDK wheels and four sdists were rebuilt into a new retained directory;
  strict filename/tag/version/checksum verification and Twine checks pass.
- **20 isolated install profiles pass**: SDK wheel with minimum/latest aiogram,
  SDK sdist, native-only shipping wheel, and paired shipping wheel, for each SDK.
  These run outside the workspace, check installed versions and missing optional
  packages, and reject Rust selection when its companion is absent.
- Minimum aiogram profiles use Python 3.10, matching CI (3.0.0 for Sentinel/Cmds,
  3.22.0 for Nav/Idle). Latest profiles use Python 3.12 and resolved aiogram 3.34.0.
  An initial probe used Python 3.12 with aiogram 3.0; its old aiohttp build failed.
  The harness was corrected to match the supported CI combination, without
  changing SDK dependencies or treating that failed probe as a passing profile.
- All **40 previously retained artifacts** and their eight checksum manifests
  still match. Native binaries were neither rebuilt nor benchmarked again.
- All four refreshed SDK **wheels are byte-for-byte identical** to the previously
  qualified wheels. Their sdists change because development configuration,
  locks and test fixtures changed. Old sdists/manifests remain intact.
- Live PyPI verification finds the four candidate SDK versions unpublished and
  all four native project endpoints returning 404. No versions are reserved.

Artifacts and new checksum manifests are retained at
`/Users/armanavanesyan/oss/own/aiogram-paired-release-candidates-2026-11-24/`.
`artifact-verification.json` records exact hashes, profiles, wheel equivalence and
qualified-source differences. It supplements rather than replaces the original
[qualification evidence](../2026-11-18-paired-release/README.md).

## Readiness

| Pair | SDK packaging/installs | Historical native performance | Current native publisher preflight |
| --- | --- | --- | --- |
| Sentinel 1.3.2 | pass | pass | hold: qualified source hash changed |
| Cmds 0.3.2 | pass | hold | hold: performance qualification |
| Nav 0.3.2 | pass | pass | hold: qualified source hash changed |
| Idle 0.3.2 | pass | hold | hold: performance qualification |

The only changed file in each qualified source inventory is its SDK
`pyproject.toml`: development-group changes and compatibility comments. SDK
wheel equivalence is verified above, but the publisher intentionally requires
exact source hashes too. **Historical Sentinel/Nav performance passes do not
override the current preflight failure.** Before reusing them, a reviewed source
provenance refresh must reconcile those differences with the exact artifacts
and retain the original raw evidence and manifests. No verifier check, source
hash or gate is waived or rewritten in this refresh.

Cmds still fails dynamic confirmation latency/repeatability; Idle still fails
Redis activation/touch and dispatcher no-op latency/repeatability. Their raw
failures remain in the original report. Further qualification needs a justified
candidate change and a declared experiment, not resampling unchanged artifacts
or relaxing thresholds. All four companions remain held and unpublished.

## Before publication

1. Complete main and refreshed PR #88 CI; review/merge the release PR and verify
   the final source before tagging. This report alone is not release approval.
2. Resolve Cmds/Idle performance holds and the source-provenance holds using
   reviewed exact-artifact evidence; keep native release gates enforced.
3. Verify SDK and native Trusted Publishers and GitHub `pypi` tag policies.
   PyPI publisher settings have not been authenticated or changed here.
4. Review the final checksum manifests, versions and release notes, then obtain
   a separate publishing instruction. Keep SDK and native distributions
   independent; publish Nav before Idle and each SDK before its exact companion.

The eight existing draft release notes remain under the original report.
Refreshed sdists require the new SDK checksum manifests; original native sets
retain their original manifests. Never mix old/new source archives silently.

Reproduce the install and artifact checks on macOS (shipping host wheel probe):

```sh
python reports/2026-11-24-paired-release-refresh/verify_refresh.py \
  --artifacts /absolute/path/to/refreshed-sdk-artifacts \
  --output /tmp/artifact-verification.json
```

This probe also requires the retained native artifacts at the locations in the
original artifact index. It writes SDK manifests but never publishes. The
complete cross-platform runtime and Redis matrices remain in GitHub CI.
