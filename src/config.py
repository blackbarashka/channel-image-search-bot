import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class BotConfig:
    token: str
    channel_username: str = ""
    database_url: str = ""
    search_limit: int = 5
    page_size: int = 1

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("BOT_TOKEN не задан")

        return cls(
            token=token,
            channel_username=os.getenv("CHANNEL_USERNAME", "").strip(),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/tgbot",
            ).strip(),
            search_limit=int(os.getenv("SEARCH_LIMIT", "5")),
            page_size=int(os.getenv("PAGE_SIZE", "1")),
        )


@dataclass(frozen=True)
class TelegramClientConfig:
    api_id: int
    api_hash: str
    channel_username: str
    database_url: str

    @classmethod
    def from_env(cls) -> "TelegramClientConfig":
        api_id = os.getenv("API_ID", "").strip()
        api_hash = os.getenv("API_HASH", "").strip()
        channel_username = os.getenv("CHANNEL_USERNAME", "").strip()

        if not api_id:
            raise ValueError("API_ID не задан")
        if not api_hash:
            raise ValueError("API_HASH не задан")
        if not channel_username:
            raise ValueError("CHANNEL_USERNAME не задан")

        return cls(
            api_id=int(api_id),
            api_hash=api_hash,
            channel_username=channel_username,
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/tgbot",
            ).strip(),
        )


@dataclass(frozen=True)
class YookassaConfig:
    shop_id: str
    api_key: str

    @classmethod
    def from_env(cls) -> "YookassaConfig":
        shop_id = os.getenv("YOOKASSA_SHOP_ID", "").strip()
        api_key = os.getenv("YOOKASSA_API_KEY", "").strip()

        if not shop_id or not api_key:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("YOOKASSA_SHOP_ID или YOOKASSA_API_KEY не заданы — платежи отключены")

        return cls(
            shop_id=shop_id,
            api_key=api_key,
        )
