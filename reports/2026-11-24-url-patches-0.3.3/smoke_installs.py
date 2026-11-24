import asyncio
import importlib
import importlib.metadata as m
import importlib.util
import json
import sys
from pathlib import Path

short, profile, repo = sys.argv[1:4]
name = "aiogram-" + short
module = name.replace("-", "_")
native_module = ("_" + module + "_native") if short == "cmds" else module + "_native"
assert short in ("cmds", "nav", "idle")
assert importlib.util.find_spec("redis") is None
for peer in ("aiogram_cmds", "aiogram_nav", "aiogram_idle", "aiogram_sentinel"):
    if peer != module:
        assert importlib.util.find_spec(peer) is None, peer
if profile == "native-only":
    native = importlib.import_module(native_module)
    assert m.version(name + "-native") == "0.3.3" and not m.requires(name + "-native")
    assert importlib.util.find_spec(module) is None and importlib.util.find_spec("aiogram") is None
    if short == "cmds":
        assert native.abi_version() == 1 and native.version() == "0.3.3"
    else:
        assert native.API_VERSION == 1 and native.ENGINE_VERSION == "0.3.3"
else:
    sdk = importlib.import_module(module)
    assert sdk.__version__ == m.version(name) == "0.3.3"
    assert "/site-packages/" in str(Path(sdk.__file__).resolve()) and not Path(
        sdk.__file__
    ).resolve().is_relative_to(Path(repo))
    paired = profile == "paired"
    if not paired:
        assert importlib.util.find_spec(native_module) is None
    if short == "cmds":
        from aiogram_cmds import (
            CmdsConfig,
            CommandDef,
            ProfileDef,
            ProfileRequest,
            ScopeDef,
            build_profile_batch,
            compile_config,
        )

        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(descriptions={"en": "Start"})},
            profiles={"member": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="chat", chat_id=42, profile="member")],
        )

        def select(engine):
            return compile_config(config, config_revision="release-check", engine=engine)

        previous = None
        for engine in ("python", "rust") if paired else ("python",):
            compiled = select(engine)
            result = build_profile_batch(
                compiled,
                [ProfileRequest("member", "en", 123, '{"chat_id":42,"type":"chat"}', None)],
                engine=engine,
            )[0]
            assert result.commands == (("start", "Start"),)
            commands = result.bot_commands()
            commands[0].description = "Changed"
            assert result.bot_commands()[0].description == "Start"
            assert previous is None or previous == result
            previous = result
    elif short == "nav":
        from aiogram_nav import (
            ConversationKey,
            ManualClock,
            MemoryNavigationRepository,
            NavigationConfig,
            NavigationIntent,
            NavigationMutation,
            RenderResult,
        )

        def select(engine):
            return MemoryNavigationRepository(
                clock=ManualClock(100), config=NavigationConfig(engine=engine)
            )

        async def check():
            for engine in ("python", "rust") if paired else ("python",):
                backend = select(engine)
                key = ConversationKey("release-check", 1, 42, 42)
                p = await backend.prepare(
                    key,
                    expected_version=None,
                    intent=NavigationIntent("enter", "main", params={"locale": "hy"}),
                )
                mutation = NavigationMutation("enter", p.session_id, RenderResult(p.view_id))
                completed = await backend.commit(
                    key, expected_version=p.expected_version, mutation=mutation
                )
                assert completed.snapshot.node_id == "main"
                replay = await backend.commit(key, expected_version="obsolete", mutation=mutation)
                assert replay.duplicate and replay.snapshot == completed.snapshot

        asyncio.run(check())
    else:
        from aiogram_idle import (
            IdleConfig,
            IdleConversationKey,
            ManualClock,
            MemoryIdleBackend,
            OwnershipLost,
            PromptPolicy,
        )

        def select(engine):
            return MemoryIdleBackend(
                clock=ManualClock(100), config=IdleConfig(enabled=True, engine=engine)
            )

        async def check():
            for engine in ("python", "rust") if paired else ("python",):
                backend = select(engine)
                key = IdleConversationKey("release-check", 1, 42, 42)
                session = await backend.open_session(
                    key, lifetime_seconds=100, operation_id="session"
                )
                activity = await backend.enter(
                    key,
                    "draft",
                    policy_id="draft",
                    policy=PromptPolicy(after_seconds=1),
                    adapter_key="app",
                    params={"rating": 5},
                    session_id=session.session_id,
                    expires_at=session.expires_at,
                    operation_id="entry",
                    enabled=True,
                )
                backend.clock.advance(2)
                first = (await backend.claim_due(limit=1, lease_seconds=2))[0]
                backend.clock.advance(2)
                second = (await backend.claim_due(limit=1, lease_seconds=2))[0]
                assert first.token != second.token
                try:
                    await backend.renew_claim(first, lease_seconds=2)
                except OwnershipLost:
                    pass
                else:
                    raise AssertionError("Expired ownership accepted")
                await backend.release_claim(second, retry_at=backend.clock.now() + 10)
                touched = await backend.touch(
                    key, expected=activity.guard, operation_id="touch", enabled=True
                )
                assert (
                    await backend.touch(
                        key, expected=activity.guard, operation_id="touch", enabled=True
                    )
                    == touched
                )

        asyncio.run(check())
    if not paired:
        try:
            select("rust")
        except Exception as error:
            assert "native" in str(error).lower(), str(error)
        else:
            raise AssertionError("Missing native must fail before effects")
print(
    json.dumps(
        {
            "package": name,
            "profile": profile,
            "result": "pass",
            "python": sys.version.split()[0],
            "aiogram": m.version("aiogram") if profile != "native-only" else None,
        }
    )
)

if profile == "native-only" or profile == "paired":
    urls = dict(v.split(", ", 1) for v in m.metadata(name + "-native").get_all("Project-URL", []))
    assert urls["Repository"] == "https://github.com/ArmanAvanesyan/aiogram-kit"
    assert urls["Homepage"].endswith("/packages/" + name + "/native")
    assert urls["Issues"] == urls["Repository"] + "/issues"
