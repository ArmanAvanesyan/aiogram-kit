"""Digest optimizations retain exact legacy policy/catalog wire identities."""

import hashlib
import json
from dataclasses import asdict, replace

from aiogram_idle.policies import (
    ExemptPolicy,
    IdlePolicies,
    PromptPolicy,
    QuietRestorePolicy,
    policy_digest,
)


def legacy(policy):
    return hashlib.sha256(
        json.dumps({"kind": policy.kind, **asdict(policy)}, sort_keys=True).encode()
    ).hexdigest()


def test_exact_numeric_type_and_policy_change_are_not_coalesced(monkeypatch):
    policies = [ExemptPolicy(), PromptPolicy(1, 2), PromptPolicy(1.0, 2.0), QuietRestorePolicy(5)]
    for policy in policies:
        assert policy_digest(policy) == legacy(policy)
    assert policy_digest(policies[1]) != policy_digest(policies[2])
    assert policy_digest(replace(policies[1], after_seconds=3)) == legacy(
        replace(policies[1], after_seconds=3)
    )
    catalog = IdlePolicies({str(i): p for i, p in enumerate(policies)})
    first = catalog.digest
    assert catalog.digest == first
    monkeypatch.setattr(PromptPolicy, "kind", "changed")
    expected = hashlib.sha256(
        json.dumps({str(i): legacy(p) for i, p in enumerate(policies)}, sort_keys=True).encode()
    ).hexdigest()
    assert catalog.digest == expected != first
