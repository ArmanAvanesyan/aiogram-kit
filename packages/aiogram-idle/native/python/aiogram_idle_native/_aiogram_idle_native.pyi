from collections.abc import Callable
from typing import Any, Literal, TypeVar

API_VERSION: Literal[1]
ENGINE_VERSION: Literal["0.3.1"]

T = TypeVar("T")

class OwnershipLost(RuntimeError): ...
class InvalidJson(ValueError): ...

class Canonicalizer:
    def __init__(
        self,
        enum_type: object,
        mapping_type: object,
        fields: object,
        datetime_type: object = None,
        view_type: object = None,
        render_type: object = None,
        immutable_types: object = None,
    ) -> None: ...
    def fork(self) -> Canonicalizer: ...
    def fingerprint(self, value: object) -> str: ...
    def freeze(self, value: object, proxy: object, style: str) -> tuple[object, int] | None: ...
    def clear_cache(self) -> None: ...
    def cache_stats(self) -> tuple[int, int]: ...

def phase_transition(phase: str, trigger: str) -> str: ...
def fingerprint_canonical(raw: str) -> str: ...
def receipt_admission(
    existing: str | None, digest: str, retained_count: str, limit: str
) -> str: ...
def activity_guard(
    actual: tuple[str, str, str, float] | None, expected: tuple[str, str, str], now: float
) -> str | None: ...
def session_guard(
    actual: tuple[str, str, float] | None, expected: tuple[str, str] | None, now: float
) -> str | None: ...
def claim_guard(
    actual: tuple[str, str, float] | None, expected: tuple[str, str], now: float
) -> str | None: ...

class DeadlineCore:
    sequence: str
    def __init__(self) -> None: ...
    def __len__(self) -> int: ...
    def heap_len(self) -> int: ...
    def heap(self) -> list[tuple[float, str, str]]: ...
    def keys(self) -> list[str]: ...
    def get(self, key: str) -> tuple[str, float, float, str | None, float] | None: ...
    def remove(self, key: str) -> tuple[str, float, float, str | None, float] | None: ...
    def clear(self) -> None: ...
    def put(
        self,
        key: str,
        namespace: str,
        bot_id: str,
        generation: str,
        deadline: float,
        eligible_at: float,
        token: str | None = None,
        lease_until: float = 0,
    ) -> None: ...
    def push(self, key: str) -> None: ...
    def schedule(
        self,
        key: str,
        namespace: str,
        bot_id: str,
        deadline: float | None,
        preserve_token: str | None = None,
    ) -> None: ...
    def check(
        self, key: str, token: str, generation: str, now: float
    ) -> tuple[str, float, float, str | None, float]: ...
    def claim(
        self,
        limit: int,
        lease_seconds: float,
        now: float,
        tokens: list[str],
        namespace: str | None = None,
        bot_id: str | None = None,
    ) -> list[tuple[str, str, str, float, float]]: ...
    def claim_objects(
        self,
        limit: int,
        lease_seconds: float,
        now: float,
        tokens: list[str],
        namespace: str | None,
        bot_id: str | None,
        keys: dict[str, Any],
        factory: Callable[..., T],
    ) -> list[T]: ...
    def renew(
        self, key: str, token: str, generation: str, now: float, lease_seconds: float
    ) -> tuple[str, str, str, float, float]: ...
    def release(
        self, key: str, token: str, generation: str, now: float, deadline: float | None = None
    ) -> None: ...
    def release_values(
        self,
        key: str,
        token: str,
        generation: int,
        now: float,
        deadline: float | None = None,
    ) -> None: ...
    def reconcile(self, candidates: list[tuple[str, str, str, float]], limit: int) -> int: ...
