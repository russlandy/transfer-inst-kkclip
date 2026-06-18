"""Точка входа: python -m inst_trans."""

from __future__ import annotations

import asyncio
import sys

import structlog

from inst_trans.bot import run
from inst_trans.config import load_settings
from inst_trans.logging_setup import configure_logging

log = structlog.get_logger(__name__)


def main() -> None:
    settings = load_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    if not settings.allowed_chat_ids:
        log.warning(
            "empty_whitelist",
            message="ALLOWED_CHAT_IDS пуст — добавь бота в чат, напиши /chatid, "
            "впиши id в .env и перезапусти.",
        )

    try:
        asyncio.run(run(settings))
    except (KeyboardInterrupt, SystemExit):
        log.info("bot_stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
