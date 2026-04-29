"""Обработчики команд и сообщений бота."""

import asyncio
import html
import logging
import os
from pathlib import Path
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from src.database import (
    add_user_channel,
    get_stats,
    list_user_channels,
    remove_user_channel,
    search_images,
)
from src.services import MEDIA_DIR, get_client, get_lock
from src.services.indexer_service import index_channel, normalize_username, resolve_channel

logger = logging.getLogger(__name__)
router = Router(name="commands")

SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", "5"))
INDEX_LIMIT = int(os.getenv("INDEX_LIMIT", "200"))


class SearchState(StatesGroup):
    waiting_query = State()


class AddChannelState(StatesGroup):
    waiting_username = State()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="📺 Мои каналы")],
            [KeyboardButton(text="➕ Добавить канал"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="ℹ️ Справка"), KeyboardButton(text="🧾 О проекте")],
        ],
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------- /start /help /about /stats ----------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я бот для поиска изображений в Telegram-каналах по описанию.\n"
        "Использую модель <b>ruCLIP</b> и PostgreSQL + pgvector.\n\n"
        "Добавьте свой канал кнопкой <b>«➕ Добавить канал»</b>, "
        "после индексации можно искать.",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Команды:</b>\n"
        "/add_channel &lt;@username&gt; — добавить публичный канал и проиндексировать\n"
        "/channels — список ваших каналов\n"
        "/remove_channel &lt;@username&gt; — удалить канал из ваших\n"
        "/search — выбор канала и ввод запроса\n"
        "/search &lt;запрос&gt; — поиск по всем вашим каналам\n"
        "/search &lt;@channel&gt; &lt;запрос&gt; — поиск в одном канале\n"
        "/stats — состояние индекса\n"
        "/about — о проекте\n"
        "/help — эта справка",
        reply_markup=main_menu(),
    )


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(
        "<b>Telegram-бот для поиска изображений по описанию в канале</b>\n\n"
        "Курсовой проект, БПИ234.\n"
        "Авторы: У. Р. Мусаев (ML), А. О. Магомедов (Telegram + БД).\n\n"
        "Стек: Python 3.11, aiogram 3, ruCLIP, PostgreSQL 15 + pgvector, asyncpg, Docker.",
        reply_markup=main_menu(),
        disable_web_page_preview=True,
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    try:
        stats = await get_stats(user_id=message.from_user.id)
    except Exception as exc:
        logger.exception("get_stats")
        await message.answer(f"Ошибка БД: {exc}", reply_markup=main_menu())
        return

    await message.answer(
        "<b>📊 Статистика</b>\n\n"
        f"Каналов: <b>{stats['channels_count']}</b>\n"
        f"Изображений в индексе: <b>{stats['images_count']}</b>\n"
        f"Последнее обновление: <code>{stats['last_indexed']}</code>",
        reply_markup=main_menu(),
    )


# ---------- Каналы ----------

@router.message(Command("channels"))
async def cmd_channels(message: Message) -> None:
    rows = await list_user_channels(message.from_user.id)
    if not rows:
        await message.answer(
            "У вас пока нет каналов. Нажмите «➕ Добавить канал».",
            reply_markup=main_menu(),
        )
        return

    lines = ["<b>📺 Ваши каналы:</b>", ""]
    for r in rows:
        ch = html.escape(r["channel"])
        cnt = r["images_count"] or 0
        last = r["last_message_date"]
        last_str = str(last)[:10] if last else "—"
        lines.append(f"• <code>@{ch}</code> — фото: <b>{cnt}</b>, посл.: {last_str}")
    lines.append("")
    lines.append("Чтобы удалить: /remove_channel @username")
    await message.answer("\n".join(lines), reply_markup=main_menu())


@router.message(Command("add_channel"))
async def cmd_add_channel(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").replace("/add_channel", "", 1).strip()
    if not raw:
        await state.set_state(AddChannelState.waiting_username)
        await message.answer(
            "Введите username публичного канала (например <code>@durov</code>):",
            reply_markup=cancel_menu(),
        )
        return
    await _do_add_channel(message, state, raw)


@router.message(Command("remove_channel"))
async def cmd_remove_channel(message: Message) -> None:
    raw = (message.text or "").replace("/remove_channel", "", 1).strip()
    if not raw:
        await message.answer(
            "Использование: <code>/remove_channel @username</code>",
            reply_markup=main_menu(),
        )
        return

    username = normalize_username(raw)
    removed = await remove_user_channel(message.from_user.id, username)
    if removed:
        await message.answer(f"Канал <code>@{username}</code> удалён из ваших.", reply_markup=main_menu())
    else:
        await message.answer(f"Канал <code>@{username}</code> не найден в ваших.", reply_markup=main_menu())


@router.message(F.text == "➕ Добавить канал")
async def btn_add_channel(message: Message, state: FSMContext) -> None:
    await state.set_state(AddChannelState.waiting_username)
    await message.answer(
        "Введите username публичного канала (например <code>@durov</code>):",
        reply_markup=cancel_menu(),
    )


@router.message(F.text == "📺 Мои каналы")
async def btn_channels(message: Message) -> None:
    await cmd_channels(message)


@router.message(AddChannelState.waiting_username)
async def process_add_channel(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Введите username")
        return
    await _do_add_channel(message, state, raw)


async def _do_add_channel(message: Message, state: FSMContext, raw: str) -> None:
    await state.clear()
    username = normalize_username(raw)
    if not username:
        await message.answer("Некорректный username", reply_markup=main_menu())
        return

    client = get_client()
    if client is None:
        await message.answer(
            "Telethon не настроен. Заполните API_ID/API_HASH в .env и выполните "
            "<code>python -m src.index_channel</code> один раз для логина.",
            reply_markup=main_menu(),
        )
        return

    try:
        await resolve_channel(client, username)
    except Exception as exc:
        logger.warning("resolve_channel(%s) failed: %s", username, exc)
        await message.answer(
            f"Не удалось открыть канал <code>@{html.escape(username)}</code>: "
            f"{html.escape(str(exc))[:200]}\n\nПроверьте, что канал публичный и username верный.",
            reply_markup=main_menu(),
        )
        return

    await add_user_channel(message.from_user.id, username)
    await message.answer(
        f"Канал <code>@{html.escape(username)}</code> добавлен. Запускаю индексацию…",
        reply_markup=main_menu(),
    )

    asyncio.create_task(_index_in_background(message, username))


async def _index_in_background(message: Message, channel_username: str) -> None:
    client = get_client()
    if client is None:
        return

    lock = get_lock()
    if lock.locked():
        await message.answer(
            f"⏳ Индексация <code>@{channel_username}</code> поставлена в очередь "
            f"(сейчас уже идёт другая).",
        )

    async with lock:
        try:
            result = await index_channel(client, channel_username, MEDIA_DIR, INDEX_LIMIT)
            await message.answer(
                f"✅ Канал <code>@{channel_username}</code> проиндексирован.\n"
                f"Добавлено фото: <b>{result['added']}</b>, пропущено: {result['skipped']}.",
                reply_markup=main_menu(),
            )
        except Exception as exc:
            logger.exception("index_channel(%s) failed", channel_username)
            await message.answer(
                f"❌ Ошибка индексации <code>@{channel_username}</code>: "
                f"{html.escape(str(exc))[:200]}",
                reply_markup=main_menu(),
            )


# ---------- Поиск ----------

def _result_link(channel: str, message_id: int) -> str:
    if not channel:
        return ""
    return f"https://t.me/{channel}/{message_id}"


def _format_caption(item: dict, idx: int, total: int) -> str:
    score = float(item.get("score") or 0.0)
    percent = max(0.0, min(100.0, score * 100.0))
    caption = item.get("caption") or "—"
    date = item.get("date")
    date_str = str(date)[:19] if date else "—"
    channel = item.get("channel", "")
    link = _result_link(channel, int(item.get("message_id") or 0))

    parts = [
        f"<b>Результат {idx} / {total}</b>",
        f"Канал: <code>@{html.escape(channel)}</code>",
        f"Релевантность: <b>{percent:.1f}%</b>",
        f"Дата: <code>{html.escape(date_str)}</code>",
        f"Подпись: {html.escape(caption[:300])}",
    ]
    if link:
        parts.append(f'<a href="{link}">Открыть в канале</a>')
    return "\n".join(parts)


def _pagination_kb(idx: int, total: int) -> Optional[InlineKeyboardMarkup]:
    if total <= 1:
        return None
    buttons: list[InlineKeyboardButton] = []
    if idx > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"pg:{idx - 1}"))
    buttons.append(InlineKeyboardButton(text=f"{idx}/{total}", callback_data="pg:noop"))
    if idx < total:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"pg:{idx + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext) -> None:
    """Формат:
      /search                          — выбор канала, потом ввод запроса
      /search текст                    — поиск по всем своим каналам
      /search @channel текст           — поиск в одном канале
    """
    raw = (message.text or "").replace("/search", "", 1).strip()
    if not raw:
        await _ask_channel_for_search(message, state)
        return

    parts = raw.split(maxsplit=1)
    if parts and parts[0].startswith("@") and len(parts) > 1:
        channel = normalize_username(parts[0])
        query = parts[1].strip()
        await _do_search(message, state, query, channel=channel)
        return

    await _do_search(message, state, raw, channel=None)


@router.message(F.text == "🔎 Поиск")
async def btn_search(message: Message, state: FSMContext) -> None:
    await _ask_channel_for_search(message, state)


async def _ask_channel_for_search(message: Message, state: FSMContext) -> None:
    """Показывает inline-клавиатуру выбора канала (или сразу спрашивает запрос)."""
    user_channels = await list_user_channels(message.from_user.id)

    if not user_channels:
        await message.answer(
            "У вас нет добавленных каналов. Сначала «➕ Добавить канал».",
            reply_markup=main_menu(),
        )
        return

    if len(user_channels) == 1:
        only_channel = user_channels[0]["channel"]
        await state.set_state(SearchState.waiting_query)
        await state.update_data(search_channel=only_channel)
        await message.answer(
            f"Канал: <code>@{html.escape(only_channel)}</code>.\nВведите запрос:",
            reply_markup=cancel_menu(),
        )
        return

    rows = []
    for r in user_channels:
        ch = r["channel"]
        rows.append([InlineKeyboardButton(text=f"@{ch}", callback_data=f"sch:{ch}")])
    rows.append([InlineKeyboardButton(text="🌐 По всем каналам", callback_data="sch:*")])

    await message.answer(
        "Выберите, где искать:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("sch:"))
async def cb_search_channel(call: CallbackQuery, state: FSMContext) -> None:
    payload = call.data.split(":", 1)[1]
    channel = None if payload == "*" else payload

    await state.set_state(SearchState.waiting_query)
    await state.update_data(search_channel=channel)

    label = "по всем каналам" if channel is None else f"в <code>@{html.escape(channel)}</code>"
    await call.answer()
    await call.message.answer(f"Поиск {label}.\nВведите запрос:", reply_markup=cancel_menu())


@router.message(F.text == "📊 Статистика")
async def btn_stats(message: Message) -> None:
    await cmd_stats(message)


@router.message(F.text == "ℹ️ Справка")
async def btn_help(message: Message) -> None:
    await cmd_help(message)


@router.message(F.text == "🧾 О проекте")
async def btn_about(message: Message) -> None:
    await cmd_about(message)


@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено", reply_markup=main_menu())


@router.message(SearchState.waiting_query)
async def process_search_query(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите текст")
        return

    data = await state.get_data()
    channel = data.get("search_channel")
    await _do_search(message, state, text, channel=channel)


async def _do_search(
    message: Message,
    state: FSMContext,
    query: str,
    channel: Optional[str] = None,
) -> None:
    user_id = message.from_user.id
    user_channels = await list_user_channels(user_id)
    if not user_channels:
        await state.clear()
        await message.answer(
            "У вас нет добавленных каналов. Сначала «➕ Добавить канал».",
            reply_markup=main_menu(),
        )
        return

    if channel is not None:
        if channel not in {r["channel"] for r in user_channels}:
            await state.clear()
            await message.answer(
                f"Канал <code>@{html.escape(channel)}</code> не в ваших. "
                f"Сначала добавьте его.",
                reply_markup=main_menu(),
            )
            return

    where = (
        f"в <code>@{html.escape(channel)}</code>" if channel else "по всем вашим каналам"
    )
    await message.answer(
        f"Ищу: <i>{html.escape(query)}</i> {where}…", reply_markup=main_menu()
    )

    try:
        results = await search_images(
            query, limit=SEARCH_LIMIT, user_id=user_id, channel=channel
        )
    except Exception as exc:
        logger.exception("search_images")
        await state.clear()
        await message.answer(f"Ошибка поиска: {exc}", reply_markup=main_menu())
        return

    if not results:
        await state.clear()
        await message.answer("Ничего не найдено 🤷", reply_markup=main_menu())
        return

    await state.set_state(None)
    await state.update_data(results=results, query=query, search_channel=channel)
    await _send_result(message, results, idx=1)


async def _send_result(message: Message, results: list[dict], idx: int) -> None:
    total = len(results)
    item = results[idx - 1]
    caption = _format_caption(item, idx, total)
    kb = _pagination_kb(idx, total)

    file_path = item.get("file_path")
    if file_path and Path(file_path).exists():
        await message.answer_photo(FSInputFile(file_path), caption=caption, reply_markup=kb)
    else:
        await message.answer(caption, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("pg:"))
async def cb_paginate(call: CallbackQuery, state: FSMContext) -> None:
    payload = call.data.split(":", 1)[1]
    if payload == "noop":
        await call.answer()
        return

    try:
        idx = int(payload)
    except ValueError:
        await call.answer("Некорректная страница")
        return

    data = await state.get_data()
    results = data.get("results") or []
    if not results or idx < 1 or idx > len(results):
        await call.answer("Результаты устарели — выполните поиск заново", show_alert=True)
        return

    await call.answer()
    await _send_result(call.message, results, idx)


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Используйте кнопки или команды (/help) 🙂", reply_markup=main_menu())
