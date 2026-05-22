"""Minimal Trakt API client with OAuth device-flow support."""

import json
import logging
import os
import time

import requests

log = logging.getLogger("trakt")

API = "https://api.trakt.tv"


class TraktError(RuntimeError):
    pass


class TraktClient:
    def __init__(self, client_id, client_secret, token_path):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = token_path
        self.session = requests.Session()
        self._tokens = self._load_tokens()

    # ------------------------------------------------------------------ tokens
    def _load_tokens(self):
        if os.path.exists(self.token_path):
            with open(self.token_path, encoding="utf-8") as handle:
                return json.load(handle)
        return {}

    def _save_tokens(self, data):
        directory = os.path.dirname(self.token_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.token_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, self.token_path)
        self._tokens = data

    def _store_token_response(self, data):
        data = dict(data)
        # Refresh a minute early to avoid races around expiry.
        data["expires_at"] = time.time() + data.get("expires_in", 0) - 60
        self._save_tokens(data)

    @property
    def authorized(self):
        return bool(self._tokens.get("refresh_token"))

    # -------------------------------------------------------------- device auth
    def device_authorize(self, prompt_callback=None):
        """Run the OAuth device flow; blocks until the user approves."""
        response = self.session.post(
            f"{API}/oauth/device/code",
            json={"client_id": self.client_id},
            timeout=30,
        )
        response.raise_for_status()
        info = response.json()
        if prompt_callback:
            prompt_callback(info)

        interval = info.get("interval", 5)
        deadline = time.time() + info.get("expires_in", 600)
        while time.time() < deadline:
            time.sleep(interval)
            poll = self.session.post(
                f"{API}/oauth/device/token",
                json={
                    "code": info["device_code"],
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=30,
            )
            if poll.status_code == 200:
                self._store_token_response(poll.json())
                return
            if poll.status_code == 400:
                continue  # still pending
            if poll.status_code == 429:
                interval += 1
                continue
            messages = {
                404: "Invalid device code.",
                409: "This code was already used.",
                410: "The code expired; restart authorization.",
                418: "Authorization was denied.",
            }
            raise TraktError(messages.get(poll.status_code, f"HTTP {poll.status_code}"))
        raise TraktError("Authorization timed out before approval.")

    def _refresh(self):
        refresh_token = self._tokens.get("refresh_token")
        if not refresh_token:
            raise TraktError("Not authorized. Run `python -m app.authorize` first.")
        log.info("Refreshing Trakt access token")
        response = self.session.post(
            f"{API}/oauth/token",
            json={
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise TraktError(
                f"Token refresh failed (HTTP {response.status_code}). "
                "Re-run `python -m app.authorize`."
            )
        self._store_token_response(response.json())

    def _access_token(self):
        if not self._tokens.get("access_token"):
            raise TraktError("Not authorized. Run `python -m app.authorize` first.")
        if time.time() >= self._tokens.get("expires_at", 0):
            self._refresh()
        return self._tokens["access_token"]

    # ------------------------------------------------------------------ request
    def _request(self, method, path, *, auth=True, **kwargs):
        url = path if path.startswith("http") else f"{API}{path}"
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id,
        }
        headers.update(kwargs.pop("headers", {}))

        for attempt in range(3):
            if auth:
                headers["Authorization"] = f"Bearer {self._access_token()}"
            response = self.session.request(
                method, url, headers=headers, timeout=30, **kwargs
            )
            if response.status_code == 401 and auth and attempt == 0:
                self._refresh()
                continue
            if response.status_code == 429 and attempt < 2:
                time.sleep(int(response.headers.get("Retry-After", "2")))
                continue
            return response
        return response

    # --------------------------------------------------------------- high-level
    def user_slug(self):
        response = self._request("GET", "/users/settings")
        response.raise_for_status()
        return response.json()["user"]["ids"]["slug"]

    def find_or_create_list(self, slug, name, privacy="private"):
        response = self._request("GET", f"/users/{slug}/lists")
        response.raise_for_status()
        for existing in response.json():
            if existing.get("name", "").lower() == name.lower():
                return existing
        log.info("Creating Trakt list %r", name)
        response = self._request(
            "POST",
            f"/users/{slug}/lists",
            json={
                "name": name,
                "description": "Films currently showing at Cinema Zed. "
                "Updated automatically.",
                "privacy": privacy,
            },
        )
        response.raise_for_status()
        return response.json()

    def list_movie_trakt_ids(self, slug, list_id):
        response = self._request(
            "GET", f"/users/{slug}/lists/{list_id}/items/movies"
        )
        response.raise_for_status()
        ids = set()
        for item in response.json():
            trakt_id = (item.get("movie") or {}).get("ids", {}).get("trakt")
            if trakt_id:
                ids.add(trakt_id)
        return ids

    def search_movie(self, title, year=None):
        response = self._request(
            "GET",
            "/search/movie",
            params={"query": title, "fields": "title", "limit": 5},
        )
        response.raise_for_status()
        results = [r.get("movie") for r in response.json() if r.get("movie")]
        if not results:
            return None
        if year:
            for movie in results:
                if movie.get("year") == year:
                    return movie
        for movie in results:
            if movie.get("title", "").lower() == title.lower():
                return movie
        return results[0]

    def add_movies_to_list(self, slug, list_id, trakt_ids):
        payload = {"movies": [{"ids": {"trakt": tid}} for tid in trakt_ids]}
        response = self._request(
            "POST", f"/users/{slug}/lists/{list_id}/items", json=payload
        )
        response.raise_for_status()
        return response.json()
