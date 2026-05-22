import os


def _bool(value, default=False):
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Runtime configuration, sourced from environment variables."""

    def __init__(self):
        self.trakt_client_id = os.environ.get("TRAKT_CLIENT_ID", "").strip()
        self.trakt_client_secret = os.environ.get("TRAKT_CLIENT_SECRET", "").strip()
        self.list_name = os.environ.get("TRAKT_LIST_NAME", "Cinema Zed").strip()
        self.list_privacy = os.environ.get("TRAKT_LIST_PRIVACY", "private").strip()
        self.program_url = os.environ.get(
            "CINEMA_ZED_URL", "https://www.cinemazed.be/film/program"
        ).strip()
        self.run_at = os.environ.get("RUN_AT", "08:00").strip()
        self.data_dir = os.environ.get("DATA_DIR", "/data").strip()
        self.user_agent = os.environ.get(
            "HTTP_USER_AGENT",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ).strip()
        self.run_once = _bool(os.environ.get("RUN_ONCE"))
        self.fetch_details = _bool(os.environ.get("FETCH_FILM_DETAILS"), default=True)

    @property
    def token_path(self):
        return os.path.join(self.data_dir, "trakt_tokens.json")

    def validate(self):
        missing = [
            name
            for name, value in (
                ("TRAKT_CLIENT_ID", self.trakt_client_id),
                ("TRAKT_CLIENT_SECRET", self.trakt_client_secret),
            )
            if not value
        ]
        if missing:
            raise SystemExit(
                "Missing required environment variables: " + ", ".join(missing)
            )
