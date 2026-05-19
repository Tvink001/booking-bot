"""Entry point. Two modes gated by `settings.mode`:

- polling: local dev, `dp.start_polling(bot)` after dropping any stale webhook.
- webhook: production on Railway, aiohttp web app with /telegram/webhook and
  /health, set_webhook called from on_startup with the secret token.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import settings
from bot.handlers.admin import admin_router
from bot.handlers.booking import booking_router
from bot.handlers.my_bookings import my_bookings_router
from bot.handlers.start import start_router
from bot.services.calendar import CalendarService
from bot.services.scheduler import scheduler
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/telegram/webhook"


def _build_bot() -> Bot:
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Workflow-data DI: handlers that declare `sheets: SheetsService` or
    # `calendar: CalendarService` parameters receive these singletons.
    dp["sheets"] = SheetsService()
    dp["calendar"] = CalendarService()
    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(my_bookings_router)
    dp.include_router(admin_router)
    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)
    return dp


async def _on_startup(bot: Bot) -> None:
    await scheduler.__aenter__()
    await scheduler.start_in_background()
    logger.info("APScheduler started; data store at %s", settings.scheduler_db_path)

    if settings.mode == "webhook":
        url = settings.webhook_base_url.rstrip("/") + WEBHOOK_PATH
        await bot.set_webhook(
            url=url,
            secret_token=settings.webhook_secret.get_secret_value(),
            drop_pending_updates=True,
        )
        logger.info("Webhook registered: %s", url)


async def _on_shutdown(bot: Bot) -> None:
    try:
        await scheduler.stop()
        await scheduler.__aexit__(None, None, None)
        logger.info("APScheduler stopped")
    except Exception:
        logger.exception("APScheduler shutdown failed")


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _run_polling() -> None:
    bot = _build_bot()
    dp = _build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def _run_webhook() -> None:
    bot = _build_bot()
    dp = _build_dispatcher()
    app = web.Application()
    app.router.add_get("/health", _health)
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret.get_secret_value(),
    ).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host=settings.web_host, port=settings.web_port)


def main() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if settings.mode == "polling":
        asyncio.run(_run_polling())
    else:
        _run_webhook()


if __name__ == "__main__":
    main()
