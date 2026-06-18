"""Сборка Bot/Dispatcher, регистрация хэндлеров, запуск long-polling."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message, MessageEntity

from inst_trans.config import Settings
from inst_trans.converter import convert_url
from inst_trans.downloader import download_to
from inst_trans.health import find_working_mirror
from inst_trans.middlewares import ChatWhitelistMiddleware

log = structlog.get_logger(__name__)


def _build_router(target_hosts: list[str], cookies_path: Path | None) -> Router:
    router = Router(name="root")

    @router.message(Command("chatid"))
    async def cmd_chatid(message: Message) -> None:
        await message.answer(f"chat_id: <code>{message.chat.id}</code>")

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "Привет! Я перезаливаю Instagram-видео в чат, чтобы они проигрывались "
            "прямо в Telegram. Если не получится скачать — пришлю ссылку на зеркало."
        )

    @router.message()
    async def on_any_message(message: Message) -> None:
        ig_urls = _extract_instagram_urls(message)
        if not ig_urls:
            return

        # Каждую ссылку обрабатываем независимо, параллельно: download → reply_video,
        # при провале — резерв через find_working_mirror.
        outcomes = await asyncio.gather(
            *(_handle_ig_url(message, u, target_hosts, cookies_path) for u in ig_urls),
            return_exceptions=False,
        )
        log.info(
            "handled",
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else None,
            outcomes=outcomes,
        )

    return router


async def _handle_ig_url(
    message: Message,
    url: str,
    target_hosts: list[str],
    cookies_path: Path | None,
) -> str:
    """Прислать видео скачиванием, при провале — ссылкой на зеркало.

    Возвращает короткий маркер для лога: ``video``, ``mirror`` или ``none``.
    """
    with tempfile.TemporaryDirectory(prefix="inst-trans-") as tmp_str:
        tmp = Path(tmp_str)
        video_path = await download_to(url, tmp, cookies_path)
        if video_path is not None:
            try:
                await message.reply_video(FSInputFile(video_path))
                return "video"
            except Exception as exc:  # noqa: BLE001 — Telegram любые отдаст
                log.warning("send_video_failed", url=url, error=str(exc))

    mirror = await find_working_mirror(url, target_hosts)
    if mirror is not None:
        await message.reply(mirror, parse_mode=None)
        return "mirror"

    log.warning("no_video_no_mirror", url=url)
    return "none"


def _extract_instagram_urls(message: Message) -> list[str]:
    """Достать из сообщения только поддерживаемые Instagram-ссылки (без дублей)."""
    text = message.text or message.caption or ""
    entities: list[MessageEntity] = list(
        message.entities or message.caption_entities or []
    )
    seen: set[str] = set()
    result: list[str] = []
    for ent in entities:
        if ent.type == "url":
            url = ent.extract_from(text)
        elif ent.type == "text_link" and ent.url:
            url = ent.url
        else:
            continue
        if url in seen:
            continue
        # convert_url возвращает None для не-IG / неподдерживаемого пути.
        if convert_url(url, "_") is None:
            continue
        seen.add(url)
        result.append(url)
    return result


async def run(settings: Settings) -> None:
    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    whitelist = ChatWhitelistMiddleware(settings.allowed_chat_ids)
    dp.message.middleware(whitelist)

    dp.include_router(_build_router(settings.target_hosts, settings.cookies_path))

    cookies_present = bool(
        settings.cookies_path is not None and settings.cookies_path.is_file()
    )
    me = await bot.get_me()
    log.info(
        "bot_started",
        username=me.username,
        whitelist_size=len(settings.allowed_chat_ids),
        target_hosts=settings.target_hosts,
        cookies_present=cookies_present,
    )

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
