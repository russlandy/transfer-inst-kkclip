"""Подмена Instagram-ссылок на kkclip-зеркало (или другой целевой хост)."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_INSTAGRAM_HOSTS = frozenset({"instagram.com", "www.instagram.com"})

# Префиксы пути, которые отдаём на kkclip. /share/ покрывает и /share/reel/.
_SUPPORTED_PATH_PREFIXES: tuple[str, ...] = ("/reel/", "/tv/", "/share/")


def convert_url(url: str, target_host: str) -> str | None:
    """Заменить хост Instagram-ссылки на ``target_host``.

    Возвращает None, если url не похож на поддерживаемую Instagram-ссылку —
    тогда подменять нечего и сообщение в чате не нужно.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None

    if parts.scheme not in ("http", "https"):
        return None

    host = (parts.hostname or "").lower()
    if host not in _INSTAGRAM_HOSTS:
        return None

    if not _is_supported_path(parts.path):
        return None

    return urlunsplit(("https", target_host, parts.path, parts.query, parts.fragment))


def convert_to_mirrors(url: str, target_hosts: list[str]) -> list[str]:
    """Сконвертировать Instagram-ссылку в список вариантов по каждому зеркалу.

    Порядок зеркал сохраняется (первый — основной). Если ссылка не Instagram
    или путь не из поддерживаемых — пустой список.
    """
    result: list[str] = []
    for host in target_hosts:
        converted = convert_url(url, host)
        if converted is not None:
            result.append(converted)
    return result


def _is_supported_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SUPPORTED_PATH_PREFIXES)
