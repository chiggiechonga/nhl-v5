nhl_v5/  — model, logs, dashboard builder
nhl_v5.py          ratings (xG/shot Elo), projection, calibration, replay
project_day.py     project a slate + append to data/predictions_log.json (edit slate/goalies at bottom)
build_dashboard.py rebuild dashboard.json; template.html -> ../nhl_simulator.html
data/              games_log.json, predictions_log.json, market_log.json, priors, early aggregates, players_base
Parameters are frozen until the 2026-11-23 refit.

Daily routine (manual, no scheduled tasks): the user says 'run reports' -> morning pass (feed, Daily Faceoff goalies + lineups, Kalshi + feed prices -> slate.json/lineups.json/market_log.json, run_slate.py ONCE, publish). The user says games are done -> grade pass (finals + shots -> grade_day.py, player_results.json, run_slate.py --grade, publish).
Never run run_slate.py without --grade twice in a row: each run logs a prediction pass.
Rules: never edit PARAMS before 2026-11-23. Never mark a goalie confirmed unless the source says so.

PLAYER BASE REFRESH (Oct 21): data/players_base.json was refreshed for 25 teams from Hockey-Reference team pages (2026-27 stats through ~Oct 20-21; 2025-26 totals kept from the NHL source where a player was already in the base). 69 players added from their team 2025-26 pages. Raw source: data/hr_stats_2026-10-21.txt. Teams not refreshed (still Oct 14): CBJ, MTL, WSH, TBL, COL, CHI, PHI.

RESULTS SOURCES (found Oct 23): https://api-web.nhle.com/v1/score/YYYY-MM-DD gives final scoring summaries (scorer + assists) via WebFetch; if the page truncates, /v1/gamecenter/<gameId>/landing works per game (Oct 23 ids 2026020166/167; Oct 22 ids ~2026020155-165). Points/goals for EVERY player = count in the scoring summary (shootout goals excluded). The fetch_sports_data box score omits players and gives shots only for listed ones, so shots stay None for players it omits (src='nhl_scoring_summary (shots unknown)'). Cross-check on 103 players: zero mismatches between the two sources.
