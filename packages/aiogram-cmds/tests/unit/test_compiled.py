"""Explicit snapshots, callback revisions, batch immutability and delivery parity."""

import asyncio
import json
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aiogram_cmds import (
    CmdsConfig,
    CommandDef,
    CommandScopeManager,
    NativeEngineError,
    ProfileDef,
    ProfileRequest,
    ScopeDef,
    build_profile_batch,
    compile_config,
)
from aiogram_cmds.delivery import UNSET, payload_fingerprint
from aiogram_cmds.engines import native_engine


@pytest.fixture(autouse=True)
def reset_native_module_cache():
    from aiogram_cmds.engines import _load_native

    _load_native.cache_clear()
    yield
    _load_native.cache_clear()


def sample():
    return CmdsConfig(
        languages=["en", "ru", "hy"],
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(descriptions={"en": "Help"}),
        },
        profiles={
            "member": ProfileDef(
                include=["start", "help", "start", "missing"], exclude=["help"]
            )
        },
        scopes=[ScopeDef(scope="chat", chat_id=42, profile="member")],
    )


def request(locale="en"):
    return ProfileRequest("member", locale, 123, '{"chat_id":42,"type":"chat"}', None)


def test_snapshot_defensively_copies_and_requires_translator_revision():
    config = sample()
    calls = []

    def translator(key, **kwargs):
        calls.append((key, kwargs["locale"]))
        return "Old description"

    with pytest.raises(ValueError, match="translation_revision"):
        compile_config(config, config_revision="one", translator=translator)
    compiled = compile_config(
        config, config_revision="one", translator=translator, translation_revision="t1"
    )
    initial = len(calls)
    config.profiles["member"].include.clear()
    config.commands["start"].i18n_key = "changed"
    a = build_profile_batch(compiled, [request()])[0]
    assert len(a.commands) == 2 and all(d == "Old description" for _, d in a.commands)
    assert len(calls) == initial
    with pytest.raises(TypeError):
        compiled.profiles["member"]["en"] = ()
    with pytest.raises(FrozenInstanceError):
        compiled.config_revision = "bad"
    copy = compiled.config()
    copy.profiles.clear()
    assert compiled.config().profiles
    models = a.bot_commands()
    models[0].description = "Mutated"
    assert a.bot_commands()[0].description == "Old description"


def test_new_config_and_translation_revisions_are_explicit():
    config = sample()
    state = {"text": "First"}

    def translator(key, **kwargs):
        return state["text"]

    old = compile_config(
        config, config_revision="1", translator=translator, translation_revision="a"
    )
    state["text"] = "Second"
    config.profiles["member"].include = ["help"]
    config.profiles["member"].exclude.clear()
    new = compile_config(
        config, config_revision="2", translator=translator, translation_revision="b"
    )
    assert build_profile_batch(old, [request()])[0].commands[0][1] == "First"
    assert build_profile_batch(new, [request()])[0].commands == (("help", "Help"),)


def test_unknown_locale_or_profile_never_silently_rerenders():
    snapshot = compile_config(sample(), config_revision="1")
    with pytest.raises(ValueError, match="Unknown compiled"):
        build_profile_batch(snapshot, [request("fr")])
    with pytest.raises(ValueError, match="Unknown compiled"):
        build_profile_batch(snapshot, [ProfileRequest("missing", "en", 123, "{}")])


@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=256
    ),
    st.integers(min_value=1, max_value=10**50),
)
def test_compiled_hash_preserves_published_canonical_fingerprint(description, bot_id):
    config = sample()
    config.commands["start"].descriptions = {"en": description}
    snapshot = compile_config(config, config_revision="1")
    r = ProfileRequest(
        "member",
        "en",
        bot_id,
        json.dumps({"type": "chat", "chat_id": 42, "meta": [1.0, True, None, "hy\n"]}),
        None,
    )
    payload = build_profile_batch(snapshot, [r])[0]
    assert payload.fingerprint == payload_fingerprint(
        bot_id, json.loads(r.scope_json), None, payload.bot_commands()
    )


@pytest.mark.parametrize("engine", ["python", "rust"])
async def test_compiled_manager_confirmations_and_partial_batches(mock_bot, engine):
    if engine == "rust":
        pytest.importorskip("_aiogram_cmds_native")
    mock_bot.id = 123
    snap = compile_config(sample(), config_revision="v1", engine=engine)
    manager = CommandScopeManager(
        mock_bot, compiled=snap, engine=engine, best_effort=True
    )
    first = await manager.apply_profile(42, "member", language_code=None)
    assert first.status == "applied"
    second = await manager.apply_profile(
        42,
        "member",
        language_code=None,
        previous_fingerprint=first.confirmed_fingerprint,
    )
    assert second.status == "unchanged" and mock_bot.set_my_commands.await_count == 1
    mock_bot.set_my_commands.side_effect = [True, TimeoutError("ambiguous")]
    partial = await manager.apply_all()
    assert partial.status == "partial" and len(partial.completed_targets) == 1
    assert partial.failed_target and partial.error


@pytest.mark.parametrize("engine", ["python", "rust"])
async def test_live_translator_is_never_implicitly_cached(mock_bot, engine):
    if engine == "rust":
        pytest.importorskip("_aiogram_cmds_native")
    state = {"calls": 0}

    def translator(key, **kwargs):
        state["calls"] += 1
        return f"Call {state['calls']}"

    manager = CommandScopeManager(
        mock_bot, config=sample(), translator=translator, engine=engine
    )
    await manager.update_profile(42, "member")
    await manager.update_profile(42, "member")
    assert state["calls"] == 4


@pytest.mark.parametrize("engine", ["python", "rust"])
async def test_compiled_cancellation_propagates_and_no_false_confirmation(
    mock_bot, engine
):
    if engine == "rust":
        pytest.importorskip("_aiogram_cmds_native")
    mock_bot.id = 123
    mock_bot.set_my_commands.side_effect = asyncio.CancelledError
    manager = CommandScopeManager(
        mock_bot,
        compiled=compile_config(sample(), config_revision="1", engine=engine),
        best_effort=True,
        engine=engine,
    )
    with pytest.raises(asyncio.CancelledError):
        await manager.apply_profile(42, "member")
    mock_bot.set_my_commands.side_effect = None
    mock_bot.set_my_commands.return_value = None
    assert (await manager.apply_profile(42, "member")).confirmed_fingerprint is None
    mock_bot.set_my_commands.return_value = True
    assert (await manager.apply_profile(42, "member")).status == "applied"
    assert mock_bot.set_my_commands.await_count == 3


def test_engine_configuration_is_explicit_and_before_effects(monkeypatch, mock_bot):
    import aiogram_cmds.engines as engines

    def missing(name):
        raise ImportError("not installed")

    monkeypatch.setattr(engines, "import_module", missing)
    assert native_engine("python") is None
    with pytest.raises(NativeEngineError):
        CommandScopeManager(mock_bot, engine="rust")
    with pytest.raises(ValueError):
        CommandScopeManager(mock_bot, engine="invalid")
    mock_bot.set_my_commands.assert_not_called()


def test_reject_incompatible_abi(monkeypatch):
    import aiogram_cmds.engines as engines

    class Bad:
        def abi_version(self):
            return 100

        def version(self):
            return "0.3.1"

    monkeypatch.setattr(engines, "import_module", lambda name: Bad())
    with pytest.raises(NativeEngineError, match="ABI"):
        native_engine("rust")


@given(
    st.lists(st.sampled_from(["start", "help", "unknown", "start"]), max_size=40),
    st.lists(st.sampled_from(["start", "help"]), max_size=10),
)
def test_native_profile_resolution_parity(include, exclude):
    native = pytest.importorskip("_aiogram_cmds_native")
    assert native.resolve_profile(include, exclude, ["start", "help"]) == [
        n for n in include if n in {"start", "help"} and n not in set(exclude)
    ]


@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=256
    )
)
def test_native_batch_and_hash_parity(description):
    pytest.importorskip("_aiogram_cmds_native")
    config = sample()
    config.commands["start"].descriptions = {"en": description}
    snapshot = compile_config(config, config_revision="1", engine="rust")
    requests = [request(), request("ru"), request("hy")]
    assert build_profile_batch(snapshot, requests) == build_profile_batch(
        snapshot, requests, engine="rust"
    )
    payload = build_profile_batch(snapshot, [request()])[0]
    assert (
        payload_fingerprint(
            123,
            {"type": "chat", "chat_id": 42},
            None,
            payload.bot_commands(),
            engine="rust",
        )
        == payload.fingerprint
    )


def test_translation_revision_recompile_changes_resolved_output():
    cfg = sample()
    catalog = {"description": "First"}

    def translate(key, **kwargs):
        return catalog["description"]

    first = compile_config(
        cfg, config_revision="1", translator=translate, translation_revision="a"
    )
    catalog["description"] = "Second"
    second = compile_config(
        cfg, config_revision="1", translator=translate, translation_revision="b"
    )
    assert first.rows("member", "en")[0][1] == "First"
    assert second.rows("member", "en")[0][1] == "Second"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10**100])
def test_native_hash_preserves_legacy_scope_serialization(value):
    pytest.importorskip("_aiogram_cmds_native")
    from aiogram.types import BotCommand

    rows = [BotCommand(command="Not normalized!", description="Description")]
    assert payload_fingerprint(
        123, {"value": value}, None, rows
    ) == payload_fingerprint(123, {"value": value}, None, rows, engine="rust")


@pytest.mark.parametrize("abi", [True, 1.0, 1])
def test_malformed_matching_native_rejected_before_callbacks(
    monkeypatch, mock_bot, abi
):
    from types import SimpleNamespace

    import aiogram_cmds.engines as engines

    module = SimpleNamespace(abi_version=lambda: abi, version=lambda: "0.3.1")
    monkeypatch.setattr(engines, "import_module", lambda name: module)

    def translator(key, **kwargs):
        pytest.fail("Malformed native module must fail before callbacks")

    with pytest.raises(NativeEngineError):
        compile_config(
            sample(),
            config_revision="1",
            translator=translator,
            translation_revision="1",
            engine="rust",
        )
    mock_bot.set_my_commands.assert_not_called()


def test_native_dynamic_loader_failure_is_normalized(monkeypatch):
    import aiogram_cmds.engines as engines

    def broken(name):
        raise OSError("dynamic loader failed")

    monkeypatch.setattr(engines, "import_module", broken)
    with pytest.raises(NativeEngineError):
        native_engine("rust")


def test_native_fingerprint_cache_preserves_scope_and_snapshot_identity():
    native = pytest.importorskip("_aiogram_cmds_native")
    snapshot = native.compile([("p", [("en", [("start", "First")])])])
    other = native.compile([("p", [("en", [("start", "Second")])])])
    requests = [("p", "en", "1", '{"type":"default"}', "null")]
    expected = snapshot.resolve_batch(requests)
    assert snapshot.resolve_batch(requests * 300) == expected * 300
    assert other.resolve_batch(requests) != expected
    # Exercise capacity flush and oversized uncached inputs, then replay the first key.
    for index in range(300):
        snapshot.resolve_batch(
            [("p", "en", str(index + 1), '{"type":"default"}', "null")]
        )
    assert snapshot.resolve_batch(requests) == expected
    large = [("p", "en", "1", '{"type":"' + "a" * 5000 + '"}', "null")]
    assert snapshot.resolve_batch(large) == snapshot.resolve_batch(large)
    with pytest.raises(ValueError):
        snapshot.resolve_batch([("missing", "en", "1", "{}", "null")])


def test_native_module_is_validated_once_before_repeated_operations(monkeypatch):
    import aiogram_cmds.engines as engines

    real = pytest.importorskip("_aiogram_cmds_native")
    calls = []

    def load(name):
        calls.append(name)
        return real

    monkeypatch.setattr(engines, "import_module", load)
    assert engines.native_engine("rust") is real
    assert engines.native_engine("rust") is real
    assert calls == ["_aiogram_cmds_native"]
    with pytest.raises(ValueError):
        engines.native_engine("invalid")


def test_native_single_resolution_matches_batch_and_slot_boundaries():
    native = pytest.importorskip("_aiogram_cmds_native")
    snapshot = native.compile([("p", [("en", [("start", "First")])])])
    for scope in ('{"type":"chat","chat_id":1}', '{"type":"chat","chat_id":2}'):
        for language in ("null", '"hy"'):
            request = ("p", "en", "123", scope, language)
            assert (
                snapshot.resolve_one(*request) == snapshot.resolve_batch([request])[0]
            )
    with pytest.raises(ValueError):
        snapshot.resolve_one("missing", "en", "123", "{}", "null")


@pytest.mark.parametrize("engine", ["python", "rust"])
@pytest.mark.parametrize("chat_id", [None, -10042])
@pytest.mark.parametrize("language_code", [None, "", "hy", UNSET])
@pytest.mark.parametrize("per_language", [True, False])
async def test_single_delivery_preserves_batch_scope_hash_and_confirmation(
    mock_bot, engine, chat_id, language_code, per_language, monkeypatch
):
    from aiogram.types import BotCommandScopeChat, BotCommandScopeChatMember

    from aiogram_cmds.compiled import ResolvedPayload

    if engine == "rust":
        pytest.importorskip("_aiogram_cmds_native")
    mock_bot.id = 123
    config = sample()
    config.per_language = per_language
    snapshot = compile_config(config, config_revision="single", engine=engine)
    scope = (
        BotCommandScopeChat(chat_id=42)
        if chat_id is None
        else BotCommandScopeChatMember(chat_id=chat_id, user_id=42)
    )
    expected = build_profile_batch(
        snapshot,
        [ProfileRequest("member", "ru", 123, scope.model_dump_json(), language_code)],
        engine=engine,
    )[0]
    manager = CommandScopeManager(mock_bot, compiled=snapshot, engine=engine)
    applied = await manager.apply_profile(
        42, "member", chat_id=chat_id, language="ru", language_code=language_code
    )
    assert applied.confirmed_fingerprint == expected.fingerprint
    actual = mock_bot.set_my_commands.call_args
    assert actual.kwargs["scope"] == scope
    assert actual.args[0] == expected.bot_commands()
    assert actual.kwargs.get("language_code") == expected.language_code
    if expected.language_code is None:
        assert "language_code" not in actual.kwargs

    def no_materialization(self):
        pytest.fail("A confirmation hit must not construct mutable command models")

    monkeypatch.setattr(ResolvedPayload, "bot_commands", no_materialization)
    unchanged = await manager.apply_profile(
        42,
        "member",
        chat_id=chat_id,
        language="ru",
        language_code=language_code,
        previous_fingerprint=expected.fingerprint,
    )
    assert unchanged.status == "unchanged"
    assert mock_bot.set_my_commands.await_count == 1


def test_native_borrowed_single_cache_respects_every_slot_and_failure():
    native = pytest.importorskip("_aiogram_cmds_native")
    snapshot = native.compile(
        [
            (
                "member",
                [("en", [("start", "English")]), ("ru", [("start", "Russian")])],
            ),
            ("guest", [("en", [("start", "Guest")])]),
        ]
    )
    base = ("member", "en", "123", '{"chat_id":42,"type":"chat"}', "null")
    expected = snapshot.resolve_batch([base])[0]
    for index, replacement in enumerate(
        ("guest", "ru", "456", '{"chat_id":43,"type":"chat"}', '"ru"')
    ):
        other = (*base[:index], replacement, *base[index + 1 :])
        for request in (base, other, other, base, base):
            assert (
                snapshot.resolve_one(*request) == snapshot.resolve_batch([request])[0]
            )
    for invalid in (
        ("unknown", *base[1:]),
        (*base[:2], "0", *base[3:]),
        (*base[:4], "42"),
    ):
        with pytest.raises(ValueError):
            snapshot.resolve_one(*invalid)
        assert snapshot.resolve_one(*base) == expected
    large = (*base[:3], '{"meta":"' + "x" * 5000 + '"}', base[4])
    assert snapshot.resolve_one(*large) == snapshot.resolve_batch([large])[0]
    assert snapshot.resolve_one(*base) == expected
