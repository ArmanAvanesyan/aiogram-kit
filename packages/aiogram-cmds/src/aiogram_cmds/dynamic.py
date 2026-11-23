"""
Dynamic command management for runtime profile changes.
"""

from typing import cast

from aiogram import Bot
from aiogram.types import BotCommandScopeChat, BotCommandScopeChatMember

from .builders_configured import build_from_config
from .customize import CmdsConfig
from .delivery import (
    UNSET,
    CommandApplyResult,
    LanguageCode,
    menu_slot,
    resolved_fingerprint,
    validate_fingerprint,
)
from .engines import Engine, NativeModule, native_engine
from .registry import CommandRegistry
from .translator import Translator


async def set_user_profile(
    bot: Bot,
    cfg: CmdsConfig,
    *,
    translator: Translator | None,
    user_id: int,
    chat_id: int | None,
    profile: str,
    language: str,
    language_code: str | None | LanguageCode = UNSET,
) -> None:
    """
    Dynamically apply a profile to a user (optionally in a specific chat).
    """
    reg = CommandRegistry(cfg)
    names = list(reg.resolve_profile_commands(profile))
    cmds = build_from_config(
        reg, names, lang=language, translator=translator, key_prefix=cfg.i18n_key_prefix
    )

    scope = (
        BotCommandScopeChat(chat_id=user_id)
        if chat_id is None
        else BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
    )

    slot = menu_slot(language, language_code, per_language=cfg.per_language)
    if slot is None:
        response = await bot.set_my_commands(cmds, scope=scope)
    else:
        response = await bot.set_my_commands(cmds, scope=scope, language_code=slot)
    if response is not True:
        raise RuntimeError("Telegram did not apply the command menu")


async def apply_profile(
    bot: Bot,
    cfg: CmdsConfig,
    *,
    translator: Translator | None = None,
    user_id: int,
    profile: str,
    chat_id: int | None = None,
    language: str = "en",
    language_code: str | None | LanguageCode = UNSET,
    previous_fingerprint: str | None = None,
    best_effort: bool = False,
    engine: Engine = "python",
) -> CommandApplyResult:
    """Apply or explicitly skip an identical caller-confirmed menu payload.

    There is no internal cache or distributed deduplication. Failed and cancelled
    requests never confirm a fingerprint, including ambiguous transport errors.
    """
    module = native_engine(engine)
    return await resolved_profile(
        bot,
        cfg,
        translator=translator,
        user_id=user_id,
        profile=profile,
        chat_id=chat_id,
        language=language,
        language_code=language_code,
        previous_fingerprint=previous_fingerprint,
        best_effort=best_effort,
        module=module,
    )


async def resolved_profile(
    bot: Bot,
    cfg: CmdsConfig,
    *,
    translator: Translator | None = None,
    user_id: int,
    profile: str,
    chat_id: int | None = None,
    language: str = "en",
    language_code: str | None | LanguageCode = UNSET,
    previous_fingerprint: str | None = None,
    best_effort: bool = False,
    module: NativeModule | None,
) -> CommandApplyResult:
    """Internal live executor after explicit engine/ABI selection, never a cache."""
    if type(best_effort) is not bool:
        raise TypeError("best_effort must be a boolean")
    validate_fingerprint(previous_fingerprint)
    fingerprint = None
    try:
        if profile not in cfg.profiles:
            raise ValueError("Unknown command profile")
        reg = CommandRegistry(cfg)
        commands = build_from_config(
            reg,
            list(reg.resolve_profile_commands(profile)),
            lang=language,
            translator=translator,
            key_prefix=cfg.i18n_key_prefix,
        )
        scope = (
            BotCommandScopeChat(chat_id=user_id)
            if chat_id is None
            else BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
        )
        slot = menu_slot(language, language_code, per_language=cfg.per_language)
        bot_id = bot.id
        if type(bot_id) is not int or bot_id <= 0:
            raise ValueError("A positive bot identity is required for fingerprints")
        # Aiogram just validated this scope; menu_slot validated the language.
        # For small live menus, CPython hashes the resolved values directly.
        # Do not repeat the public engine check or marshal a tiny native call.
        fingerprint = resolved_fingerprint(
            bot_id,
            scope.model_dump(exclude_none=True),
            slot,
            commands,
            module=module if module is not None and len(commands) > 10 else None,
        )
        if previous_fingerprint == fingerprint:
            return CommandApplyResult("unchanged", fingerprint, fingerprint)
        if slot is None:
            response = await bot.set_my_commands(commands, scope=scope)
        else:
            response = await bot.set_my_commands(
                commands, scope=scope, language_code=slot
            )
        if response is not True:
            raise RuntimeError("Telegram did not apply the command menu")
    except Exception as error:
        if not best_effort:
            raise
        return CommandApplyResult("failed", fingerprint, error=error)
    return CommandApplyResult("applied", fingerprint, fingerprint)


async def clear_language_variants(
    bot: Bot, *, user_id: int, language_codes: list[str], chat_id: int | None = None
) -> None:
    """Delete only caller-listed language slots; preserve the default menu.

    Migrate obsolete language-specific overrides explicitly: they otherwise keep
    taking precedence over a newly installed default-language fallback.
    """
    if not isinstance(cast(object, language_codes), list):
        raise TypeError("language_codes must be a list of explicit language codes")
    if any(
        not isinstance(cast(object, code), str) or not code for code in language_codes
    ):
        raise ValueError(
            "List explicit nonempty language codes; default slot cannot be deleted"
        )
    scope = (
        BotCommandScopeChat(chat_id=user_id)
        if chat_id is None
        else BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
    )
    for code in dict.fromkeys(language_codes):
        if await bot.delete_my_commands(scope=scope, language_code=code) is not True:
            raise RuntimeError("Telegram did not delete the command menu")
