"""Telethon-клиент бота. Один синглтон на процесс, использует общую сессию.

Сессия лежит в data/sessions/tg_indexer.session — её создаёт `src.index_channel`
интерактивно (с вводом кода). После этого бот может ходить в Telegram неинтерактивно.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from telethon import TelegramClient

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = ROOT_DIR / "data" / "sessions"
MEDIA_DIR = ROOT_DIR / "data" / "media"

_client: Optional[TelegramClient] = None
_lock: asyncio.Lock = asyncio.Lock()


async def init_client() -> Optional[TelegramClient]:
    """Поднимает Telethon-клиент. Возвращает None, если нет API_ID/API_HASH или сессии."""
    global _client

    if _client is not None:
        return _client

    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    if not api_id_raw or not api_hash:
        logger.warning("Telethon недоступен: API_ID / API_HASH не заданы.")
        return None

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSIONS_DIR / "tg_indexer")

    if not Path(session_path + ".session").exists():
        logger.warning(
            "Telethon-сессия %s не найдена. Запустите `python -m src.index_channel`"
            " один раз для интерактивного логина.",
            session_path + ".session",
        )
        return None

    client = TelegramClient(session_path, int(api_id_raw), api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        logger.warning("Telethon-сессия не авторизована. Перелогиньтесь через index_channel.")
        await client.disconnect()
        return None

    _client = client
    logger.info("Telethon-клиент подключён.")
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None


def get_client() -> Optional[TelegramClient]:
    return _client


def get_lock() -> asyncio.Lock:
    """Lock на единственную одновременную операцию индексации."""
    return _lock
