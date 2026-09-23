from aiogram import Router

from bot.handlers import fallback, menu, support


def user_routers() -> list[Router]:
    """Порядок важен: fallback — всегда последним."""
    return [menu.router, support.router]


def fallback_router() -> Router:
    return fallback.router
