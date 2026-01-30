# Telegram-бот для поиска изображений по описанию в канале

Бот для семантического поиска изображений в Telegram-канале по текстовому запросу (в перспективе - с использованием ruCLIP и PostgreSQL/pgvector).

## Стек (по ТЗ)

- **Python** 3.11+
- **Aiogram** 3.x - Telegram Bot API
- **PostgreSQL** 15+ (pgvector) - хранение векторов (в разработке)
- **ruCLIP** - эмбеддинги изображений и текста (в разработке)
- **Docker** - развёртывание (в разработке)

## Текущее состояние

- Реализованы команды: `/start`, `/help`, `/search`, `/stats`
- Конфигурация через `.env`
- Подключение индекса канала, ML-модели и БД - в планах

## Установка и запуск

1. Клонируйте репозиторий и перейдите в папку проекта:

   ```bash
   cd tg_bot
   ```

2. Создайте виртуальное окружение и установите зависимости:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

3. Создайте бота через [@BotFather](https://t.me/BotFather), получите токен.

4. Создайте файл `.env` в корне проекта:

   ```
   BOT_TOKEN=ваш_токен_от_BotFather
   CHANNEL_USERNAME=имя_канала_без_собаки   # опционально, для будущей индексации
   ```

5. Запустите бота:

   ```bash
   python run.py
   ```

## Команды бота

| Команда | Описание |
|--------|----------|
| `/start` | Приветствие и список команд |
| `/help` | Справка по использованию |
| `/search <запрос>` | Поиск изображений по описанию (пока заглушка) |
| `/stats` | Статистика по индексу (пока заглушка) |

## CI/CD

На каждый push и pull request в `main`/`master` запускается GitHub Actions:

- **Lint** — Ruff проверяет код (`ruff check`)
- **Format** — проверка форматирования (`ruff format --check`)
- **Smoke test** — проверка, что приложение импортируется и создаётся бот (с тестовым токеном)

Конфиг: [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Локально можно запустить те же проверки:

```bash
pip install ruff
ruff check src run.py
ruff format --check src run.py
```

## Структура проекта

```
tg_bot/
├── .github/workflows/ci.yml
├── run.py              # Точка входа
├── requirements.txt
├── pyproject.toml      # Ruff, метаданные проекта
├── .env                # Не в Git: BOT_TOKEN, CHANNEL_USERNAME
├── src/
│   ├── config.py       # Загрузка конфига из .env
│   ├── bot.py          # Создание бота и диспетчера
│   └── handlers/
│       └── commands.py # Обработчики /start, /help, /search, /stats
└── README.md
```
