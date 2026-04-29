"""ruCLIP-сервис: эмбеддинги текста и изображений в одном векторном пространстве (512 dim).

Использует пакет ruclip (ai-forever/ru-clip):
  pip install ruclip==0.0.2
"""

import logging
import os

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("RUCLIP_MODEL", "ruclip-vit-base-patch32-224")

_predictor = None
_device = None


def _get_predictor():
    """Ленивая инициализация ruCLIP Predictor (один раз на процесс)."""
    global _predictor, _device

    if _predictor is not None:
        return _predictor

    import torch
    import ruclip

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Загрузка ruCLIP %s на %s...", DEFAULT_MODEL, _device)

    clip, processor = ruclip.load(DEFAULT_MODEL, device=_device)
    _predictor = ruclip.Predictor(clip, processor, _device, bs=8, quiet=True)
    logger.info("ruCLIP загружен (dim=512).")

    return _predictor


def encode_text(text: str) -> np.ndarray:
    """Текст -> нормализованный вектор float32 (512,)."""
    import torch

    predictor = _get_predictor()
    with torch.no_grad():
        latents = predictor.get_text_latents([text])
    return latents[0].cpu().float().numpy().astype(np.float32)


def encode_image(image_path: str) -> np.ndarray:
    """Картинка (путь или PIL.Image) -> нормализованный вектор float32 (512,)."""
    import torch

    predictor = _get_predictor()
    img = Image.open(image_path).convert("RGB")
    with torch.no_grad():
        latents = predictor.get_image_latents([img])
    return latents[0].cpu().float().numpy().astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Косинусное сходство (векторы уже нормализованы -> скалярное произведение)."""
    return float(np.dot(a, b))
