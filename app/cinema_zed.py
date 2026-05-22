"""Scraper for the Cinema Zed film programme (https://www.cinemazed.be)."""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("cinema-zed")

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_FILM_HREF_RE = re.compile(r"/film/(?!program\b)[\w%-]+", re.IGNORECASE)


@dataclass(frozen=True)
class Film:
    title: str
    year: Optional[int] = None
    url: Optional[str] = None


def _session(user_agent):
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def _iter_jsonld(soup):
    """Yield every dict found inside the page's JSON-LD <script> blocks."""
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                for value in node.values():
                    if isinstance(value, (list, dict)):
                        stack.append(value)


def _extract_year(movie):
    for key in ("datePublished", "dateCreated", "releaseDate", "copyrightYear"):
        value = movie.get(key)
        if value:
            match = _YEAR_RE.search(str(value))
            if match:
                return int(match.group(0))
    return None


def _films_from_jsonld(soup):
    films = {}
    for node in _iter_jsonld(soup):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        types = {str(t).lower() for t in types if t}

        movie = None
        if "movie" in types:
            movie = node
        elif "screeningevent" in types:
            presented = node.get("workPresented")
            if isinstance(presented, dict):
                movie = presented

        if not movie:
            continue
        name = (movie.get("name") or "").strip()
        if not name:
            continue
        url = movie.get("url") or node.get("url")
        films.setdefault(
            name.lower(), Film(title=name, year=_extract_year(movie), url=url)
        )
    return list(films.values())


def _films_from_links(soup, base_url):
    films = {}
    for anchor in soup.find_all("a", href=True):
        if not _FILM_HREF_RE.search(anchor["href"]):
            continue
        title = anchor.get_text(strip=True) or (anchor.get("title") or "").strip()
        if not title:
            image = anchor.find("img")
            if image:
                title = (image.get("alt") or "").strip()
        if not title or len(title) < 2:
            continue
        url = requests.compat.urljoin(base_url, anchor["href"])
        films.setdefault(title.lower(), Film(title=title, url=url))
    return list(films.values())


def _enrich_year(session, film):
    """Best-effort: fetch a film's detail page to discover its release year."""
    if film.year or not film.url:
        return film
    try:
        response = session.get(film.url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for candidate in _films_from_jsonld(soup):
            if candidate.year:
                return Film(title=film.title, year=candidate.year, url=film.url)
    except requests.RequestException as exc:
        log.debug("Could not fetch detail page %s: %s", film.url, exc)
    time.sleep(0.3)
    return film


def scrape_films(config):
    """Return the list of films currently on the Cinema Zed programme."""
    session = _session(config.user_agent)
    log.info("Fetching Cinema Zed programme: %s", config.program_url)
    response = session.get(config.program_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    films = _films_from_jsonld(soup)
    source = "JSON-LD"
    if not films:
        films = _films_from_links(soup, config.program_url)
        source = "HTML links"
    log.info("Found %d film(s) via %s", len(films), source)

    if config.fetch_details:
        films = [_enrich_year(session, film) for film in films]
    return films


if __name__ == "__main__":
    # Debug helper: `python -m app.cinema_zed` prints the scraped programme.
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    from .config import Config

    for film in scrape_films(Config()):
        year = f" ({film.year})" if film.year else ""
        print(f"- {film.title}{year}")
