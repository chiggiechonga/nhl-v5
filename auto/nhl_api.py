"""NHL public API (api-web.nhle.com): schedule, finals, box scores, club skater stats.
Parsers are pure functions over the JSON so they can be tested on fixtures."""
import datetime as dt
from common import get, team, norm

BASE = 'https://api-web.nhle.com/v1'
FINAL_STATES = {'FINAL', 'OFF'}


def schedule(date):
    return get(f'{BASE}/schedule/{date}')


def score(date):
    return get(f'{BASE}/score/{date}')


def boxscore(game_id):
    return get(f'{BASE}/gamecenter/{game_id}/boxscore')


def club_stats(code):
    return get(f'{BASE}/club-stats/{code}/now')


def games_on(sched_json, date):
    """Games on ET calendar day `date` (str YYYY-MM-DD) from a /schedule response."""
    out = []
    for day in sched_json.get('gameWeek', []):
        if day.get('date') != str(date): continue
        for g in day.get('games', []):
            a = team(g['awayTeam'].get('abbrev')); h = team(g['homeTeam'].get('abbrev'))
            if not a or not h: continue
            out.append(dict(id=g['id'], away=a, home=h, start=g.get('startTimeUTC'), state=g.get('gameState', ''),
                            type=g.get('gameType', 2)))
    return out


def started(g, now):
    """True if the game has started (or finished) as of `now` (aware datetime)."""
    if g['state'] not in ('FUT', 'PRE', ''): return True
    if g.get('start'):
        t = dt.datetime.fromisoformat(g['start'].replace('Z', '+00:00'))
        return now >= t
    return False


def final_result(box):
    """Boxscore JSON -> dict(ag,hg,a_sh,h_sh,ot,winner) or None if not final."""
    if box.get('gameState') not in FINAL_STATES: return None
    a, h = box['awayTeam'], box['homeTeam']
    last = (box.get('gameOutcome') or {}).get('lastPeriodType') or (box.get('periodDescriptor') or {}).get('periodType') or 'REG'
    ot = {'OT': 'OT', 'SO': 'SO'}.get(last)
    r = dict(away=team(a['abbrev']), home=team(h['abbrev']), ag=int(a['score']), hg=int(h['score']),
             a_sh=int(a.get('sog', 0)), h_sh=int(h.get('sog', 0)), ot=ot)
    r['winner'] = r['home'] if r['hg'] > r['ag'] else r['away']
    return r


def skaters(box):
    """Boxscore -> {team: [dict(name, goals, assists, points, sog)]} for forwards + defense (players who dressed)."""
    out = {}
    pbg = box.get('playerByGameStats') or {}
    for side, tk in (('awayTeam', 'awayTeam'), ('homeTeam', 'homeTeam')):
        code = team(box[tk]['abbrev'])
        rows = []
        for grp in ('forwards', 'defense'):
            for p in (pbg.get(side) or {}).get(grp, []):
                nm = p['name']['default'] if isinstance(p.get('name'), dict) else p.get('name', '')
                rows.append(dict(name=nm, goals=int(p.get('goals', 0)), assists=int(p.get('assists', 0)),
                                 points=int(p.get('points', p.get('goals', 0) + p.get('assists', 0))), sog=int(p.get('sog', 0))))
        out[code] = rows
    return out


def match_player(full_name, box_rows):
    """Match our 'First Last' to a box-score row ('F. Last'). Returns row, or None if absent/ambiguous."""
    toks = norm(full_name).split()
    if len(toks) < 2: return None
    first, last = toks[0][:1], ' '.join(toks[1:])
    hits = []
    for r in box_rows:
        b = norm(r['name']).split()
        if len(b) < 2: continue
        if b[0][:1] == first and ' '.join(b[1:]) == last: hits.append(r)
    if len(hits) == 1: return hits[0]
    if not hits:  # last-name-only fallback (e.g. 'J.T. Miller' vs 'J. Miller' handled above; this covers rare spellings)
        hits = [r for r in box_rows if norm(r['name']).split()[-1] == toks[-1] and norm(r['name'])[:1] == first]
        if len(hits) == 1: return hits[0]
    return None


def club_skaters(js):
    """club-stats response -> list of dict(name, pos, gp, g, a, s)."""
    out = []
    for p in js.get('skaters', []):
        fn = p['firstName']['default'] if isinstance(p.get('firstName'), dict) else p.get('firstName', '')
        ln = p['lastName']['default'] if isinstance(p.get('lastName'), dict) else p.get('lastName', '')
        pos = p.get('positionCode', 'F')
        out.append(dict(name=f'{fn} {ln}'.strip(), pos='D' if pos == 'D' else 'F', gp=float(p.get('gamesPlayed', 0)),
                        g=float(p.get('goals', 0)), a=float(p.get('assists', 0)), s=float(p.get('shots', 0))))
    return out
