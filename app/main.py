"""Entry point: run the sync on startup, then once per day."""

import logging
import time

import schedule

from .config import Config
from .sync import run_sync


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _safe_sync(config):
    try:
        run_sync(config)
    except Exception:  # noqa: BLE001 - keep the daily loop alive
        logging.getLogger("main").exception("Sync run failed")


def main():
    _setup_logging()
    log = logging.getLogger("main")
    config = Config()

    log.info("Running initial sync on startup")
    _safe_sync(config)

    if config.run_once:
        log.info("RUN_ONCE is set; exiting after a single run.")
        return

    schedule.every().day.at(config.run_at).do(_safe_sync, config)
    log.info("Scheduled daily sync at %s. Waiting...", config.run_at)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
