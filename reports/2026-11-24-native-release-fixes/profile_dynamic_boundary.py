import asyncio
import gc
import json
import sys
import time

sys.path.insert(0, sys.argv[1])
import _aiogram_cmds_native as native
from aiogram_cmds import CmdsConfig, CommandDef, CommandScopeManager, ProfileDef, dynamic

if sys.argv[2] == "model":

    def fingerprint(bot_id, scope, language, commands, *, module):
        if module is None:
            return original(bot_id, scope, language, commands, module=None)
        return native.fingerprint_models(
            str(bot_id),
            json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            json.dumps(language, ensure_ascii=False),
            commands,
        )

    original = dynamic.resolved_fingerprint
    dynamic.resolved_fingerprint = fingerprint


class Bot:
    id = 123

    async def set_my_commands(self, *a, **k):
        return True


names = [f"command_{i}" for i in range(100)]
config = CmdsConfig(
    languages=["en", "ru", "hy"],
    commands={name: CommandDef(i18n_key=f"{name}.desc") for name in names},
    profiles={"p": ProfileDef(include=names)},
)


def translate(key, *, locale=None, **kwargs):
    return f"{locale}: {key} description"


async def run():
    manager = CommandScopeManager(Bot(), config=config, translator=translate, engine="rust")
    confirmed = (
        await manager.apply_profile(42, "p", language="hy", language_code=None)
    ).confirmed_fingerprint
    for _ in range(5):
        await manager.apply_profile(
            42, "p", language="hy", language_code=None, previous_fingerprint=confirmed
        )
    before = gc.get_stats()
    raw = []
    startcpu = time.process_time()
    for _ in range(3000):
        start = time.perf_counter_ns()
        result = await manager.apply_profile(
            42, "p", language="hy", language_code=None, previous_fingerprint=confirmed
        )
        raw.append(time.perf_counter_ns() - start)
        assert result.status == "unchanged"
    return {
        "cpu_seconds": time.process_time() - startcpu,
        "p95_ns": sorted(raw)[int(0.95 * (len(raw) - 1))],
        "gc_collections": [
            b["collections"] - a["collections"] for a, b in zip(before, gc.get_stats())
        ],
        "raw_ns": raw,
    }


print(json.dumps(asyncio.run(run())))
