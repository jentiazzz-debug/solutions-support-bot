"""Все эмодзи интерфейса — в одном месте.

Каждый значок — пара: обычный эмодзи (виден всегда, в том числе тем, у
кого нет Premium) и id кастомного эмодзи из набора проекта
t.me/addemoji/solutions_project_by_Solutmark_bot.

ID берутся из assets/premium_emoji.json — это выгрузка реального набора,
а не выдуманные числа. Чтобы заменить значок, поменяйте имя в PACK_NAME
или пропишите id напрямую.

Если Telegram не пустит кастомные эмодзи (у бота нет купленного на
Fragment юзернейма), bot/services/premium.py сам снимет разметку и
отправит обычные эмодзи — сообщение не потеряется.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from config.settings import BASE_DIR

PACK_FILE = BASE_DIR / "assets" / "premium_emoji.json"


@lru_cache
def _pack() -> dict[str, str]:
    try:
        return json.loads(PACK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@dataclass(frozen=True, slots=True)
class Emoji:
    fallback: str
    pack_name: str | None = None

    @property
    def custom_id(self) -> str | None:
        if not self.pack_name:
            return None
        return _pack().get(self.pack_name)

    @property
    def html(self) -> str:
        """Разметка для parse_mode=HTML."""
        if self.custom_id:
            return f'<tg-emoji emoji-id="{self.custom_id}">{self.fallback}</tg-emoji>'
        return self.fallback

    def __str__(self) -> str:
        return self.html


# --- Главное меню ---
ABOUT_EMOJI = Emoji("ℹ️", "info")
SUPPORT_EMOJI = Emoji("🎧", "headphones")
PORTFOLIO_EMOJI = Emoji("💼", "briefcase")
ADS_EMOJI = Emoji("📢", "ads")
PROJECTS_EMOJI = Emoji("📂", "folder")
HOME_EMOJI = Emoji("🏠", "home")
BACK_EMOJI = Emoji("⬅️", "back")

# --- Поддержка ---
TICKET_EMOJI = Emoji("🎫", "hashtag")
NEW_TICKET_EMOJI = Emoji("➕", "plus")
MY_TICKETS_EMOJI = Emoji("📋", "list")
CATEGORY_EMOJI = Emoji("📁", "folder")
MESSAGE_EMOJI = Emoji("💬", "chat")
REPLY_EMOJI = Emoji("✍️", "edit")
SEND_EMOJI = Emoji("📨", "send")
CLOSE_EMOJI = Emoji("✅", "check")
BELL_EMOJI = Emoji("🔔", "bell")
USER_EMOJI = Emoji("👤", "user")
TIME_EMOJI = Emoji("🕐", "clock")
LINK_EMOJI = Emoji("🔗", "link")
WARNING_EMOJI = Emoji("⚠️", "warning")
BAN_EMOJI = Emoji("🚫", "ban")
UNLOCK_EMOJI = Emoji("🔓", "unlock")
QUICK_EMOJI = Emoji("⚡", "bolt")
HISTORY_EMOJI = Emoji("📜", "history")
PROGRESS_EMOJI = Emoji("⏳", "pending")

# --- Админка ---
ADMIN_EMOJI = Emoji("👑", "crown")
STATS_EMOJI = Emoji("📊", "bar_chart")
BROADCAST_EMOJI = Emoji("📢", "megaphone")
SETTINGS_EMOJI = Emoji("⚙️", "gear")
MENU_EMOJI = Emoji("🧩", "menu")
ACCOUNT_EMOJI = Emoji("📱", "phone")
USERS_EMOJI = Emoji("👥", "users")
TRASH_EMOJI = Emoji("🗑", "trash")
EDIT_EMOJI = Emoji("✏️", "edit")
PLUS_EMOJI = Emoji("➕", "plus")
EYE_EMOJI = Emoji("👁", "eye")
EYE_OFF_EMOJI = Emoji("🙈", "eye_off")
UP_EMOJI = Emoji("⬆️", "arrow_up")
DOWN_EMOJI = Emoji("⬇️", "arrow_down")
SEARCH_EMOJI = Emoji("🔍", "search")
ROCKET_EMOJI = Emoji("🚀", "rocket")
STAR_EMOJI = Emoji("⭐", "star")
BOT_EMOJI = Emoji("🤖", "bot")
GLOBE_EMOJI = Emoji("🌐", "globe")
CHANNEL_EMOJI = Emoji("📣", "announce")
SHIELD_EMOJI = Emoji("🛡", "shield")
CROSS_EMOJI = Emoji("✖️", "cross")
SOLUTIONS_EMOJI = Emoji("🔷", "solutions")
