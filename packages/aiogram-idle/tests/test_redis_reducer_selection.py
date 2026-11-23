"""Redis scratch work must not allocate unused native queues or codecs per read."""

from dataclasses import replace
from unittest.mock import patch

from aiogram_idle import IdleConfig, IdleConversationKey
from aiogram_idle.storage.redis_engine import Engine
from aiogram_idle.storage.redis_store import RedisStore


def test_redis_retains_public_selection_but_preselects_scratch_executor():
    config = IdleConfig(engine="rust", max_receipts_per_conversation=17)
    store = RedisStore(object(), "selection", config)
    assert store.config is config
    assert store.reducer_config == replace(config, engine="python")
    # No extension import/construction belongs to repeated scratch reads.
    with patch("aiogram_idle.engines.native_core", side_effect=AssertionError("native allocation")):
        reducer = Engine(
            key=IdleConversationKey("selection", 123, 42, 42),
            raw="",
            job="",
            manifest=None,
            now=1,
            config=store.reducer_config,
            created_at=1,
            storage_format=3,
        )
    assert reducer.json_processor is None
    assert reducer.config.max_receipts_per_conversation == 17


def test_python_scratch_selection_reuses_configuration():
    config = IdleConfig()
    assert RedisStore(object(), "selection", config).reducer_config is config
