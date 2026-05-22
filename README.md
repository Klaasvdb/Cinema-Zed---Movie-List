# Cinema Zed → Trakt

A small Dockerised service that checks the [Cinema Zed](https://www.cinemazed.be)
film programme every day and adds the films to a list on your
[Trakt](https://trakt.tv) account.

The list is **append-only**: new films are added, nothing is ever removed, so
the list builds up as an archive of everything that played at Cinema Zed.

## How it works

1. Scrapes the Cinema Zed programme page (`/film/program`).
2. Matches each film against the Trakt search API.
3. Adds any film that isn't already on the list to your Trakt list
   (created automatically the first time).
4. Repeats once a day at a configurable time.

## Setup

### 1. Create a Trakt API application

Go to <https://trakt.tv/oauth/applications> and create a new application.

- **Redirect URI:** `urn:ietf:wg:oauth:2.0:oob`
- Note the **Client ID** and **Client Secret**.

### 2. Configure

```sh
cp .env.example .env
```

Edit `.env` and fill in `TRAKT_CLIENT_ID` and `TRAKT_CLIENT_SECRET`.
Adjust `TRAKT_LIST_NAME`, `RUN_AT` and `TZ` if you like.

### 3. Authorize (one time)

This links the app to your Trakt account. It prints a URL and a code —
open the URL, enter the code, approve.

```sh
docker compose run --rm cinema-zed-trakt python -m app.authorize
```

The resulting tokens are stored in `./data/trakt_tokens.json` and refreshed
automatically afterwards.

### 4. Run

```sh
docker compose up -d --build
```

The container runs a sync immediately on startup and then every day at
`RUN_AT`. Follow the logs with:

```sh
docker compose logs -f
```

## Useful commands

| Command | What it does |
| --- | --- |
| `docker compose run --rm cinema-zed-trakt python -m app.cinema_zed` | Print the scraped programme (debug). |
| `RUN_ONCE=1` in `.env` | Run a single sync and exit (e.g. for use with host `cron`). |
| Delete `data/trakt_tokens.json` | Forces re-authorization. |

## Configuration

All settings are environment variables (see `.env.example`):

| Variable | Default | Description |
| --- | --- | --- |
| `TRAKT_CLIENT_ID` | – | Trakt application client ID (required). |
| `TRAKT_CLIENT_SECRET` | – | Trakt application client secret (required). |
| `TRAKT_LIST_NAME` | `Cinema Zed` | Name of the Trakt list to maintain. |
| `TRAKT_LIST_PRIVACY` | `private` | `private`, `friends` or `public`. |
| `CINEMA_ZED_URL` | `https://www.cinemazed.be/film/program` | Programme page to scrape. |
| `RUN_AT` | `08:00` | Daily run time (24h, in `TZ`). |
| `TZ` | `Europe/Brussels` | Container timezone. |
| `RUN_ONCE` | `0` | `1` = run once and exit. |
| `FETCH_FILM_DETAILS` | `1` | Fetch detail pages to read each film's year. |

## Notes

- The scraper reads structured `JSON-LD` data when the site exposes it and
  falls back to parsing `/film/...` links otherwise. If Cinema Zed changes
  their site layout, run the `app.cinema_zed` debug command above to check
  what is being picked up, and adjust the parser in `app/cinema_zed.py`.
- Trakt's search is used to match titles; rare or very new films may not be
  found and are logged as unmatched.
