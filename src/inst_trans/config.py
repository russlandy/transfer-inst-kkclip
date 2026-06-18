"""Конфигурация приложения. Все значения берутся из .env / переменных окружения."""

from __future__ import annotations

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

    target_host: str = Field(
        default="www.kkclip.com",
        description="Хост-замена для instagram.com (без схемы и слешей)",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def _parse_chat_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(x) for x in value.split(",") if x.strip()]
        return value

    @field_validator("target_host", mode="after")
    @classmethod
    def _strip_target_host(cls, value: str) -> str:
        # На случай если в .env написали "https://www.kkclip.com/" — аккуратно срежем.
        cleaned = value.strip().removeprefix("https://").removeprefix("http://")
        return cleaned.strip("/")


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
