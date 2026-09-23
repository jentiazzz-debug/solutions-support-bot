"""Статистика и график по дням (PNG через Pillow)."""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from database.models import TicketStatus, utcnow
from database.repositories import Repo
from utils.text import as_utc


@dataclass(slots=True)
class Stats:
    users_total: int
    users_today: int
    users_week: int
    users_month: int
    active_day: int
    active_week: int
    blocked_bot: int
    banned: int
    tickets_total: int
    tickets_open: int
    tickets_in_progress: int
    tickets_closed: int
    tickets_banned: int
    messages_total: int
    by_category: list[tuple[str, int]]


def _start_of_day(tz: ZoneInfo, days_ago: int = 0) -> datetime:
    today = datetime.now(tz).date() - timedelta(days=days_ago)
    # В UTC: так сравнение корректно и в PostgreSQL, и в SQLite (хранит время без зоны).
    return datetime.combine(today, time.min, tzinfo=tz).astimezone(timezone.utc)


async def collect(repo: Repo, tz: ZoneInfo) -> Stats:
    now = utcnow()
    by_status = await repo.tickets.count_by_status()
    return Stats(
        users_total=await repo.users.count(),
        users_today=await repo.users.count_created_since(_start_of_day(tz)),
        users_week=await repo.users.count_created_since(_start_of_day(tz, 6)),
        users_month=await repo.users.count_created_since(_start_of_day(tz, 29)),
        active_day=await repo.users.count_active_since(now - timedelta(days=1)),
        active_week=await repo.users.count_active_since(now - timedelta(days=7)),
        blocked_bot=await repo.users.count_blocked_bot(),
        banned=await repo.bans.count(),
        tickets_total=sum(by_status.values()),
        tickets_open=by_status.get(TicketStatus.OPEN.value, 0),
        tickets_in_progress=by_status.get(TicketStatus.IN_PROGRESS.value, 0),
        tickets_closed=by_status.get(TicketStatus.CLOSED.value, 0),
        tickets_banned=by_status.get(TicketStatus.BANNED.value, 0),
        messages_total=await repo.tickets.count_messages(),
        by_category=(await repo.tickets.count_by_category())[:6],
    )


def per_day(values: Sequence[datetime], tz: ZoneInfo, days: int) -> list[tuple[date, int]]:
    counter = Counter(as_utc(v).astimezone(tz).date() for v in values)
    today = datetime.now(tz).date()
    return [(today - timedelta(days=i), counter.get(today - timedelta(days=i), 0)) for i in range(days - 1, -1, -1)]


async def series(repo: Repo, tz: ZoneInfo, days: int) -> tuple[list[tuple[date, int]], list[tuple[date, int]]]:
    since = _start_of_day(tz, days - 1)
    users = per_day(await repo.users.created_dates_since(since), tz, days)
    tickets = per_day(await repo.tickets.created_dates_since(since), tz, days)
    return users, tickets


def _font(image_font, candidates: tuple[str, ...], size: int):
    """Шрифт с кириллицей: в Docker — DejaVu (fonts-dejavu-core), на Windows — Arial."""
    for name in candidates:
        try:
            return image_font.truetype(name, size)
        except OSError:
            continue
    return image_font.load_default(size=size)


def render_chart(users: list[tuple[date, int]], tickets: list[tuple[date, int]], title: str) -> bytes:
    """Две серии столбиков: новые пользователи и новые тикеты по дням."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1200, 640
    pad_left, pad_right, pad_top, pad_bottom = 70, 30, 90, 80
    bg, grid, text_color = (16, 18, 22), (44, 48, 56), (225, 229, 235)
    c_users, c_tickets = (77, 144, 254), (52, 199, 120)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    font = _font(ImageFont, ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"), 18)
    font_big = _font(
        ImageFont, ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"), 26
    )

    draw.text((pad_left, 24), title, fill=text_color, font=font_big)
    legend_x = width - pad_right - 420
    draw.rectangle((legend_x, 34, legend_x + 16, 50), fill=c_users)
    draw.text((legend_x + 24, 30), "Новые пользователи", fill=text_color, font=font)
    draw.rectangle((legend_x + 230, 34, legend_x + 246, 50), fill=c_tickets)
    draw.text((legend_x + 254, 30), "Тикеты", fill=text_color, font=font)

    peak = max([v for _, v in users] + [v for _, v in tickets] + [1])
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom
    for i in range(5):
        y = pad_top + chart_h - chart_h * i / 4
        draw.line((pad_left, y, width - pad_right, y), fill=grid, width=1)
        draw.text((10, y - 10), str(round(peak * i / 4)), fill=text_color, font=font)

    n = len(users)
    slot = chart_w / max(n, 1)
    bar = max(slot * 0.36, 2)
    for i, ((day, u), (_, t)) in enumerate(zip(users, tickets)):
        x = pad_left + slot * i + slot * 0.12
        for j, (value, color) in enumerate(((u, c_users), (t, c_tickets))):
            if not value:
                continue
            h = chart_h * value / peak
            x0 = x + j * bar
            draw.rectangle((x0, pad_top + chart_h - h, x0 + bar - 1, pad_top + chart_h), fill=color)
        if n <= 14 or i % max(n // 10, 1) == 0 or i == n - 1:
            draw.text((x - 4, pad_top + chart_h + 10), day.strftime("%d.%m"), fill=text_color, font=font)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
