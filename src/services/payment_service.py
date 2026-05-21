"""Сервис платежей через ЮKassa."""

import logging
import uuid
from typing import Optional

import yookassa

logger = logging.getLogger(__name__)

# Константы ЮKassa
YOOKASSA_SHOP_ID = ""
YOOKASSA_API_KEY = ""

SUBSCRIPTION_NAMES = {
    "basic": "Подписка Базовая (5 каналов)",
    "pro": "Подписка Профессиональная (10 каналов)",
    "premium": "Подписка Премиум (15 каналов)",
}

SUBSCRIPTION_PRICES = {
    "basic": "199.00",      # В рублях
    "pro": "399.00",
    "premium": "599.00",
}


def init_yookassa(shop_id: str, api_key: str) -> None:
    """Инициализирует ЮKassa с учетными данными."""
    global YOOKASSA_SHOP_ID, YOOKASSA_API_KEY
    YOOKASSA_SHOP_ID = shop_id
    YOOKASSA_API_KEY = api_key
    yookassa.Configuration.configure(shop_id, api_key)
    logger.info("ЮKassa инициализирована: shop_id=%s", shop_id)


def create_payment(
    user_id: int,
    subscription_tier: str,
    return_url: str,
) -> Optional[dict]:
    """Создает платеж в ЮKassa.
    
    Args:
        user_id: ID пользователя Telegram
        subscription_tier: 'basic', 'pro', или 'premium'
        return_url: URL для возврата после платежа
    
    Returns:
        Словарь с информацией о платеже (id, confirmation_url и т.д.)
    """
    if subscription_tier not in SUBSCRIPTION_PRICES:
        logger.error("Unknown subscription tier: %s", subscription_tier)
        return None
    
    # Генерируем уникальный ID для платежа
    idempotency_key = str(uuid.uuid4())
    
    try:
        payment = yookassa.Payment.create(
            {
                "amount": {
                    "value": SUBSCRIPTION_PRICES[subscription_tier],
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url,
                },
                "capture": True,
                "description": SUBSCRIPTION_NAMES[subscription_tier],
                "metadata": {
                    "user_id": str(user_id),
                    "subscription_tier": subscription_tier,
                },
            },
            idempotency_key,
        )
        
        logger.info(
            "Payment created: payment_id=%s, user_id=%s, tier=%s, amount=%s",
            payment.id, user_id, subscription_tier, SUBSCRIPTION_PRICES[subscription_tier]
        )
        
        return {
            "id": payment.id,
            "status": payment.status,
            "confirmation_url": payment.confirmation.confirmation_url,
            "amount": SUBSCRIPTION_PRICES[subscription_tier],
            "subscription_tier": subscription_tier,
        }
    except Exception as exc:
        logger.exception("Failed to create payment for user_id=%s: %s", user_id, exc)
        return None


def get_payment(payment_id: str) -> Optional[dict]:
    """Получает информацию о платеже из ЮKassa."""
    try:
        payment = yookassa.Payment.find_one(payment_id)
        return {
            "id": payment.id,
            "status": payment.status,
            "amount": str(payment.amount.value),
            "currency": payment.amount.currency,
            "metadata": payment.metadata or {},
        }
    except Exception as exc:
        logger.exception("Failed to get payment %s: %s", payment_id, exc)
        return None
