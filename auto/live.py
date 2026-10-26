"""Live-score relay.   python auto/live.py [minutes]

Browsers cannot read the NHL scoreboard directly if the NHL does not allow it, so while games are on this polls the scoreboard
every 30 s and publishes a tiny live.json to the 'live' branch (force-pushed, so no history piles up and no Pages rebuild).
The page reads it from raw.githubusercontent.com. Exits immediately when nothing is live or about to start."""
import os, sys, json, time, subprocess, shutil, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *            # noqa
import nhl_api

MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 25
OUT = '/tmp/live_pub'
REPO = os.environ.get('GITHUB_REPOSITORY', 'chiggiechonga/nhl-v5')
TOKEN = os.environ.get('GITHUB_TOKEN', '')


def slim(g):
    return dict(gameState=g.get('gameState'), startTimeUTC=g.get('startTimeUTC'),
                awayTeam=dict(abbrev=g['awayTeam']['abbrev'], score=g['awayTeam'].get('score')),
                homeTeam=dict(abbrev=g['homeTeam']['abbrev'], score=g['homeTeam'].get('score')),
                periodDescriptor=g.get('periodDescriptor') or {}, clock=g.get('clock') or {})


def snapshot():
    now = now_utc(); today = et_today(now); days = {}; active = False
    for d in (today - dt.timedelta(days=1), today):
        try: js = nhl_api.score(d)
        except Exception as e:
            print('score fetch failed', d, e); continue
        gs = [slim(g) for g in js.get('games', []) if g.get('gameType', 2) == 2]
        days[str(d)] = dict(games=gs)
        for g in gs:
            st = g['gameState']
            if st in ('LIVE', 'CRIT'): active = True
            if st in ('FUT', 'PRE') and g['startTimeUTC']:
                t = dt.datetime.fromisoformat(g['startTimeUTC'].replace('Z', '+00:00'))
                if t - now < dt.timedelta(minutes=30): active = True
    return dict(asof=now.isoformat(timespec='seconds'), days=days), active


def git(*a, check=True):
    return subprocess.run(['git', '-C', OUT, *a], check=check, capture_output=True, text=True)


def publish(obj):
    os.makedirs(OUT, exist_ok=True)
    json.dump(obj, open(os.path.join(OUT, 'live.json'), 'w'), separators=(',', ':'))
    if not os.path.exists(os.path.join(OUT, '.git')):
        git('init', '-q'); git('checkout', '-q', '-b', 'live')
        git('config', 'user.name', 'nhl-v5-bot'); git('config', 'user.email', 'actions@users.noreply.github.com')
        git('remote', 'add', 'origin', f'https://x-access-token:{TOKEN}@github.com/{REPO}.git')
    git('add', 'live.json')
    r = git('commit', '-q', '-m', 'live scores ' + obj['asof'], check=False)
    p = git('push', '-q', '-f', 'origin', 'HEAD:live', check=False)
    if p.returncode: print('push failed:', p.stderr[-300:])


if __name__ == '__main__':
    end = time.time() + MIN * 60; last = None; n = 0
    while True:
        obj, active = snapshot()
        if not active and n == 0:
            print('nothing live or starting soon; exiting'); break
        body = json.dumps(obj['days'], sort_keys=True)
        if body != last or n % 10 == 0:      # publish on change, and a heartbeat every ~5 min
            if TOKEN: publish(obj)
            else: print('no token; would publish', len(body), 'bytes')
            last = body
        n += 1
        if time.time() + 30 > end or (not active and n > 3): break
        time.sleep(30)
    print('done after', n, 'polls')
