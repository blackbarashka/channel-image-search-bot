"""Обработчики команд: /start, /help, /search, /stats."""
import html
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Приветствие и краткое описание бота."""
    await message.answer(
        "Привет! Я бот для поиска изображений в Telegram-канале по текстовому описанию.\n\n"
        "Команды:\n"
        "/search запрос — поиск картинок по описанию\n"
        "/help — справка\n"
        "/stats — статистика (пока в разработке)"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Справка по использованию."""
    await message.answer(
        "Как пользоваться:\n\n"
        "• Отправьте /search и текст запроса, например:\n"
        "  /search закат на море\n\n"
        "• Поддерживаются запросы на русском и английском.\n"
        "• Результаты показываются с предпросмотром и ссылкой на сообщение в канале.\n\n"
        "Индексация канала и семантический поиск (ruCLIP) будут подключены в следующих версиях."
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика по индексу (заглушка)."""
    # TODO: реальная статистика из БД
    await message.answer(
        "Статистика пока недоступна: индексация канала ещё не подключена.\n"
        "После настройки канала и индекса здесь будет число проиндексированных изображений."
    )


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    """Поиск по описанию (заглушка до подключения ruCLIP и БД)."""
    text = message.text or ""
    # Убираем команду /search
    query = text.replace("/search", "").strip() if "/search" in text else text.strip()

    if not query:
        await message.answer(
            "Напишите запрос после команды, например:\n/search закат на море"
        )
        return

    # TODO: вызов ML (ruCLIP) и поиск по векторам в БД, пагинация
    safe_query = html.escape(query[:100])
    await message.answer(
        f"Запрос «{safe_query}» принят.\n"
        "Семантический поиск будет доступен после подключения индекса и модели ruCLIP."
    )
