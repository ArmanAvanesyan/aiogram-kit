# Retired repositories and preserved Git history

The active repository is [aiogram-kit](https://github.com/ArmanAvanesyan/aiogram-kit),
the original Sentinel repository renamed during consolidation. Do not recreate
`aiogram-sentinel`: its existing repository redirect follows the surviving identity.

The owner authorized removing the following five legacy repositories on 24 November
2026, without creating any new backups, exports, release-asset copies or archive site.
They are no longer current development or publishing destinations.

| Retired repository | Retained source directory | Original source history in Kit |
| --- | --- | --- |
| `aiogram-idle` | `packages/aiogram-idle` | [original main](https://github.com/ArmanAvanesyan/aiogram-kit/tree/04a753ab1ce04086d2dabe4f4381cf188553a8e1) |
| `aiogram-nav` | `packages/aiogram-nav` | [original main](https://github.com/ArmanAvanesyan/aiogram-kit/tree/a5a0696c495b66350446923715de82256f8dfde1) |
| `aiogram-cmds` | `packages/aiogram-cmds` | [original main](https://github.com/ArmanAvanesyan/aiogram-kit/tree/1457341dca31565335c9d53e22b9ae534dce9031) |
| `aiogram-coordination` | `packages/aiogram-coordination` | [original main](https://github.com/ArmanAvanesyan/aiogram-kit/tree/7dcb06e2e46a57e8b826279c744ab51d368a997d) |
| `aiogram-kit-legacy` | `packages/aiogram-kit` | [original main](https://github.com/ArmanAvanesyan/aiogram-kit/tree/f279f964371b95133a331b99c385855f8f0ef534) |

Original commit IDs and the 100 published historical branch/tag references remain
in Kit. `tools/verify_migration.py --historical-objects --remote-refs` verifies their
objects, source ancestry, remote targets and the protected original Kit working documents.
Existing migration reports and source snapshots retain their original bytes and dates;
their old repository URLs are historical evidence, not maintained destinations.

## Records that Git does not preserve

Repository removal makes legacy PRs, comments, workflow pages, releases and attached
asset URLs unavailable. These records are not recreated by importing Git history.
No new copies are created for retirement. Previously retained evidence is left alone.

Original Kit PR numbers 1, 2 and 3 refer to the former Kit repository, not to those
numbers in the surviving repository. Original Kit's `v0.0.1` Git tag remains preserved;
its legacy GitHub release/asset URL is not a replacement download location. Do not
remap old PR or release numbers to unrelated records in Kit.

Older PyPI distributions and external bookmarks can retain legacy URLs permanently.
Current source metadata points at Kit for future releases; already published package
files are not replaced. Current package downloads remain available from PyPI, and
maintained releases/assets are under Kit's independent package-qualified tags.

## Maintained documentation

Use [Kit documentation](https://armanavanesyan.github.io/aiogram-kit/) and its
[Cmds](https://armanavanesyan.github.io/aiogram-kit/libraries/aiogram-cmds/),
[Coordination](https://armanavanesyan.github.io/aiogram-kit/libraries/aiogram-coordination/),
[Nav](https://armanavanesyan.github.io/aiogram-kit/libraries/aiogram-nav/) and
[Idle](https://armanavanesyan.github.io/aiogram-kit/libraries/aiogram-idle/) sections.
GitHub Pages addresses do not acquire redirects automatically when repositories
are renamed or removed. Historical site addresses are not supported destinations.
