# nhl-v5

NHL game and player-prop projections. The model is frozen until about 300 games are logged (refit planned Mon Nov 23).
Every projection and every result is logged in `data/`, and the report card is the page in `docs/`.

**Live page:** https://chiggiechonga.github.io/nhl-v5/

## How it runs by itself
`.github/workflows/nhl.yml` runs on a schedule (GitHub Actions) and commits any changed data back to this repo:

| mode | when | what |
|---|---|---|
| `plan` | every 30 min, 8am to 11pm ET | NHL schedule, Daily Faceoff goalies and lineups, Kalshi prices. Logs a new pass only for games that have not started and are new or whose goalies changed. |
| `grade` | hourly overnight, and after each plan | finished games from the NHL box score into `games_log.json` and `player_results.json`, then rebuilds the page |
| `players` | daily | season stats from NHL club-stats into `players_base.json` |

Run one by hand: Actions tab, `nhl-v5`, Run workflow, mode `plan` / `grade` / `players`.

## Honesty rules built in
- A goalie is only marked `confirmed` if Daily Faceoff says so; otherwise `TBD` or `unconfirmed`.
- A game that has started is never projected or re-projected.
- Model parameters are never changed by automation.
- Anything that fails is written to `data/health.json` (shown at the bottom of the page) and, for scrapers, a structure sketch goes to `data/debug/`. The run keeps the previous good data instead of guessing.

## Files
`nhl_v5.py` model, `project_day.py` projections, `run_slate.py` builds the page, `auto/` fetchers and runner, `data/` all logs, `docs/` the site, `tests/` parser tests (`python -m unittest discover tests`).

Daily Faceoff has no public API; the scraper reads the JSON embedded in its pages and may need fixing if the site changes.
