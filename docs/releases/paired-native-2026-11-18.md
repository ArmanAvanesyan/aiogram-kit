# Paired SDK and native releases

Published on 24 November 2026 after explicit owner authorization, SDK before native
companion, with Nav before Idle. All publishing and release-tag verification workflows
passed against source commit `7939442484daa915ae8ebf60efda902d72d32021`. Versions:

| SDK | SDK and companion version | Native companion |
| --- | --- | --- |
| aiogram-sentinel | 1.3.2 | aiogram-sentinel-native |
| aiogram-cmds | 0.3.2 | aiogram-cmds-native |
| aiogram-nav | 0.3.2 | aiogram-nav-native |
| aiogram-idle | 0.3.2 | aiogram-idle-native |

Each SDK checks the exact companion version and ABI 1 before native mutation or
application effects. Mismatched versions fail explicitly. Python remains the
default, and base installations have no mandatory native, Redis or peer-library
dependency. Coordination remains a small shared dependency for Nav and Idle;
Idle's navigation integration remains an optional extra.

Install the SDK by itself for Python operation. For Rust operation, install its
exact companion wheel separately and select `engine="rust"` in the documented
configuration. These versions are available from PyPI. Do not use editable installs to qualify
release artifacts.

## Gates and artifact handoff

Candidate wheel and source archives must pass metadata, checksum, namespace,
version and tag checks. Native releases require all seven supported platform
wheels plus one source archive, strict ABI3 audits, CPython 3.10–3.14 runtime
checks, clean standalone installs, paired SDK installs and negative version tests.
SDK wheel and source builds must remain independently installable. Real-Redis,
standalone and combined navigation/activity tests remain required.

The unchanged performance protocol requires CPU Rust/Python <=0.80, individual
p95 <=1.05 and repeat spread <=10%. Historical qualified development artifacts
are provenance, not substitutes for qualifying the final versioned candidates.
Every failed run and complete raw observation is retained. Shipping qualification
uses the checksum-bound platform CI binaries through
`tools/optimization/prepare_release_qualification.py`; it never substitutes a
host-rebuilt companion.

All four current candidates pass the unchanged performance gates. Sentinel and
Nav retain their original qualification with narrowly checked provenance
reconciliation; Idle passes its changed Redis reducer candidate, and Cmds passes
its changed compiled SDK boundary with the exact verified native binaries. The
earlier failed candidates and raw observations remain retained.

The source reports in the repository are:

- `reports/2026-11-18-paired-release/`: original measurements and Sentinel/Nav qualification.
- `reports/2026-11-24-native-release-fixes/`: Idle qualification and the first changed Cmds candidate.
- `reports/2026-11-24-cmds-compiled-boundary/`: passing final Cmds qualification, all-four publisher preflight and the final 40-artifact index.

The artifact directories themselves are retained outside Git with SHA256 manifests.
All eight published distributions were verified from PyPI against the reviewed hashes.
Standalone/paired installs and optional integration profiles passed. A future version
still needs its own exact-artifact qualification; these reports do not authorize a new build.

## Publication procedure for future versions

Use independent tags `aiogram-<package>-v<version>` and
`aiogram-<package>-native-v<version>`, all pointing at the reviewed release source.
Publish the SDK before its exact companion. Publish Nav before Idle so the
optional integration resolves from the public index. Existing Coordination 0.1.1
satisfies both packages; no Coordination release is required.

Upload only the exact reviewed SDK wheel/sdist or native seven-wheel/sdist set
and their `SHA256SUMS` to the corresponding GitHub release. Review the checksum
manifest digest independently. Manual package-specific publishing workflows
recheck identity, tag, full native platform coverage and checksums after artifact
handoff; publishing jobs never rebuild. They re-evaluate retained raw performance evidence
and enforce exact SDK/native hashes before and after immutable handoff. All four
current publisher preflights pass. Native workflows are
`publish-aiogram-<package>-native.yml`, bound to environment `pypi`.

All ten project-specific SDK/native publishers target `ArmanAvanesyan/aiogram-kit`,
their matching publishing workflows and environment `pypi`. The four native bindings
were exercised successfully by the 24 November releases. Existing Coordination and Kit
cutover publishers were verified during migration. No publishing workflow fetches a
retired repository. The five legacy repositories are covered by the owner's retirement
instruction; see [retired repository boundaries](../legacy-links.md).

Future native metadata now points at Kit. Already published files retain their original
metadata: some native 0.3.2 project links are absent or refer to retired repositories.
Do not overwrite those files or weaken source-hash checks. Qualify fresh artifacts
from the new source before publishing any future version.

After publication, verify public-index downloads, metadata, exact versions and
standalone/paired installs again. Do not replace reviewed artifacts with rebuilt
ones or remove old publishers before verified successful publication.
