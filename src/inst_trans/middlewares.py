"""Пропускает события только из разрешённых чатов."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

log = structlog.get_logger(__name__)


class ChatWhitelistMiddleware(BaseMiddleware):
    """Пропускает только сообщения из чатов с разрешённым chat_id.

    Команду /chatid пропускаем всегда — чтобы можно было узнать id чата
    при первоначальной настройке.
    """

    def __init__(self, allowed_chat_ids: list[int]) -> None:
        self._allowed = set(allowed_chat_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        if _is_chatid_command(event):
            return await handler(event, data)

        if event.chat.id not in self._allowed:
            log.info(
                "chat_not_allowed",
                chat_id=event.chat.id,
                chat_type=event.chat.type,
                title=event.chat.title,
            )
            return None

        return await handler(event, data)


def _is_chatid_command(message: Message) -> bool:
    text = message.text or message.caption or ""
    # /chatid, /chatid@inst_trans_bot — в любом регистре
    first = text.strip().split()[:1]
    if not first:
        return False
    head = first[0].lower()
    return head == "/chatid" or head.startswith("/chatid@")
