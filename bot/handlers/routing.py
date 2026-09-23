from __future__ import annotations

from aiogram import Router


def attach(parent: Router, *routers: Router) -> None:
    """Подключить роутеры, отвязав их от прежнего родителя.

    Роутеры объявлены на уровне модулей, а приложение может собираться
    несколько раз в одном процессе (тесты, перезапуск polling) — aiogram
    запрещает повторное подключение без отвязки.
    """
    for router in routers:
        old = router.parent_router
        if old is not None:
            if router in old.sub_routers:
                old.sub_routers.remove(router)
            router._parent_router = None  # noqa: SLF001
        parent.include_router(router)
