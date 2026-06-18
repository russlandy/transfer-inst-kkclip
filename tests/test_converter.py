from __future__ import annotations

import pytest

from inst_trans.converter import convert_to_mirrors, convert_url

TARGET = "www.kkclip.com"


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        (
            "https://www.instagram.com/reel/DZtsG07smnC/?igsh=cDJueTRudm56OTJy",
            "https://www.kkclip.com/reel/DZtsG07smnC/?igsh=cDJueTRudm56OTJy",
        ),
        (
            "https://instagram.com/reel/ABC/",
            "https://www.kkclip.com/reel/ABC/",
        ),
        (
            "https://www.instagram.com/tv/XYZ/",
            "https://www.kkclip.com/tv/XYZ/",
        ),
        (
            "https://www.instagram.com/share/reel/QWE/?igsh=foo",
            "https://www.kkclip.com/share/reel/QWE/?igsh=foo",
        ),
        (
            "https://www.instagram.com/share/RTY/",
            "https://www.kkclip.com/share/RTY/",
        ),
        # uppercase host — Instagram сам нормализует, но мы тоже умеем
        (
            "https://WWW.Instagram.com/reel/ABC/",
            "https://www.kkclip.com/reel/ABC/",
        ),
        # http → https (на всякий)
        (
            "http://www.instagram.com/reel/ABC/",
            "https://www.kkclip.com/reel/ABC/",
        ),
    ],
)
def test_convert_supported(src: str, expected: str) -> None:
    assert convert_url(src, TARGET) == expected


@pytest.mark.parametrize(
    "src",
    [
        # /p/ намеренно не поддержан — пользователь его не выбрал
        "https://www.instagram.com/p/ABC/",
        # профиль
        "https://www.instagram.com/someuser/",
        # сторонний хост
        "https://example.com/reel/ABC/",
        # не http(s)
        "ftp://www.instagram.com/reel/ABC/",
        # мусор
        "not a url",
        "",
    ],
)
def test_convert_unsupported(src: str) -> None:
    assert convert_url(src, TARGET) is None


def test_convert_to_mirrors_preserves_order() -> None:
    src = "https://www.instagram.com/reel/ABC/?igsh=foo"
    hosts = ["www.kkclip.com", "www.eeinstagram.com", "www.ddinstagram.com"]
    assert convert_to_mirrors(src, hosts) == [
        "https://www.kkclip.com/reel/ABC/?igsh=foo",
        "https://www.eeinstagram.com/reel/ABC/?igsh=foo",
        "https://www.ddinstagram.com/reel/ABC/?igsh=foo",
    ]


def test_convert_to_mirrors_unsupported() -> None:
    assert convert_to_mirrors("https://example.com/reel/ABC/", ["www.kkclip.com"]) == []


def test_convert_to_mirrors_empty_hosts() -> None:
    assert convert_to_mirrors("https://www.instagram.com/reel/ABC/", []) == []
