# Telegram-бот для поиска изображений по описанию в канале

Курсовой проект (БПИ234, ВШЭ).
Авторы: **У. Р. Мусаев** (ML-модуль на ruCLIP), **А. О. Магомедов** (Telegram + БД).

Семантический поиск изображений в Telegram-канале по текстовому описанию.
Используется CLIP-модель **ruCLIP**: текст и картинки кодируются в одно векторное
пространство (512 dim), поиск — по косинусному расстоянию в **PostgreSQL + pgvector**.

## Стек

| Слой        | Технология                            |
| ----------- | ------------------------------------- |
| Bot API     | aiogram 3                             |
| ML          | ruCLIP (ai-forever/ru-clip), PyTorch  |
| БД          | PostgreSQL 15 + pgvector              |
| Драйвер БД  | asyncpg                               |
| Indexer     | Telethon (user-аккаунт)               |
| Деплой      | Docker, docker-compose                |

## Возможности

- `/start` — приветствие и меню
- `/add_channel @username` — добавить публичный канал и проиндексировать его в фоне
- `/channels` — список своих каналов со счётчиком фото
- `/remove_channel @username` — удалить канал
- `/search <запрос>` — семантический поиск картинок **по своим каналам** (рус/англ)
- `/stats` — состояние индекса (количество, дата последнего обновления)
- `/help`, `/about` — справка и информация о проекте
- Пагинация результатов (inline-кнопки), процент релевантности, дата, ссылка на сообщение в канале

Каждый пользователь имеет свой набор каналов. При добавлении канала бот сразу запускает
индексацию (Telethon-сессия одна на сервис, поэтому одновременно индексируется один канал —
остальные ставятся в очередь через asyncio Lock).

## Архитектура

```
TestTGbotCourseProject/
├── docker-compose.yml      # PostgreSQL+pgvector + бот
├── Dockerfile              # Образ бота
├── requirements.txt
├── .env.example            # Шаблон переменных окружения
└── src/
    ├── bot.py              # Точка входа: aiogram, lifespan пула + Telethon
    ├── config.py           # BotConfig / TelegramClientConfig из .env
    ├── index_channel.py    # CLI-индексер (создаёт сессию Telethon, гонит канал)
    ├── reindex_local.py    # Локальная переиндексация из data/media/
    ├── database/
    │   └── db.py           # asyncpg + pgvector: images, user_channels, поиск с user_id
    ├── services/
    │   ├── ruclip_service.py     # ruCLIP: encode_text/encode_image/cosine_similarity
    │   ├── telethon_client.py    # Синглтон Telethon + asyncio.Lock на индексацию
    │   └── indexer_service.py    # index_channel(client, username) — общий код
    └── handlers/
        └── commands.py     # FSM, команды (/add_channel, /search, ...), inline-пагинация
```

## Запуск через Docker (рекомендуется)

```bash
cp .env.example .env
# заполните BOT_TOKEN, CHANNEL_USERNAME, API_ID, API_HASH

docker compose up -d --build
docker compose logs -f bot
```

После старта `db` контейнера расширение `vector` создаётся автоматически
при первом подключении бота (`CREATE EXTENSION IF NOT EXISTS vector`).

## Запуск без Docker (локально)

1. Поднять PostgreSQL с pgvector (например, через `docker run pgvector/pgvector:pg15`).
2. Установить зависимости:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Заполнить `.env` (см. `.env.example`).
4. Запустить бота:
   ```bash
   python -m src.bot
   ```

## Индексирование канала

Обычный путь — через бота: команда `/add_channel @some_channel`.

Из CLI (нужен один раз для интерактивного логина Telethon):

```bash
python -m src.index_channel @some_channel       # любой канал
python -m src.index_channel                     # канал из CHANNEL_USERNAME
```

Скачивает фото из канала, кодирует каждое через ruCLIP и сохраняет вектор в таблицу
`images`. Сессия сохраняется в `data/sessions/tg_indexer.session` и переиспользуется
ботом — поэтому **первый раз** обязательно запустить CLI-индексер для логина по SMS-коду.

## Соответствие ТЗ

- ✅ Команды `/start`, `/search`, `/help`, `/stats` (плюс `/about`, `/add_channel`, `/channels`, `/remove_channel`)
- ✅ ruCLIP, embeddings 512 dim, поддержка русского и английского
- ✅ PostgreSQL 15 + pgvector, индекс HNSW с `vector_cosine_ops`
- ✅ Асинхронность: `asyncio` + `asyncpg`, пул соединений, asyncio.Lock на одновременную индексацию
- ✅ Пагинация результатов, процент релевантности, дата, ссылка на сообщение
- ✅ Логирование, обработка исключений
- ✅ Развёртывание через Docker
- ✅ Многопользовательский режим: `user_channels`, изоляция данных по `user_id`

## Лицензия

MIT
