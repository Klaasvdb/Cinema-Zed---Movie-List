"""One-time interactive Trakt authorization via the OAuth device flow."""

import logging

from .config import Config
from .trakt_client import TraktClient


def _show_prompt(info):
    print("\n" + "=" * 60)
    print("  Trakt authorization")
    print("=" * 60)
    print(f"  1. Open this URL:  {info['verification_url']}")
    print(f"  2. Enter the code:  {info['user_code']}")
    print("=" * 60)
    print("Waiting for you to approve the app in your browser...\n")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = Config()
    config.validate()

    trakt = TraktClient(
        config.trakt_client_id, config.trakt_client_secret, config.token_path
    )
    if trakt.authorized:
        print(
            f"Already authorized (tokens at {config.token_path}).\n"
            "Delete that file if you want to re-authorize."
        )
        return

    trakt.device_authorize(prompt_callback=_show_prompt)
    print(f"\nAuthorized! Tokens stored at {config.token_path}")


if __name__ == "__main__":
    main()
