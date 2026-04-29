"""CLI-индексер: создаёт/использует Telethon-сессию и индексирует канал.

Запуск:
  python -m src.index_channel @some_channel        # любой канал
  python -m src.index_channel                      # канал из CHANNEL_USERNAME (.env)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from src.database import close_pool, init_pool
from src.services.indexer_service import index_channel, normalize_username

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT_DIR / "data" / "media"
SESSIONS_DIR = ROOT_DIR / "data" / "sessions"
LIMIT = int(os.getenv("INDEX_LIMIT", "200"))


async def main() -> None:
    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/tgbot"
    )

    if not api_id or not api_hash:
        raise ValueError("API_ID / API_HASH не заданы в .env")

    if len(sys.argv) > 1:
        channel = normalize_username(sys.argv[1])
    else:
        channel = normalize_username(os.getenv("CHANNEL_USERNAME", ""))
    if not channel:
        raise ValueError("Укажите канал: `python -m src.index_channel @username`")

    await init_pool(database_url)

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSIONS_DIR / "tg_indexer")

    client = TelegramClient(session_path, int(api_id), api_hash)
    logger.info("Авторизация Telethon (потребуется код, если сессии нет)…")
    await client.start()

    try:
        result = await index_channel(client, channel, MEDIA_DIR, LIMIT)
        logger.info("Готово: %s", result)
    finally:
        await client.disconnect()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
