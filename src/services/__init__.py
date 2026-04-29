from .ruclip_service import encode_text, encode_image, cosine_similarity
from .telethon_client import (
    init_client,
    close_client,
    get_client,
    get_lock,
    MEDIA_DIR,
)

# indexer_service здесь не реэкспортируем — он сам импортирует database,
# а database импортирует encode_text/encode_image отсюда (circular import).
# Используйте `from src.services.indexer_service import index_channel`.

__all__ = [
    "encode_text",
    "encode_image",
    "cosine_similarity",
    "init_client",
    "close_client",
    "get_client",
    "get_lock",
    "MEDIA_DIR",
]
