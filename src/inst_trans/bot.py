"""Сборка Bot/Dispatcher, регистрация хэндлеров, запуск long-polling."""

from __future__ import annotations

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, MessageEntity

from inst_trans.config import Settings
from inst_trans.converter import convert_url
from inst_trans.middlewares import ChatWhitelistMiddleware

log = structlog.get_logger(__name__)


def _build_router(target_host: str) -> Router:
    router = Router(name="root")

    @router.message(Command("chatid"))
    async def cmd_chatid(message: Message) -> None:
        await message.answer(f"chat_id: <code>{message.chat.id}</code>")

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "Привет! Я подменяю Instagram-ссылки на kkclip-зеркало, "
            "чтобы видео проигрывалось прямо в Telegram. "
            "Просто кидайте ссылки в чат — я буду отвечать преобразованной версией."
        )

    @router.message()
    async def on_any_message(message: Message) -> None:
        urls = _extract_urls(message)
        if not urls:
            return

        converted: list[str] = []
        for url in urls:
            new_url = convert_url(url, target_host)
            if new_url is not None:
                converted.append(new_url)

        if not converted:
            return

        # Сохраняем порядок, убираем дубликаты, если одна ссылка встречается несколько раз.
        unique = list(dict.fromkeys(converted))
        reply_text = "\n".join(unique)

        log.info(
            "converted",
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else None,
            count=len(unique),
        )
        # parse_mode=None: текст — обычные URL, никаких HTML-сущностей в нём нет,
        # пусть Telegram сам распознаёт ссылки и подгружает превью.
        await message.reply(reply_text, parse_mode=None)

    return router


def _extract_urls(message: Message) -> list[str]:
    text = message.text or message.caption or ""
    entities: list[MessageEntity] = list(
        message.entities or message.caption_entities or []
    )
    urls: list[str] = []
    for ent in entities:
        if ent.type == "url":
            urls.append(ent.extract_from(text))
        elif ent.type == "text_link" and ent.url:
            urls.append(ent.url)
    return urls


async def run(settings: Settings) -> None:
    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    whitelist = ChatWhitelistMiddleware(settings.allowed_chat_ids)
    dp.message.middleware(whitelist)

    dp.include_router(_build_router(settings.target_host))

    me = await bot.get_me()
    log.info(
        "bot_started",
        username=me.username,
        whitelist_size=len(settings.allowed_chat_ids),
        target_host=settings.target_host,
    )

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
