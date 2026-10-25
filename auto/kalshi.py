"""Kalshi public market data (no login needed): NHL moneyline + total-goals prices.
Event tickers look like KXNHLGAME-26OCT25NYIDAL (date + AWAY + HOME); Kalshi uses a few different team codes (NJ, TB, LA, SJ)."""
import re, datetime as dt
from common import get, team, TEAMS, ALIAS

BASE = 'https://api.elections.kalshi.com/trade-api/v2'
MON = {m: i + 1 for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])}
EV = re.compile(r'^(KXNHL[A-Z]+)-(\d\d)([A-Z]{3})(\d\d)([A-Z]+)$')


def split_teams(s):
    """'NYIDAL' -> ('NYI','DAL'): try every split where both sides are teams."""
    for i in range(2, len(s) - 1):
        a, b = team(s[:i]), team(s[i:])
        if a and b and a != b: return a, b
    return None


def price(m):
    """Mid of yes bid/ask (else last) as a 0-1 probability. Handles cents ints or dollar strings."""
    def f(k):
        v = m.get(k)
        if v in (None, '', 0, '0', '0.0000'): return None
        v = float(v)
        return v / 100 if v > 1 else v
    bid = f('yes_bid') or f('yes_bid_dollars'); ask = f('yes_ask') or f('yes_ask_dollars')
    last = f('last_price') or f('last_price_dollars')
    if bid and ask and ask >= bid: return round((bid + ask) / 2, 4)
    return last


def markets(series):
    out, cursor = [], None
    for _ in range(5):
        url = f'{BASE}/markets?series_ticker={series}&status=open&limit=200' + (f'&cursor={cursor}' if cursor else '')
        js = get(url)
        out += js.get('markets', [])
        cursor = js.get('cursor')
        if not cursor: break
    return out


def parse(ms, date):
    """List of Kalshi market dicts -> {'AWAY@HOME': {'home_prob': p, 'over55': .., 'over65': ..}} for games on `date`."""
    res = {}
    for m in ms:
        ev = m.get('event_ticker') or m.get('ticker', '').rsplit('-', 1)[0]
        mm = EV.match(ev)
        if not mm: continue
        series, yy, mon, dd, tm = mm.groups()
        d = dt.date(2000 + int(yy), MON[mon], int(dd))
        if d != date: continue
        pair = split_teams(tm)
        if not pair: continue
        a, h = pair
        p = price(m)
        if p is None: continue
        key = f'{a}@{h}'
        slot = res.setdefault(key, {})
        suffix = m.get('ticker', '').rsplit('-', 1)[-1]
        if series == 'KXNHLGAME':
            if team(suffix) == h: slot['home_prob'] = p
            elif team(suffix) == a: slot.setdefault('away_prob', p)
        elif series == 'KXNHLTOTAL':
            strike = m.get('floor_strike')
            if strike in (5.5, 6.5): slot['over%d' % int(strike * 10)] = p
    for slot in res.values():
        if 'home_prob' not in slot and 'away_prob' in slot: slot['home_prob'] = round(1 - slot['away_prob'], 4)
    return {k: v for k, v in res.items() if 'home_prob' in v}


def fetch(date):
    ms = markets('KXNHLGAME')
    try: ms += markets('KXNHLTOTAL')
    except Exception: pass
    return parse(ms, date)
