"""HTTP healthcheck для Docker: GET /health → 200, если БД доступна и polling жив."""

from __future__ import annotations

import logging
import time

from aiohttp import web

from database.database import Database

log = logging.getLogger(__name__)


class HealthState:
    def __init__(self) -> None:
        self.started = time.time()
        self.polling = False
        self.last_update = 0.0

    def touch(self) -> None:
        self.last_update = time.time()


async def start_health_server(db: Database, state: HealthState, host: str, port: int) -> web.AppRunner | None:
    async def health(_: web.Request) -> web.Response:
        db_ok = await db.ping()
        ok = db_ok and state.polling
        body = {
            "status": "ok" if ok else "fail",
            "db": db_ok,
            "polling": state.polling,
            "uptime": int(time.time() - state.started),
            "last_update_ago": int(time.time() - state.last_update) if state.last_update else None,
        }
        return web.json_response(body, status=200 if ok else 503)

    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app, access_log=None)
    try:
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
        log.info("Healthcheck: http://%s:%s/health", host, port)
        return runner
    except OSError as error:
        log.warning("Healthcheck-сервер не запущен: %s", error)
        await runner.cleanup()
        return None
