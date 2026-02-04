"""Обработчики команд и сообщений бота: /start, /help, /search, /stats, /abdul + меню кнопками."""

import html
import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    FSInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

logger = logging.getLogger(__name__)

router = Router(name="commands")


class SearchState(StatesGroup):
    """Состояния для диалога поиска."""
    waiting_query = State()


def main_menu() -> ReplyKeyboardMarkup:
    """Главное меню бота (reply-клавиатура)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="ℹ️ Справка"), KeyboardButton(text="🖼 Пример")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Приветствие и краткое описание бота."""
    await message.answer(
        "Привет! Я бот для поиска изображений в Telegram-канале по текстовому описанию.\n"
        "Выберите действие кнопками ниже 👇",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Справка по использованию."""
    await message.answer(
        "<b>Как пользоваться</b>\n\n"
        "🔎 <b>Поиск</b> — нажмите кнопку и введите текст запроса\n"
        "📊 <b>Статистика</b> — информация об индексе (пока заглушка)\n"
        "🖼 <b>Пример</b> — отправлю тестовое изображение\n\n"
        "Позже подключим индексацию канала и семантический поиск (ruCLIP).",
        reply_markup=main_menu(),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика по индексу (заглушка)."""
    # TODO: реальная статистика из БД
    await message.answer(
        "Статистика пока недоступна: индексация канала ещё не подключена.\n"
        "После настройки канала и индекса здесь будет число проиндексированных изображений.",
        reply_markup=main_menu(),
    )


@router.message(Command("demo"))
async def cmd_demo(message: Message) -> None:
    """Отправляет фото по команде /demo."""
    root = Path(__file__).resolve().parent.parent.parent
    photo_path = root / "image.png"
    if not photo_path.exists():
        await message.answer("Фото не найдено (image.png).", reply_markup=main_menu())
        return
    await message.answer_photo(FSInputFile(photo_path), reply_markup=main_menu())


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext) -> None:
    """
    Поиск.
    Варианты:
      - /search запрос   -> сразу обработаем запрос
      - /search          -> перейдём в режим ожидания текста
    """
    text = message.text or ""
    query = text.replace("/search", "", 1).strip() if text.startswith("/search") else text.strip()

    if not query:
        await state.set_state(SearchState.waiting_query)
        await message.answer(
            "Введите текст запроса (например: <i>закат на море</i>).",
            reply_markup=cancel_menu(),
        )
        return


    # TODO: вызов ML (ruCLIP) и поиск по векторам в БД, пагинация
    safe_query = html.escape(query[:100])
    await message.answer(
        f"Запрос «{safe_query}» принят ✅\n"
        "Семантический поиск будет доступен после подключения индекса и модели ruCLIP.",
        reply_markup=main_menu(),
    )
@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    """Информация о проекте."""
    await message.answer(
        "<b>📌 О проекте</b>\n\n"
        "<b>Название:</b> Image Search Telegram Bot\n"
        "<b>Версия:</b> 0.2 (КТ2)\n\n"
        "<b>Цель проекта:</b>\n"
        "Поиск изображений в Telegram-канале по текстовому описанию пользователя.\n\n"
        "<b>Реализовано на КТ2:</b>\n"
        "• кнопочное меню\n"
        "• режим ввода запроса без команд\n"
        "• базовая архитектура проекта\n"
        "• конфигурация через .env\n"
        "• логирование\n\n"
        "<b>Планируется:</b>\n"
        "• индексация изображений канала\n"
        "• семантический поиск (ruCLIP)\n"
        "• база данных и выдача результатов\n\n"
        "<i>Проект выполнен в рамках курсовой работы.</i>",
        reply_markup=main_menu(),
    )

def cancel_menu() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ----- КНОПКИ МЕНЮ -----

@router.message(lambda m: (m.text or "") == "🖼 Пример")
async def btn_example(message: Message) -> None:
    await cmd_demo(message)


@router.message(lambda m: (m.text or "") == "📊 Статистика")
async def btn_stats(message: Message) -> None:
    await cmd_stats(message)


@router.message(lambda m: (m.text or "") == "ℹ️ Справка")
async def btn_help(message: Message) -> None:
    await cmd_help(message)


@router.message(lambda m: (m.text or "") == "🔎 Поиск")
async def btn_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchState.waiting_query)
    await message.answer(
        "Введите текст запроса (например: <i>закат на море</i>).",
        reply_markup=cancel_menu(),
    )


# ----- ОБРАБОТКА ТЕКСТА В РЕЖИМЕ ПОИСКА -----

@router.message(lambda m: (m.text or "") == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Действие отменено 👍",
        reply_markup=main_menu(),
    )

@router.message(SearchState.waiting_query)
async def process_search_query(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if not text:
        await message.answer("Введите текст запроса или нажмите ❌ Отмена.")
        return

    # TODO: вызов ML (ruCLIP) и поиск по векторам в БД, пагинация
    safe_text = html.escape(text[:100])
    await message.answer(
        f"Запрос «{safe_text}» принят ✅\n"
        "Семантический поиск будет доступен после подключения индекса и модели ruCLIP."
    )

    await state.clear()
    await message.answer("Что дальше?", reply_markup=main_menu())


# ----- АВТООТВЕТ НА ПРИВЕТ -----
# (ставим ВЫШЕ fallback, чтобы привет не попадал в "не понял")

@router.message(lambda m: (m.text or "").strip().lower() in {"привет", "здравствуй", "здравствуйте", "hello", "hi", "hey"})
async def greet(message: Message) -> None:
    await message.answer(
        "Привет! 👋\n"
        "Нажмите 🔎 Поиск, чтобы ввести описание изображения, или откройте справку.",
        reply_markup=main_menu(),
    )


# ----- FALLBACK: ЛЮБОЕ ДРУГОЕ СООБЩЕНИЕ -----
# (обязательно САМЫЙ ПОСЛЕДНИЙ обработчик в файле)

@router.message()
async def fallback(message: Message) -> None:
    # НЕТ текста: фото/стикер/голосовое и т.д.
    if not (message.text or "").strip():
        await message.answer(
            "Я пока понимаю только текст 🙂\n"
            "Используйте кнопки меню ниже.",
            reply_markup=main_menu(),
        )
        return


    # TODO: вызов ML (ruCLIP) и поиск по векторам в БД, пагинация
    safe_query = html.escape(query[:100])
    await message.answer(
        f"Запрос «{safe_query}» принят ✅\n"
        "Семантический поиск будет доступен после подключения индекса и модели ruCLIP.",
        reply_markup=main_menu(),
    )
@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    """Информация о проекте."""
    await message.answer(
        "<b>📌 О проекте</b>\n\n"
        "<b>Название:</b> Image Search Telegram Bot\n"
        "<b>Версия:</b> 0.2 (КТ2)\n\n"
        "<b>Цель проекта:</b>\n"
        "Поиск изображений в Telegram-канале по текстовому описанию пользователя.\n\n"
        "<b>Реализовано на КТ2:</b>\n"
        "• кнопочное меню\n"
        "• режим ввода запроса без команд\n"
        "• базовая архитектура проекта\n"
        "• конфигурация через .env\n"
        "• логирование\n\n"
        "<b>Планируется:</b>\n"
        "• индексация изображений канала\n"
        "• семантический поиск (ruCLIP)\n"
        "• база данных и выдача результатов\n\n"
        "<i>Проект выполнен в рамках курсовой работы.</i>",
        reply_markup=main_menu(),
    )

def cancel_menu() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ----- КНОПКИ МЕНЮ -----

@router.message(lambda m: (m.text or "") == "🖼 Пример")
async def btn_example(message: Message) -> None:
    await cmd_demo(message)


@router.message(lambda m: (m.text or "") == "📊 Статистика")
async def btn_stats(message: Message) -> None:
    await cmd_stats(message)


@router.message(lambda m: (m.text or "") == "ℹ️ Справка")
async def btn_help(message: Message) -> None:
    await cmd_help(message)


@router.message(lambda m: (m.text or "") == "🔎 Поиск")
async def btn_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchState.waiting_query)
    await message.answer(
        "Введите текст запроса (например: <i>закат на море</i>).",
        reply_markup=cancel_menu(),
    )


# ----- ОБРАБОТКА ТЕКСТА В РЕЖИМЕ ПОИСКА -----

@router.message(lambda m: (m.text or "") == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Действие отменено 👍",
        reply_markup=main_menu(),
    )

@router.message(SearchState.waiting_query)
async def process_search_query(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if not text:
        await message.answer("Введите текст запроса или нажмите ❌ Отмена.")
        return

    # TODO: вызов ML (ruCLIP) и поиск по векторам в БД, пагинация
    safe_text = html.escape(text[:100])
    await message.answer(
        f"Запрос «{safe_text}» принят ✅\n"
        "Семантический поиск будет доступен после подключения индекса и модели ruCLIP."
    )

    await state.clear()
    await message.answer("Что дальше?", reply_markup=main_menu())


# ----- АВТООТВЕТ НА ПРИВЕТ -----
# (ставим ВЫШЕ fallback, чтобы привет не попадал в "не понял")

@router.message(lambda m: (m.text or "").strip().lower() in {"привет", "здравствуй", "здравствуйте", "hello", "hi", "hey"})
async def greet(message: Message) -> None:
    await message.answer(
        "Привет! 👋\n"
        "Нажмите 🔎 Поиск, чтобы ввести описание изображения, или откройте справку.",
        reply_markup=main_menu(),
    )


# ----- FALLBACK: ЛЮБОЕ ДРУГОЕ СООБЩЕНИЕ -----
# (обязательно САМЫЙ ПОСЛЕДНИЙ обработчик в файле)

@router.message()
async def fallback(message: Message) -> None:
    # НЕТ текста: фото/стикер/голосовое и т.д.
    if not (message.text or "").strip():
        await message.answer(
            "Я пока понимаю только текст 🙂\n"
            "Используйте кнопки меню ниже.",
            reply_markup=main_menu(),
        )
        return


    await message.answer(
        "Я не совсем понял сообщение 🤔\n\n"
        "Попробуйте:\n"
        "• нажать 🔎 Поиск и ввести описание\n"
        "• открыть ℹ️ Справка (/help)\n"
        "• посмотреть 📊 Статистика\n",
        reply_markup=main_menu(),
    )
