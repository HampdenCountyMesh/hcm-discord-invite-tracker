from __future__ import annotations

import asyncio
import logging
import sys

from .bot import InviteTrackerBot
from .catalog import SourceCatalog
from .config import ConfigError, load_settings
from .dashboard import Dashboard
from .database import Database


async def run() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    catalog = SourceCatalog.load(settings.source_config_path)
    db = Database(settings.database_path)
    db.seed_sources(catalog)
    db.ensure_special_source("member-invite", "Member-created invite")
    bot = InviteTrackerBot(settings, db, catalog)
    dashboard = Dashboard(db, settings, catalog.project_name)

    try:
        if settings.dashboard_enabled:
            await dashboard.start()
            logging.getLogger(__name__).info(
                "Dashboard listening on %s:%s",
                settings.dashboard_host,
                settings.dashboard_port,
            )
        await bot.start(settings.discord_token)
    finally:
        await dashboard.stop()
        if not bot.is_closed():
            await bot.close()
        db.close()


def main() -> None:
    try:
        asyncio.run(run())
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
