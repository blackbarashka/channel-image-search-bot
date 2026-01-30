#!/usr/bin/env python3
"""Точка входа: запуск бота."""

from src.bot import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
