"""Python-owned Telegram boundary for explicitly compiled profile payloads."""

from __future__ import annotations

import json

from aiogram import Bot
from aiogram.types import BotCommandScopeChat, BotCommandScopeChatMember

from .compiled import CompiledCommands, resolved_payload
from .delivery import (
    UNSET,
    CommandApplyResult,
    LanguageCode,
    validate_fingerprint,
)
from .engines import Engine, NativeModule, native_engine


async def apply_compiled_profile(
    bot: Bot,
    compiled: CompiledCommands,
    *,
    user_id: int,
    profile: str,
    chat_id: int | None = None,
    language: str = "en",
    language_code: str | None | LanguageCode = UNSET,
    previous_fingerprint: str | None = None,
    best_effort: bool = False,
    engine: Engine = "python",
) -> CommandApplyResult:
    module = native_engine(engine)
    return await resolved_compiled_profile(
        bot,
        compiled,
        user_id=user_id,
        profile=profile,
        chat_id=chat_id,
        language=language,
        language_code=language_code,
        previous_fingerprint=previous_fingerprint,
        best_effort=best_effort,
        module=module,
    )


async def resolved_compiled_profile(
    bot: Bot,
    compiled: CompiledCommands,
    *,
    user_id: int,
    profile: str,
    chat_id: int | None = None,
    language: str = "en",
    language_code: str | None | LanguageCode = UNSET,
    previous_fingerprint: str | None = None,
    best_effort: bool = False,
    module: NativeModule | None,
) -> CommandApplyResult:
    """Execute after the caller captured and validated its engine selection."""
    if type(best_effort) is not bool:
        raise TypeError("best_effort must be a boolean")
    validate_fingerprint(previous_fingerprint)
    fingerprint = None
    try:
        scope = (
            BotCommandScopeChat(chat_id=user_id)
            if chat_id is None
            else BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
        )
        # The scope was just validated by aiogram. Serializing its JSON-mode
        # values directly avoids dump -> parse -> dump and a one-item batch.
        canonical_scope = json.dumps(
            scope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload = resolved_payload(
            compiled,
            profile=profile,
            language=language,
            bot_id=bot.id,
            canonical_scope=canonical_scope,
            language_code=language_code,
            module=module,
        )
        fingerprint = payload.fingerprint
        if previous_fingerprint == fingerprint:
            return CommandApplyResult("unchanged", fingerprint, fingerprint)
        commands = payload.bot_commands()
        if payload.language_code is None:
            response = await bot.set_my_commands(commands, scope=scope)
        else:
            response = await bot.set_my_commands(
                commands, scope=scope, language_code=payload.language_code
            )
        if response is not True:
            raise RuntimeError("Telegram did not apply the command menu")
    except Exception as error:
        if not best_effort:
            raise
        return CommandApplyResult("failed", fingerprint, error=error)
    return CommandApplyResult("applied", fingerprint, fingerprint)
