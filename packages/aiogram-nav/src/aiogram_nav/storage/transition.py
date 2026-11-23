"""Pure state/history transition boundary shared by deterministic engines."""

from __future__ import annotations

from collections.abc import Callable

from ..config import NavigationConfig
from ..engine import native_core
from ..models import HistoryEntry, NavigationMutation, NavigationSnapshot, PreparedAction


def transition(
    old: NavigationSnapshot | None,
    prepared: PreparedAction,
    mutation: NavigationMutation,
    *,
    config: NavigationConfig,
    now: int,
    fingerprint: Callable[[object], str],
) -> tuple[tuple[HistoryEntry, ...], dict[str, int]]:
    params_changed = old is None or fingerprint(old.params) != fingerprint(prepared.params)
    accepted = prepared.intent.accepted_activity and mutation.accepted_activity
    limit = config.history_limit
    mode = prepared.intent.history
    if config.engine == "python":
        history = old.history if old else ()
        if (
            mode == "push"
            and old is not None
            and (old.node_id != prepared.node_id or params_changed)
        ):
            history = (*history, HistoryEntry(old.node_id, old.params))
        elif mode == "pop":
            amount = getattr(prepared.intent, "history_pop", 1)
            history = history[:-amount] if amount else history
        elif mode == "clear":
            history = ()
        history = history[-limit:] if limit else ()
        state = dict(
            nav_revision=(old.nav_revision + 1) if old else 1,
            activity_revision=(old.activity_revision + int(accepted)) if old else 1,
            entered_at=now
            if old is None or old.node_id != prepared.node_id or params_changed
            else old.entered_at,
            last_activity_at=now if accepted or old is None else old.last_activity_at,
        )
        return history, state
    core = native_core()
    changed = old is None or old.node_id != prepared.node_id or params_changed
    entries, values = core.transition_values(
        old.history if old else (),
        HistoryEntry(old.node_id, old.params) if old and changed and mode == "push" else None,
        mode,
        limit,
        getattr(prepared.intent, "history_pop", 1),
        changed,
        (
            str(old.nav_revision),
            str(old.activity_revision),
            str(old.entered_at),
            str(old.last_activity_at),
        )
        if old
        else None,
        accepted,
        str(now),
    )
    return tuple(entries), dict(
        zip(
            ("nav_revision", "activity_revision", "entered_at", "last_activity_at"),
            map(int, values),
            strict=True,
        )
    )
