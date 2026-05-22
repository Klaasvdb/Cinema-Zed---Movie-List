"""Orchestrates a single sync: scrape Cinema Zed, then update the Trakt list."""

import logging

from .cinema_zed import scrape_films
from .trakt_client import TraktClient, TraktError

log = logging.getLogger("sync")


def run_sync(config):
    config.validate()
    trakt = TraktClient(
        config.trakt_client_id, config.trakt_client_secret, config.token_path
    )
    if not trakt.authorized:
        raise TraktError(
            "No Trakt tokens found. Run the one-time authorization first:\n"
            "  docker compose run --rm cinema-zed-trakt python -m app.authorize"
        )

    films = scrape_films(config)
    if not films:
        log.warning("No films scraped from Cinema Zed; nothing to do.")
        return

    slug = trakt.user_slug()
    trakt_list = trakt.find_or_create_list(
        slug, config.list_name, config.list_privacy
    )
    list_id = trakt_list["ids"]["trakt"]
    existing_ids = trakt.list_movie_trakt_ids(slug, list_id)
    log.info("List %r currently holds %d movie(s)", config.list_name, len(existing_ids))

    to_add = []
    queued_ids = set()
    unmatched = []
    for film in films:
        match = trakt.search_movie(film.title, film.year)
        if not match:
            unmatched.append(film.title)
            continue
        trakt_id = match["ids"]["trakt"]
        if trakt_id in existing_ids or trakt_id in queued_ids:
            continue
        queued_ids.add(trakt_id)
        to_add.append(match)

    if to_add:
        result = trakt.add_movies_to_list(
            slug, list_id, [movie["ids"]["trakt"] for movie in to_add]
        )
        added = result.get("added", {}).get("movies", len(to_add))
        log.info("Added %d new movie(s) to %r:", added, config.list_name)
        for movie in to_add:
            log.info("  + %s (%s)", movie.get("title"), movie.get("year") or "?")
    else:
        log.info("No new movies to add; list already up to date.")

    if unmatched:
        log.warning(
            "Could not match %d title(s) on Trakt: %s",
            len(unmatched),
            ", ".join(unmatched),
        )
