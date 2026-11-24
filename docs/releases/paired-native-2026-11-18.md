# Paired SDK and native release candidates

No package, release or tag is published by this preparation. Candidate versions:

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
configuration. Until publication, use the reviewed local artifacts rather than
asking PyPI for these candidate versions. Do not use editable installs to qualify
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

The release evidence is recorded in `reports/2026-11-18-paired-release/`. The
artifact directories themselves are retained outside Git with SHA256 manifests.
No candidate is ready to publish until all its gates and publisher bindings are
verified. A successful build alone is insufficient.

## Publication after a separate go-ahead

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
and enforce exact SDK/native hashes before and after immutable handoff; the
Cmds and Idle candidates are held by their measured performance gates. Native workflows are
`publish-aiogram-<package>-native.yml`, bound to environment `pypi`.

Four native PyPI project Trusted Publishers need verification against
`ArmanAvanesyan/aiogram-kit`, the matching native publishing workflow and `pypi`.
The SDK bindings must also remain valid. Publisher registration and release/tag
creation are outside this preparation and have not been performed. Source and
build verification do not grant publishing credentials.

After publication, verify public-index downloads, metadata, exact versions and
standalone/paired installs again. Do not replace reviewed artifacts with rebuilt
ones or remove old publishers before verified successful publication.
