"""Блокировки на пользователя.

Апдейты обрабатываются параллельно; альбом из 5 фото приходит пятью
сообщениями почти одновременно. Без блокировки из одного альбома
создалось бы пять тикетов.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def user_lock(user_id: int) -> AsyncIterator[None]:
    lock = _locks[user_id]
    async with lock:
        yield
    if not lock.locked() and len(_locks) > 5000:
        _locks.pop(user_id, None)
