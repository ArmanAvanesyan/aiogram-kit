# Monorepo cutover complete

The active repository is [ArmanAvanesyan/aiogram-kit](https://github.com/ArmanAvanesyan/aiogram-kit),
repository ID `1065465593`, originally Sentinel. Its star and fork network were retained.
Original Kit, ID `1424361052`, is retained as `aiogram-kit-legacy`.
Migration [PR 67](https://github.com/ArmanAvanesyan/aiogram-kit/pull/67) and verification
[PR 81](https://github.com/ArmanAvanesyan/aiogram-kit/pull/81) were merged without rewriting source histories.

## Published cutover releases

| Distribution | PyPI version |
| --- | --- |
| aiogram-coordination | 0.1.1 |
| aiogram-nav | 0.3.1 |
| aiogram-idle | 0.3.1 |
| aiogram-sentinel | 1.3.1 |
| aiogram-cmds | 0.3.1 |
| aiogram-kit | 0.0.2 |

Each has an independent package-prefixed Git tag and GitHub release, containing the exact
reviewed wheel, sdist and SHA256SUMS. All six package-specific Trusted Publishers were
registered and successfully used. Coordination was published and verified before Nav;
Nav was published and verified before Idle. No native companion was published: their
independent performance gates remain unsatisfied.

All 12 PyPI artifacts were downloaded, checked against the reviewed hashes and independently
installed outside the workspace. Redis was absent in base installs; Idle did not install Nav,
and Nav did not install Idle. Kit still has no runtime dependencies. A fresh PyPI installation
of Idle[nav,redis], Nav and Coordination passed 127 combined memory/real-Redis, recovery,
coordination, callback and FSM tests with source packages absent.

See `release-manifests.json`, `publication-runs.json`, `published-artifact-verification.json`
and `published-combined-verification.json`.

## Preservation and verification

- Verified Git bundles retain all six source repositories; 100 namespaced historical refs were checked against remote object IDs. Original commit IDs were not rewritten.
- All 68 historical release assets were backed up and checked; historical releases and assets remain with their repository identities.
- The source/destination manifests map 929 working files and 183 documents. Original Kit's 16 working documents remain byte-preserved; maintained central installation recipes were updated separately.
- All 41 ordinary issues remain attached to the surviving repository. The retiring repositories contain no ordinary issues requiring transfer. Historical PRs, comments and reviews remain retained; original Kit's reused URL mappings are explicit in the documentation.
- Project 12 retained its ID, 41 item IDs, statuses, exposed custom values, 16 fields and three views. Its name is now aiogram-kit.
- The original open Sentinel dependency PR 66 was automatically closed by Dependabot after migration; its records remain retained. Cmds PR 17 remains open in its historical repository. Neither was implicitly merged.
- Full package compatibility, strict typing, security, coverage, real-Redis, optional integration, native platform and installed-artifact workflows passed. `cutover-main-checks.json` records the release commit's passing main/tag checks. PR 81 also explicitly tested scheduled-only Cmds jobs.
- Cmds' PyPy 3.10 profile uses a compatible Pydantic 2.12/Hypothesis test profile because current upstream native dependencies require newer PyPy; public runtime bounds and CPython minimum/latest coverage are unchanged. Timing probes now emit JUnit results rather than requesting an unused pytest-benchmark fixture.
- The unified documentation was deployed and its package/standalone URLs checked. Old Sentinel Pages returns 404; the explicit maintained URL map avoids recreating aiogram-sentinel and breaking the repository redirect. Cmds' historical site still responds.

## Final cleanup and archival: completed 2026-11-17

All six obsolete PyPI Trusted Publisher bindings were removed after the cutover releases
succeeded. Each project retains exactly its matching `publish-aiogram-<package>.yml`
workflow in `ArmanAvanesyan/aiogram-kit`, environment `pypi`. The GitHub environment
admits only the six package-specific tag prefixes; its obsolete `v*` policy was removed.
No existing version was republished.

The five retiring repositories are archived, with migration notices and retained records:
`aiogram-cmds`, `aiogram-coordination`, `aiogram-nav`, `aiogram-idle`, `aiogram-kit-legacy`.
The surviving Kit repository remains active under Sentinel's original ID, with its star
and fork network retained. Do not recreate aiogram-sentinel.

Immediately before archival, all 12 main verification workflows were green, all 12 published
artifact downloads matched the reviewed hashes, all 68 historical asset backups matched
their checksums, and no new legacy issues required transfer. Fresh full-ref Git bundles
were created and verified for all six repository identities. Five new immutable history
refs preserve the migration-notice commits; the earlier 95 refs were not overwritten.
Project 12's 41 item IDs, exposed values and 16 fields were rechecked unchanged.

**Cmds draft visibility:** the old GitHub `v0.1.1` release (ID `254429599`) remains a draft.
Archival hides draft releases from the API because GitHub's draft listings require push
access. An archive/unarchive roundtrip verified the same release ID and all four assets
intact before final archival. Its metadata and asset backups are retained; temporarily
unarchive Cmds to access the draft. It was not published, recreated or deleted.
See [GitHub's release visibility rule](https://docs.github.com/en/rest/releases/releases#list-releases)
and [archival behavior](https://docs.github.com/en/repositories/archiving-a-github-repository/archiving-repositories).
Published releases and assets remain visible in the archived repositories.

See `publisher-retirement.json`, `pre-archive-gates.json`, `archival-results.json`,
`archival-bundles.json`, `archival-preservation-checks.json` and `active-repository.json`.
The pre-archive snapshot intentionally records the state before archival; `archival-results.json`
records the verified final state. Raw authenticated API responses remain in the private backup.

Private raw inventories, verified bundles, release assets and operational evidence remain locally
at `../aiogram-migration-2026-11-11/`. Credential values were not exported.

## Post-cutover review

See [the 2026-11-17 end-to-end review](review-2026-11-17.md) for the correction of
latest-main command-test transports, publishing handoff hardening, canonical history
references, automatic main documentation deployment and shared-tool matrix coverage.
The operational cutover and published artifact hashes remain unchanged.
