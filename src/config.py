"""Конфигурация бота из переменных окружения."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class BotConfig:
    """Настройки бота."""

    token: str
    # Канал для индексации (username без @ или ID)
    channel_username: str = ""

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "BOT_TOKEN не задан. Создайте файл .env и укажите BOT_TOKEN=..."
            )
        return cls(
            token=token,
            channel_username=os.getenv("CHANNEL_USERNAME", "").strip(),
        )
