"""Сборка и запуск бота."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from src.config import BotConfig, YookassaConfig
from src.database import close_pool, init_pool
from src.handlers import commands_router
from src.services import close_client, init_client
from src.services.payment_service import init_yookassa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_bot(config: BotConfig) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(commands_router)
    return bot, dp


async def main() -> None:
    config = BotConfig.from_env()
    await init_pool(config.database_url)
    await init_client()
    
    # Инициализируем ЮKassa для платежей
    yookassa_config = YookassaConfig.from_env()
    if yookassa_config.shop_id and yookassa_config.api_key:
        init_yookassa(yookassa_config.shop_id, yookassa_config.api_key)
        logger.info("ЮKassa инициализирована для платежей")
    else:
        logger.warning("Платежи ЮKassa не настроены. Заполните YOOKASSA_SHOP_ID и YOOKASSA_API_KEY в .env")

    bot, dp = create_bot(config)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота / показать меню"),
            BotCommand(command="add_channel", description="Добавить канал"),
            BotCommand(command="channels", description="Мои каналы"),
            BotCommand(command="remove_channel", description="Удалить канал"),
            BotCommand(command="search", description="Поиск изображений по описанию"),
            BotCommand(command="subscribe", description="Подписки и платежи"),
            BotCommand(command="stats", description="Статистика индекса"),
            BotCommand(command="help", description="Справка"),
            BotCommand(command="about", description="О проекте"),
        ]
    )

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен (long polling)")

    try:
        await dp.start_polling(bot)
    finally:
        await close_client()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
