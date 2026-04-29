"""Слой БД: PostgreSQL + pgvector через asyncpg.

Хранит embeddings размерности 512 (ruCLIP). Поиск — по оператору <=> (cosine distance).
"""

import logging
from datetime import datetime
from typing import Optional, Union

import asyncpg
import numpy as np

from src.services import encode_image, encode_text

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512

_pool: Optional[asyncpg.Pool] = None


def _vector_literal(vec: np.ndarray) -> str:
    """pgvector принимает строку вида '[1.0,2.0,...]'."""
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


async def init_pool(database_url: str) -> asyncpg.Pool:
    """Создаёт пул соединений и инициализирует схему БД."""
    global _pool

    if _pool is not None:
        return _pool

    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with _pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS images (
                id           SERIAL PRIMARY KEY,
                message_id   BIGINT NOT NULL,
                channel      TEXT   NOT NULL,
                date         TIMESTAMPTZ,
                caption      TEXT,
                file_path    TEXT,
                file_id      TEXT,
                embedding    vector({EMBEDDING_DIM}),
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(message_id, channel)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_channels (
                user_id    BIGINT NOT NULL,
                channel    TEXT   NOT NULL,
                added_at   TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, channel)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS user_channels_user_idx ON user_channels(user_id)"
        )
        # ivfflat капризен на маленьких объёмах, поэтому пробуем HNSW (pgvector >= 0.5).
        # Если pgvector старее — fallback на seqscan (без индекса), что для тестового
        # объёма (десятки тысяч строк) приемлемо.
        await conn.execute("DROP INDEX IF EXISTS images_embedding_idx")
        try:
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS images_embedding_idx
                ON images USING hnsw (embedding vector_cosine_ops)
                """
            )
        except Exception as exc:
            logger.warning("HNSW индекс недоступен (%s), оставляем seqscan", exc)

    logger.info("PostgreSQL pool готов, схема инициализирована.")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool не инициализирован. Вызовите init_pool().")
    return _pool


def _to_datetime(date: Union[str, datetime, None]) -> Optional[datetime]:
    if date is None or isinstance(date, datetime):
        return date
    try:
        return datetime.fromisoformat(date)
    except ValueError:
        return None


async def add_image(
    message_id: int,
    channel: str,
    file_path: str,
    caption: str = "",
    file_id: str = "",
    date: Union[str, datetime, None] = None,
) -> None:
    """Кодирует изображение через ruCLIP и сохраняет запись в БД."""
    embedding = encode_image(file_path)
    vec_literal = _vector_literal(embedding)
    dt = _to_datetime(date)

    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO images
                (message_id, channel, caption, file_id, file_path, date, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
            ON CONFLICT (message_id, channel) DO UPDATE
                SET caption = EXCLUDED.caption,
                    file_path = EXCLUDED.file_path,
                    embedding = EXCLUDED.embedding
            """,
            message_id,
            channel,
            caption,
            file_id,
            file_path,
            dt,
            vec_literal,
        )


async def search_images(
    query: str,
    limit: int = 5,
    user_id: Optional[int] = None,
    channel: Optional[str] = None,
) -> list[dict]:
    """Семантический поиск: текст -> embedding -> top-K похожих картинок.

    Параметры:
      user_id  — если задан, ищем только в каналах пользователя (JOIN с user_channels).
      channel  — если задан, дополнительно фильтруем по конкретному каналу.

    Возвращает список dict: message_id, channel, caption, file_path, file_id, date, score.
    """
    query_vec = encode_text(query)
    vec_literal = _vector_literal(query_vec)

    pool = _require_pool()
    async with pool.acquire() as conn:
        if user_id is not None and channel is not None:
            sql = f"""
                SELECT
                    i.message_id, i.channel, i.caption, i.file_path, i.file_id, i.date,
                    1 - (i.embedding <=> '{vec_literal}'::vector) AS score
                FROM images i
                JOIN user_channels uc
                  ON uc.channel = i.channel AND uc.user_id = $1
                WHERE i.embedding IS NOT NULL
                  AND i.channel = $2
                ORDER BY i.embedding <=> '{vec_literal}'::vector
                LIMIT $3
            """
            rows = await conn.fetch(sql, user_id, channel, limit)
        elif user_id is not None:
            sql = f"""
                SELECT
                    i.message_id, i.channel, i.caption, i.file_path, i.file_id, i.date,
                    1 - (i.embedding <=> '{vec_literal}'::vector) AS score
                FROM images i
                JOIN user_channels uc
                  ON uc.channel = i.channel AND uc.user_id = $1
                WHERE i.embedding IS NOT NULL
                ORDER BY i.embedding <=> '{vec_literal}'::vector
                LIMIT $2
            """
            rows = await conn.fetch(sql, user_id, limit)
        elif channel is not None:
            sql = f"""
                SELECT
                    message_id, channel, caption, file_path, file_id, date,
                    1 - (embedding <=> '{vec_literal}'::vector) AS score
                FROM images
                WHERE embedding IS NOT NULL AND channel = $1
                ORDER BY embedding <=> '{vec_literal}'::vector
                LIMIT $2
            """
            rows = await conn.fetch(sql, channel, limit)
        else:
            sql = f"""
                SELECT
                    message_id, channel, caption, file_path, file_id, date,
                    1 - (embedding <=> '{vec_literal}'::vector) AS score
                FROM images
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> '{vec_literal}'::vector
                LIMIT $1
            """
            rows = await conn.fetch(sql, limit)

        logger.info(
            "search_images: user_id=%s, channel=%s, query=%r, returned=%s",
            user_id, channel, query, len(rows),
        )

    return [dict(r) for r in rows]


async def add_user_channel(user_id: int, channel: str) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_channels (user_id, channel)
            VALUES ($1, $2)
            ON CONFLICT (user_id, channel) DO NOTHING
            """,
            user_id,
            channel,
        )


async def remove_user_channel(user_id: int, channel: str) -> bool:
    pool = _require_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_channels WHERE user_id = $1 AND channel = $2",
            user_id,
            channel,
        )
    # asyncpg возвращает строку вида 'DELETE 1' / 'DELETE 0'
    return result.endswith(" 1")


async def list_user_channels(user_id: int) -> list[dict]:
    """Возвращает каналы пользователя со счётчиком картинок и датой последней."""
    pool = _require_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                uc.channel,
                uc.added_at,
                COUNT(i.id)               AS images_count,
                MAX(i.date)               AS last_message_date
            FROM user_channels uc
            LEFT JOIN images i ON i.channel = uc.channel
            WHERE uc.user_id = $1
            GROUP BY uc.channel, uc.added_at
            ORDER BY uc.added_at
            """,
            user_id,
        )
    return [dict(r) for r in rows]


async def get_stats(user_id: Optional[int] = None) -> dict:
    pool = _require_pool()
    async with pool.acquire() as conn:
        if user_id is None:
            count = await conn.fetchval("SELECT COUNT(*) FROM images")
            last_date = await conn.fetchval("SELECT MAX(date) FROM images")
            channels = await conn.fetchval("SELECT COUNT(DISTINCT channel) FROM images")
        else:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM images i
                JOIN user_channels uc
                  ON uc.channel = i.channel AND uc.user_id = $1
                """,
                user_id,
            )
            last_date = await conn.fetchval(
                """
                SELECT MAX(i.date) FROM images i
                JOIN user_channels uc
                  ON uc.channel = i.channel AND uc.user_id = $1
                """,
                user_id,
            )
            channels = await conn.fetchval(
                "SELECT COUNT(*) FROM user_channels WHERE user_id = $1", user_id
            )

    return {
        "images_count": count or 0,
        "channels_count": channels or 0,
        "last_indexed": str(last_date) if last_date else "—",
    }
