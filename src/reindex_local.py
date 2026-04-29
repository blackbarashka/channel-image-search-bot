"""Локальная переиндексация: берёт картинки из data/media/ и кладёт в PostgreSQL.

Полезно для отладки без Telethon. Имена файлов вида `<channel>_<message_id>.jpg`.

Запуск:
  docker compose exec bot python -m src.reindex_local
  # или локально, если есть .venv:
  python -m src.reindex_local
"""

import asyncio
import logging
import os
import re
from pathlib import Path

from src.database import add_image, close_pool, init_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT_DIR / "data" / "media"

FILE_RE = re.compile(r"^(?P<channel>.+)_(?P<msg_id>\d+)\.(jpg|jpeg|png|webp)$", re.IGNORECASE)


async def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/tgbot"
    )
    await init_pool(database_url)

    files = sorted(MEDIA_DIR.glob("*.*"))
    if not files:
        logger.warning("В %s нет файлов", MEDIA_DIR)
        await close_pool()
        return

    added = 0
    skipped = 0
    for f in files:
        m = FILE_RE.match(f.name)
        if not m:
            skipped += 1
            logger.warning("Пропуск (не подходит шаблон): %s", f.name)
            continue
        try:
            await add_image(
                message_id=int(m.group("msg_id")),
                channel=m.group("channel"),
                file_path=str(f),
                caption="",
            )
            added += 1
            logger.info("OK %s", f.name)
        except Exception as exc:
            skipped += 1
            logger.warning("Ошибка %s: %s", f.name, exc)

    await close_pool()
    logger.info("Готово. Добавлено: %d, пропущено: %d", added, skipped)


if __name__ == "__main__":
    asyncio.run(main())
