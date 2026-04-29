"""Индексация одного канала через готовый Telethon-клиент.

Используется и из CLI (`src.index_channel`), и из бота (когда пользователь добавляет канал).
"""

import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

from src.database import add_image

logger = logging.getLogger(__name__)


def normalize_username(raw: str) -> str:
    """Чистит ввод от @, https://t.me/, t.me/ и пробелов."""
    s = raw.strip().lstrip("@")
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip("/")


async def resolve_channel(client: TelegramClient, channel_username: str):
    """Возвращает entity канала или бросает исключение, если канал недоступен."""
    return await client.get_entity(channel_username)


async def index_channel(
    client: TelegramClient,
    channel_username: str,
    media_dir: Path,
    limit: int = 200,
) -> dict:
    """Индексирует фото из канала. Использует уже подключённый Telethon-клиент.

    Возвращает {'added': N, 'skipped': M, 'channel': str}.
    """
    media_dir.mkdir(parents=True, exist_ok=True)
    entity = await resolve_channel(client, channel_username)

    title = getattr(entity, "title", channel_username)
    if not isinstance(entity, (Channel, Chat)):
        raise ValueError(f"'{channel_username}' — не канал/группа")

    added = 0
    skipped = 0

    async for message in client.iter_messages(entity, limit=limit):
        if not message.photo:
            continue

        file_path = media_dir / f"{channel_username}_{message.id}.jpg"
        if not file_path.exists():
            await client.download_media(message, file=file_path)

        try:
            await add_image(
                message_id=message.id,
                channel=channel_username,
                caption=message.message or "",
                file_path=str(file_path),
                date=message.date,
            )
            added += 1
        except Exception as exc:
            skipped += 1
            logger.warning("[%s] message_id=%s: %s", channel_username, message.id, exc)

    logger.info("Индексация %s (%s): added=%d, skipped=%d", channel_username, title, added, skipped)
    return {"channel": channel_username, "title": title, "added": added, "skipped": skipped}
