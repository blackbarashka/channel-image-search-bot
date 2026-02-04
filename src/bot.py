"""Сборка и запуск бота."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import BotConfig
from src.handlers import commands_router

from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_bot(config: BotConfig) -> tuple[Bot, Dispatcher]:
    """Создаёт экземпляры Bot и Dispatcher, подключает роутеры."""
    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(commands_router)
    return bot, dp


async def main() -> None:
    config = BotConfig.from_env()
    bot, dp = create_bot(config)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота / показать меню"),
            BotCommand(command="search", description="Поиск изображений по описанию"),
            BotCommand(command="stats", description="Статистика и состояние индекса"),
            BotCommand(command="help", description="Справка по использованию"),
            BotCommand(command="demo", description="Тестовое изображение"),
            BotCommand(command="about", description="О проекте и текущей версии"),
        ]
    )

    # Удаляем вебхук, если был (для long polling)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен (long polling)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
