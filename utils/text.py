from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TAG_RE = re.compile(r"<[^>]+>")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def strip_tags(value: str) -> str:
    return html.unescape(TAG_RE.sub("", value))


def truncate(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: max(limit - 1, 0)].rstrip() + "…"


def as_utc(value: datetime) -> datetime:
    # SQLite возвращает naive datetime — считаем, что это UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def fmt_dt(value: datetime | None, tz: ZoneInfo, pattern: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return "—"
    return as_utc(value).astimezone(tz).strftime(pattern)


def fmt_time(value: datetime | None, tz: ZoneInfo) -> str:
    return fmt_dt(value, tz, "%H:%M")


def fmt_number(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", " ")


def is_valid_url(value: str) -> bool:
    value = value.strip()
    if value.startswith("tg://"):
        return len(value) > 5
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_username(value: str) -> str | None:
    value = value.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    value = value.split("?")[0].strip("/")
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", value) else None


def parse_buttons(raw: str) -> list[list[dict[str, str]]]:
    """Разобрать кнопки из текста администратора.

    Формат — одна строка = один ряд, кнопки в ряду через « | »:
        Сайт - https://example.com | Канал - https://t.me/channel
        Поддержка - https://t.me/bot
    Бросает ValueError с понятным текстом при ошибке.
    """
    rows: list[list[dict[str, str]]] = []
    for line_no, line in enumerate(raw.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        row: list[dict[str, str]] = []
        for chunk in line.split("|"):
            chunk = chunk.strip()
            if " - " not in chunk:
                raise ValueError(f"Строка {line_no}: нужен формат «Текст - ссылка»")
            text, url = (part.strip() for part in chunk.rsplit(" - ", 1))
            if not text or len(text) > 64:
                raise ValueError(f"Строка {line_no}: текст кнопки 1–64 символа")
            if not is_valid_url(url):
                raise ValueError(f"Строка {line_no}: некорректная ссылка «{url}»")
            row.append({"text": text, "url": url})
        if len(row) > 4:
            raise ValueError(f"Строка {line_no}: не больше 4 кнопок в ряду")
        rows.append(row)
    if not rows:
        raise ValueError("Не найдено ни одной кнопки")
    if len(rows) > 10:
        raise ValueError("Не больше 10 рядов кнопок")
    return rows


def progress_bar(value: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "▱" * width
    filled = round(width * min(value, total) / total)
    return "▰" * filled + "▱" * (width - filled)
