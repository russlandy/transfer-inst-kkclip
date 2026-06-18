"""Скачивание Instagram-видео через yt-dlp.

Без cookies Instagram возвращает "empty media response" — поэтому загрузка
включается только если в settings.cookies_path указан путь к рабочему
Netscape-cookies-файлу от IG-аккаунта (см. README, раздел про cookies).

Скачиваем в переданную временную папку, отдаём путь к итоговому .mp4.
Если yt-dlp не справился (cookies истекли, IG заблокировал, контент
приватный, файл больше лимита) — возвращаем None, и бот свалится на
резервную ссылку через зеркало.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import structlog
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

log = structlog.get_logger(__name__)

# Telegram Bot API ограничивает send_video файлами до 50 МБ.
# Берём запас в 1 МБ под HTTP-обёртку.
_MAX_SIZE_BYTES = 49 * 1024 * 1024

# Общий timeout на загрузку (сеть + диск). 50 МБ при IG ~1 МБ/с = ~50 сек,
# плюс запас на установку соединения и парсинг.
_DOWNLOAD_TIMEOUT_S = 75.0

# Реалистичный браузерный UA. С дефолтным UA yt-dlp Instagram возвращает
# "empty media response" даже при валидных cookies.
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def download_to(
    url: str,
    target_dir: Path,
    cookies_path: Path | None = None,
) -> Path | None:
    """Скачать видео из ``url`` в ``target_dir``. Вернуть путь к .mp4 или None.

    target_dir создаёт и чистит вызывающая сторона (обычно через
    ``tempfile.TemporaryDirectory``). cookies_path — путь к Netscape-cookies-файлу;
    если None или файл отсутствует, скачивание не выполняется (без cookies IG
    отдаёт пустой ответ).
    """
    if cookies_path is None or not cookies_path.is_file():
        log.info("download_skipped_no_cookies", cookies_path=str(cookies_path))
        return None

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_sync, url, target_dir, cookies_path),
            timeout=_DOWNLOAD_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        log.info("download_timeout", url=url)
        return None


def _download_sync(url: str, target_dir: Path, cookies_path: Path) -> Path | None:
    # yt-dlp по выходу обновляет cookies-файл (свежие токены сессии). Не хотим
    # трогать «золотой» файл на диске — копируем во временную папку, оригинал
    # остаётся неизменным (systemd может монтировать его read-only).
    tmp_cookies = target_dir / "cookies.txt"
    shutil.copy2(cookies_path, tmp_cookies)

    out_template = str(target_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        # Лучшее mp4 одним файлом, без необходимости в ffmpeg-мерже.
        "format": "best[ext=mp4][filesize<49M]/best[ext=mp4]/best",
        "cookiefile": str(tmp_cookies),
        "http_headers": {"User-Agent": _CHROME_UA},
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "max_filesize": _MAX_SIZE_BYTES,
        "retries": 1,
        "concurrent_fragment_downloads": 1,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError as exc:
        log.info("download_failed", url=url, error=str(exc))
        return None
    except Exception as exc:  # noqa: BLE001 — yt-dlp может бросить что угодно
        log.warning("download_error", url=url, error=str(exc), exc_type=type(exc).__name__)
        return None

    # Находим скачанный файл (yt-dlp кладёт его рядом с шаблоном).
    # Исключаем cookies.txt — это служебная копия, не видео.
    files = [
        p
        for p in target_dir.iterdir()
        if p.is_file() and p.stat().st_size > 0 and p.name != "cookies.txt"
    ]
    if not files:
        log.info("download_empty", url=url)
        return None

    # Берём самый крупный — на случай если yt-dlp положил несколько вариантов.
    chosen = max(files, key=lambda p: p.stat().st_size)
    if chosen.stat().st_size > _MAX_SIZE_BYTES:
        log.info("download_too_large", url=url, size=chosen.stat().st_size)
        return None

    return chosen
