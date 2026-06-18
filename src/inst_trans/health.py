"""Проверка зеркал: возвращает первое, на котором сервер живой и отдаёт 2xx/3xx.

Содержательно угадать «отрендерит ли Telegram превью» по HTML невозможно: у разных
зеркал разные стратегии (kkclip отдаёт прямой video/mp4-редирект, eeinstagram —
meta-refresh обратно на instagram.com, который Telegram потом сам обрабатывает),
поэтому HTML-сигналы вводят в заблуждение. Поэтому проверяем минимально — что
зеркало вообще доступно по сети — и доверяем порядку приоритета в TARGET_HOSTS.

Если зеркало стало возвращать сломанное превью — переставь его в конец списка
в .env, не нужно править код.
"""

from __future__ import annotations

import asyncio

import aiohttp
import structlog

from inst_trans.converter import convert_to_mirrors

log = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=5.0, connect=3.0)

# UA, который Telegram использует для построения превью. Многие зеркала отдают
# другой HTML обычному браузеру — нам нужна именно «телеграмная» ветка.
_TELEGRAM_UA = "TelegramBot (like TwitterBot)"


async def find_working_mirror(url: str, target_hosts: list[str]) -> str | None:
    """Для Instagram-ссылки вернуть первое зеркало, до которого сервер откликается.

    Зеркала проверяются в порядке приоритета. Возвращает None, если url — не
    поддерживаемая Instagram-ссылка либо все зеркала недоступны.
    """
    candidates = convert_to_mirrors(url, target_hosts)
    if not candidates:
        return None

    headers = {"User-Agent": _TELEGRAM_UA, "Accept": "text/html,*/*"}
    async with aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT, headers=headers) as session:
        for candidate in candidates:
            verdict = await _check_alive(session, candidate)
            if verdict == "ok":
                return candidate
            log.info("mirror_skipped", url=candidate, reason=verdict)
    return None


async def _check_alive(session: aiohttp.ClientSession, url: str) -> str:
    """'ok' если сервер ответил 2xx/3xx, иначе — короткая причина для лога."""
    try:
        async with session.get(url, allow_redirects=False) as resp:
            if 200 <= resp.status < 400:
                return "ok"
            return f"http_{resp.status}"
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return f"network_{type(exc).__name__}"
