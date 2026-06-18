"""Конфигурация приложения. Все значения берутся из .env / переменных окружения."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    telegram_bot_token: SecretStr = Field(..., description="Токен бота от @BotFather")

    allowed_chat_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        description="Telegram chat IDs, в которых бот реагирует",
    )

    cookies_path: Path | None = Field(
        default=None,
        description=(
            "Путь к Netscape-cookies-файлу IG-аккаунта для yt-dlp. "
            "Если файла нет или путь пустой — скачивание отключено, бот сразу "
            "отвечает ссылкой через зеркало."
        ),
    )

    target_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "www.kkclip.com",
            "www.eeinstagram.com",
            "www.ddinstagram.com",
        ],
        description=(
            "Список хостов-зеркал через запятую, в порядке приоритета. "
            "Первый используется как основной (с превью), остальные — как резерв."
        ),
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def _parse_chat_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(x) for x in value.split(",") if x.strip()]
        return value

    @field_validator("target_hosts", mode="before")
    @classmethod
    def _parse_target_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            parts = [x.strip() for x in value.split(",") if x.strip()]
            return [_clean_host(p) for p in parts] or None
        if isinstance(value, list):
            return [_clean_host(str(x)) for x in value]
        return value


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def _clean_host(value: str) -> str:
    """instagram.com/ → instagram.com; https://x.com → x.com."""
    cleaned = value.strip().removeprefix("https://").removeprefix("http://")
    return cleaned.strip("/")
