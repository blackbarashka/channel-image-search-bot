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
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                user_id         BIGINT PRIMARY KEY,
                subscription_tier TEXT DEFAULT 'free',
                start_date      TIMESTAMPTZ DEFAULT NOW(),
                end_date        TIMESTAMPTZ,
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id               SERIAL PRIMARY KEY,
                user_id          BIGINT NOT NULL,
                payment_id       TEXT UNIQUE NOT NULL,
                subscription_tier TEXT NOT NULL,
                amount           INTEGER NOT NULL,
                currency         TEXT DEFAULT 'RUB',
                status           TEXT DEFAULT 'pending',
                created_at       TIMESTAMPTZ DEFAULT NOW(),
                confirmed_at     TIMESTAMPTZ,
                FOREIGN KEY (user_id) REFERENCES user_subscriptions(user_id)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS payments_user_idx ON payments(user_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS payments_payment_id_idx ON payments(payment_id)"
        )
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


# ---------- Подписки и лимиты ----------

CHANNEL_LIMITS = {
    "free": 1,
    "basic": 5,
    "pro": 10,
    "premium": 15,
}


async def get_user_subscription(user_id: int) -> dict:
    """Получает информацию о подписке пользователя.
    
    Возвращает: {'subscription_tier': str, 'channels_limit': int, 'channels_count': int}
    """
    pool = _require_pool()
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            "SELECT subscription_tier FROM user_subscriptions WHERE user_id = $1",
            user_id,
        )
        
        channels_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_channels WHERE user_id = $1",
            user_id,
        )
    
    tier = sub["subscription_tier"] if sub else "free"
    limit = CHANNEL_LIMITS.get(tier, 1)
    
    return {
        "subscription_tier": tier,
        "channels_limit": limit,
        "channels_count": channels_count or 0,
    }


async def set_user_subscription(user_id: int, subscription_tier: str, end_date: Optional[datetime] = None) -> None:
    """Устанавливает (или обновляет) подписку пользователя.
    
    subscription_tier: 'free', 'basic', 'pro', 'premium'
    """
    if subscription_tier not in CHANNEL_LIMITS:
        raise ValueError(f"Неизвестный уровень подписки: {subscription_tier}")
    
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_subscriptions (user_id, subscription_tier, start_date, end_date, updated_at)
            VALUES ($1, $2, NOW(), $3, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET subscription_tier = EXCLUDED.subscription_tier,
                end_date = EXCLUDED.end_date,
                updated_at = NOW()
            """,
            user_id,
            subscription_tier,
            end_date,
        )


async def can_add_channel(user_id: int) -> tuple[bool, str]:
    """Проверяет, может ли пользователь добавить канал.
    
    Возвращает: (можно_ли, сообщение)
    """
    sub_info = await get_user_subscription(user_id)
    channels_count = sub_info["channels_count"]
    channels_limit = sub_info["channels_limit"]
    tier = sub_info["subscription_tier"]
    
    if channels_count >= channels_limit:
        if tier == "free":
            msg = (
                f"❌ Вы достигли лимита: <b>1 канал</b> для бесплатного аккаунта.\n\n"
                f"Подключите подписку для добавления большего количества каналов:\n"
                f"• <b>Базовая</b> — 5 каналов\n"
                f"• <b>Профессиональная</b> — 10 каналов\n"
                f"• <b>Премиум</b> — 15 каналов\n\n"
                f"Используйте команду: /subscribe"
            )
        else:
            msg = f"❌ Вы достигли лимита: <b>{channels_limit} каналов</b> для подписки <b>{tier}</b>."
        return False, msg
    
    return True, ""


# ---------- Платежи ----------

SUBSCRIPTION_PRICES = {
    "basic": 19900,      # 199 рублей в копейках
    "pro": 39900,        # 399 рублей
    "premium": 59900,    # 599 рублей
}


async def create_payment(user_id: int, subscription_tier: str, payment_id: str) -> int:
    """Создает запись о платеже в БД.
    
    Возвращает ID платежа в БД.
    """
    if subscription_tier not in SUBSCRIPTION_PRICES:
        raise ValueError(f"Неизвестный уровень подписки: {subscription_tier}")
    
    amount = SUBSCRIPTION_PRICES[subscription_tier]
    pool = _require_pool()
    
    async with pool.acquire() as conn:
        payment_id_db = await conn.fetchval(
            """
            INSERT INTO payments (user_id, payment_id, subscription_tier, amount)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            user_id,
            payment_id,
            subscription_tier,
            amount,
        )
    return payment_id_db


async def confirm_payment(payment_id: str) -> bool:
    """Подтверждает платеж и обновляет подписку пользователя.
    
    Возвращает True если платеж был успешно подтвержден.
    """
    pool = _require_pool()
    
    async with pool.acquire() as conn:
        # Получаем информацию о платеже
        payment = await conn.fetchrow(
            "SELECT * FROM payments WHERE payment_id = $1",
            payment_id,
        )
        
        if not payment:
            logger.warning("Payment not found: %s", payment_id)
            return False
        
        if payment["status"] == "succeeded":
            logger.info("Payment already confirmed: %s", payment_id)
            return True
        
        # Обновляем статус платежа
        await conn.execute(
            """
            UPDATE payments
            SET status = 'succeeded', confirmed_at = NOW()
            WHERE payment_id = $1
            """,
            payment_id,
        )
        
        # Обновляем подписку пользователя
        tier = payment["subscription_tier"]
        user_id = payment["user_id"]
        
        # Подписка на 30 дней
        end_date = datetime.now() + __import__("datetime").timedelta(days=30)
        
        await conn.execute(
            """
            INSERT INTO user_subscriptions (user_id, subscription_tier, start_date, end_date, updated_at)
            VALUES ($1, $2, NOW(), $3, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET subscription_tier = EXCLUDED.subscription_tier,
                end_date = EXCLUDED.end_date,
                updated_at = NOW()
            """,
            user_id,
            tier,
            end_date,
        )
        
        logger.info("Payment confirmed: user_id=%s, tier=%s, payment_id=%s", user_id, tier, payment_id)
        return True


async def get_payment_by_id(payment_id: str) -> Optional[dict]:
    """Получает информацию о платеже."""
    pool = _require_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payments WHERE payment_id = $1",
            payment_id,
        )
    return dict(row) if row else None


