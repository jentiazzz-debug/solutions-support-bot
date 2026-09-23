from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import BASE_DIR

FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO", log_dir: str | None = "logs") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(FORMAT)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_dir:
        path = Path(log_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        try:
            path.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                path / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            root.warning("Не удалось создать файл логов в %s — пишу только в stdout", path)

    for noisy in ("aiogram.event", "telethon", "sqlalchemy.engine", "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
