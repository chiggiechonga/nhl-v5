"""Automation entry point.   python auto/run.py plan | grade | players [--dry]

plan     schedule + goalies + lineups/injuries + Kalshi -> data/*.json -> log a prediction pass ONLY for games that have not
         started and are new or whose goalies changed -> rebuild docs/.
grade    every NHL final not yet in games_log -> games_log + player_results (from the box score) -> rebuild docs/.
players  refresh players_base.json from NHL club stats (games/goals/assists/shots this season).

Rules kept from the manual routine: parameters are never touched here; a game that has started is never projected or
re-projected; nothing is marked 'confirmed' unless the source says so; failures are written to data/health.json."""
import json, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *            # noqa
import nhl_api, dailyfaceoff, kalshi

DRY = '--dry' in sys.argv


def hhmm_et(start):
    t = dt.datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(ET)
    return f"{t.hour % 12 or 12}:{t.minute:02d} ET"


def save_if(name, obj):
    if not DRY: save(name, obj)


def debug(name, obj):
    if DRY: return
    os.makedirs(os.path.join(DATA, 'debug'), exist_ok=True)
    json.dump(obj, open(os.path.join(DATA, 'debug', name), 'w'), indent=1, ensure_ascii=False)


# ----------------------------------------------------------------------------------------------------------------- plan
def plan(h):
    now = now_utc(); today = et_today(now)
    try:
        games = [g for g in nhl_api.games_on(nhl_api.schedule(today), today) if g['type'] == 2]
    except Exception as e:
        h.problem(f'NHL schedule failed: {e}'); return False
    if not games:
        h.ok(f'no regular-season games on {today}'); return False
    h.ok(f'{len(games)} games on {today}')
    try:
        yday = today - dt.timedelta(days=1)
        b2b = sorted({t for g in nhl_api.games_on(nhl_api.schedule(yday), yday) for t in (g['away'], g['home'])}
                     & {t for g in games for t in (g['away'], g['home'])})
    except Exception as e:
        b2b = []; h.problem(f'yesterday schedule failed (back-to-back flags may be missing): {e}')

    old = load('slate.json', {}) or {}
    prev = {(g['away'], g['home']): g for g in old.get('games', [])} if old.get('date') == str(today) else {}

    # goalies
    gl = {}
    try:
        gl, nd = dailyfaceoff.fetch_goalies(today)
        if gl: h.ok(f'Daily Faceoff goalies parsed for {len(gl)} teams')
        else:
            h.problem('Daily Faceoff goalie page loaded but 0 goalies parsed (parser needs a look; see data/debug/df_goalies.json)')
            debug('df_goalies.json', dailyfaceoff.outline(nd, depth=6))
    except Exception as e:
        h.problem(f'Daily Faceoff goalies failed: {e}')

    slate_games, need_lines = [], set()
    for g in games:
        is_started = nhl_api.started(g, now)
        pg = prev.get((g['away'], g['home']), {})
        row = dict(away=g['away'], home=g['home'], time=hhmm_et(g['start']), start=g['start'], gid=g['id'], started=is_started)
        for side, k in (('away', 'a'), ('home', 'h')):
            t = g[side]
            if is_started and pg:                       # freeze what we knew at puck drop
                row['goalie_' + k] = pg.get('goalie_' + k, 'TBD'); row['status_' + k] = pg.get('status_' + k, 'unconfirmed')
            elif t in gl:
                row['goalie_' + k], row['status_' + k] = gl[t]
            else:                                         # keep an earlier real answer, never invent one
                row['goalie_' + k] = pg.get('goalie_' + k, 'TBD'); row['status_' + k] = pg.get('status_' + k, 'unconfirmed')
            if not is_started: need_lines.add(t)
        slate_games.append(row)

    # lineups / injuries (only teams in games that haven't started)
    L = load('lineups.json', {}) or {}
    n_ok = 0
    for t in sorted(need_lines):
        try:
            lines, inj, nd = dailyfaceoff.fetch_lines(t)
            time.sleep(1.0)
            if len(lines) >= 12:
                L[t] = dict(asof=now.strftime('%Y-%m-%dT%H:%MZ'), source='Daily Faceoff', lines=lines, inj=inj); n_ok += 1
            else:
                h.problem(f'{t}: lineup page parsed {len(lines)} skaters (<12), kept the old lineup')
                if n_ok == 0: debug('df_lines_%s.json' % t, dailyfaceoff.outline(nd, depth=6))
        except Exception as e:
            h.problem(f'{t}: lineup fetch failed ({e}), kept the old lineup')
    if need_lines: (h.ok if n_ok else h.problem)(f'lineups refreshed for {n_ok}/{len(need_lines)} teams')

    # market
    M = load('market_log.json', []) or []
    try:
        km = kalshi.fetch(today)
        added = 0
        for g in games:
            k = f"{g['away']}@{g['home']}"; v = km.get(k)
            if not v or nhl_api.started(g, now): continue   # after puck drop the price is live, not pregame
            prior = [x for x in M if x['date'] == str(today) and x['game'] == k and x['source'] == 'Kalshi moneyline']
            def moved(key, tol):
                a_, b_ = (prior[-1].get(key) if prior else None), v.get(key)
                return (a_ is None) != (b_ is None) or (a_ is not None and abs(a_ - b_) >= tol)
            if not prior or moved('home_prob', 0.005) or moved('over55', 0.01) or moved('pl_h', 0.01) or moved('pl_a', 0.01):
                extra = ''.join(f"; O{x[4]}.{x[5]} goals {int(round(v[x]*100))}%" for x in ('over55', 'over65') if x in v)
                row = {'date': str(today), 'game': k, 'source': 'Kalshi moneyline', 'home_prob': v['home_prob'],
                       'note': f"auto {now.strftime('%H:%MZ')}; mid of bid/ask{extra}"}
                for key in ('over55', 'over65', 'pl_h', 'pl_a'):
                    if key in v: row[key] = v[key]
                M.append(row); added += 1
        h.ok(f'Kalshi: {len(km)} NHL games priced, {added} new rows')
        sp = kalshi.LAST.get('KXNHLSPREAD') or []
        if sp and not any('pl_h' in x or 'pl_a' in x for x in km.values()):
            h.problem(f'Kalshi spread markets found ({len(sp)}) but none matched a game today; sample saved to data/debug/kalshi_spread.json')
            debug('kalshi_spread.json', sp[:3])
        elif not sp: h.problem('Kalshi spread markets: none returned (+1.5 legs will use model odds)')
    except Exception as e:
        h.problem(f'Kalshi failed: {e}')

    label = dt.date.fromisoformat(str(today)).strftime('%a %b ') + str(today.day)
    notes = []
    if any(g['goalie_a'] == 'TBD' or g['goalie_h'] == 'TBD' for g in slate_games): notes.append('some goalies unknown (TBD)')
    slate = dict(date=str(today), label=label, b2b=b2b, note='; '.join(notes), games=slate_games)
    save_if('slate.json', slate); save_if('lineups.json', L); save_if('market_log.json', M)

    # which games get a logged pass: not started AND (never logged OR goalies/status changed since the last logged pass)
    P = load('predictions_log.json', [])
    only = set()
    for g in slate_games:
        if g['started']: continue
        gid = f"{today}_{g['away']}@{g['home']}"
        last = [x for x in P if x['id'] == gid and x['model'] == 'v5']
        sig = (g['goalie_a'], g['goalie_h'], g['status_a'], g['status_h'])
        if not last: only.add(gid)
        else:
            x = max(last, key=lambda r: (r.get('pass_no', 0), r.get('made_at', '')))
            if sig != (x['goalie_a'], x['goalie_h'], x['goalie_status_a'], x['goalie_status_h']): only.add(gid)
    h.ok(f'logging {len(only)} game(s): {sorted(only)}' if only else 'nothing new to log (no new games, no goalie changes)')
    if DRY: return True
    import run_slate
    run_slate.build(log=bool(only), only=only)
    return True


# ---------------------------------------------------------------------------------------------------------------- grade
def grade(h):
    now = now_utc(); today = et_today(now)
    G = load('games_log.json', []); have = {g['id'] for g in G}
    P = load('predictions_log.json', []); R = load('player_results.json', [])
    have_pl = {(r['date'], r['name']) for r in R}
    new_games = 0; new_rows = 0
    for d in (today, today - dt.timedelta(days=1), today - dt.timedelta(days=2)):
        try:
            sc = nhl_api.score(d)
        except Exception as e:
            h.problem(f'NHL scores {d} failed: {e}'); continue
        for g in sc.get('games', []):
            if g.get('gameState') not in nhl_api.FINAL_STATES or g.get('gameType', 2) != 2: continue
            a, ho = team(g['awayTeam']['abbrev']), team(g['homeTeam']['abbrev'])
            gid = f'{d}_{a}@{ho}'
            if gid in have: continue
            try:
                box = nhl_api.boxscore(g['id']); res = nhl_api.final_result(box)
            except Exception as e:
                h.problem(f'box score {gid} failed: {e}'); continue
            if not res: continue
            res.update(date=str(d), id=gid); G.append(res); have.add(gid); new_games += 1
            h.ok(f"graded {gid}: {res['ag']}-{res['hg']}{' ' + res['ot'] if res['ot'] else ''}, shots {res['a_sh']}-{res['h_sh']}")
            # player rows for the players we projected in this game (latest v5 pass)
            ent = [x for x in P if x['id'] == gid and x['model'] == 'v5']
            if not ent: continue
            last = max(ent, key=lambda r: (r.get('pass_no', 0), r.get('made_at', '')))
            sk = nhl_api.skaters(box)
            for p in last.get('players', []):
                if (str(d), p['name']) in have_pl: continue
                row = nhl_api.match_player(p['name'], sk.get(p['team'], []))
                base = dict(date=str(d), name=p['name'], team=p['team'], p_pt=p['p_pt'], p_g=p['p_g'], sog=p['sog'], sog3=p['sog3'])
                if row:
                    R.append(dict(base, found=True, points=row['points'], goals=row['goals'], shots=row['sog'], src='nhl_boxscore'))
                else:  # did not dress, or name did not match: not counted in calibration
                    R.append(dict(base, found=False, points=None, goals=None, shots=None, src='nhl_boxscore: not in box score'))
                have_pl.add((str(d), p['name'])); new_rows += 1
    if not new_games:
        h.ok('no new finals'); return False
    if not DRY:
        save('games_log.json', G); save('player_results.json', R)
        import run_slate
        run_slate.build(log=False)
    h.ok(f'{new_games} games and {new_rows} player rows added')
    return True


# --------------------------------------------------------------------------------------------------------------- players
def players(h):
    B = load('players_base.json', [])
    idx = {}
    for i, p in enumerate(B): idx.setdefault(name_key(p['name']), []).append(i)
    asof = now_utc().astimezone(ET).strftime('%b %-d')
    upd = added = 0
    for t in TEAMS:
        try:
            sk = nhl_api.club_skaters(nhl_api.club_stats(t)); time.sleep(0.5)
        except Exception as e:
            h.problem(f'club stats {t} failed: {e}'); continue
        for s in sk:
            hits = idx.get(name_key(s['name']), [])
            same = [i for i in hits if B[i]['team'] == t]
            i = (same or hits or [None])[0] if len(same or hits) == 1 else None
            if i is not None:
                B[i].update(team=t, gp26=s['gp'], g26=s['g'], a26=s['a'], s26=s['s'], asof=asof)
                upd += 1
            elif not hits and s['gp'] >= 3:
                B.append(dict(name=s['name'], team=t, pos=s['pos'], gp25=0.0, g25=0.0, a25=0.0, s25=0.0, gp26=s['gp'], g26=s['g'],
                              a26=s['a'], s26=s['s'], old=t, asof=asof))
                idx.setdefault(name_key(s['name']), []).append(len(B) - 1); added += 1
    if upd < 200:
        h.problem(f'only {upd} players matched; base NOT saved (expected ~600 skaters league-wide... check club-stats parser)')
        return False
    save_if('players_base.json', B)
    h.ok(f'players_base refreshed: {upd} updated, {added} added')
    return True


if __name__ == '__main__':
    mode = sys.argv[1]
    h = Health(mode)
    changed = False
    try:
        changed = {'plan': plan, 'grade': grade, 'players': players}[mode](h)
    except Exception as e:
        import traceback; traceback.print_exc()
        h.problem(f'{mode} crashed: {e!r}')
    if (changed or h.d['problems']) and not DRY: h.write()
    sys.exit(0)
