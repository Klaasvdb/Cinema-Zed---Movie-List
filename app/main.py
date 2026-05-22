"""Entry point: authorize with Trakt if needed, sync on startup, then daily."""

import logging
import time

import schedule

from .config import Config
from .sync import run_sync
from .trakt_client import TraktClient

log = logging.getLogger("main")


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _log_authorization_prompt(info):
    minutes = max(1, info.get("expires_in", 600) // 60)
    border = "=" * 60
    for line in (
        border,
        "ACTION NEEDED - link this app to your Trakt account:",
        f"  1. Open:        {info['verification_url']}",
        f"  2. Enter code:  {info['user_code']}",
        f"Waiting for approval (this code is valid for ~{minutes} min)...",
        border,
    ):
        log.warning(line)


def _ensure_authorized(trakt):
    if trakt.authorized:
        return
    log.info("Not linked to Trakt yet; starting authorization.")
    while not trakt.authorized:
        try:
            trakt.device_authorize(prompt_callback=_log_authorization_prompt)
            log.info("Trakt authorization complete.")
        except Exception as exc:  # noqa: BLE001 - keep retrying with a fresh code
            log.warning("Authorization not completed (%s); requesting a new code.", exc)
            time.sleep(5)


def _safe_sync(config, trakt):
    try:
        run_sync(config, trakt)
    except Exception:  # noqa: BLE001 - keep the daily loop alive
        log.exception("Sync run failed")


def main():
    _setup_logging()
    config = Config()
    config.validate()

    trakt = TraktClient(
        config.trakt_client_id, config.trakt_client_secret, config.token_path
    )
    _ensure_authorized(trakt)

    log.info("Running initial sync on startup")
    _safe_sync(config, trakt)

    if config.run_once:
        log.info("RUN_ONCE is set; exiting after a single run.")
        return

    schedule.every().day.at(config.run_at).do(_safe_sync, config, trakt)
    log.info("Scheduled daily sync at %s. Waiting...", config.run_at)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
