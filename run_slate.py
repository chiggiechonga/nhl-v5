"""Rebuild the dashboard. Reads data/slate.json + data/lineups.json + data/market_log.json,
optionally logs v5 projections, writes docs/dashboard.json and docs/index.html.
   python run_slate.py                  log every game on the slate as a new pass, then rebuild
   python run_slate.py --grade          rebuild only (no logging)
Normally called by auto/run.py, which decides WHICH games get logged (only games not yet started
whose goalies changed or that have no logged projection yet)."""
import json, os, datetime, sys
import nhl_v5 as m, project_day as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
D = m.D
DOCS = os.path.join(ROOT, 'docs')


def build(log=True, only=None):
    slate = json.load(open(D + '/slate.json'))
    lineups = json.load(open(D + '/lineups.json'))
    market = json.load(open(D + '/market_log.json'))
    games = [(g['away'], g['home']) for g in slate['games']]
    goalies = {}; status = {}
    for g in slate['games']:
        goalies[g['away']] = g['goalie_a']; goalies[g['home']] = g['goalie_h']
        status[g['away']] = g.get('status_a', 'unconfirmed'); status[g['home']] = g.get('status_h', 'unconfirmed')
    _, gms, allp = pd.project_slate(slate['date'], games, goalies, status, b2b=set(slate.get('b2b', [])),
                                    write=log, lineups=lineups, only=only)
    for g, s in zip(gms, slate['games']):
        g['time'] = s.get('time', '')
        fin = json.load(open(D + '/games_log.json')); fin = {x['id']: x for x in fin}.get(f"{slate['date']}_{g['away']}@{g['home']}")
        if fin: g['final'] = dict(score=f"{fin['ag']}-{fin['hg']}", ot=fin['ot'], winner=fin['winner'])
    R, rows = m.replay(); S = m.summarize(rows)
    days = {}
    for r in rows: days.setdefault(r['date'], []).append(r)
    daily = []
    for d, v in sorted(days.items()):
        h = [x for x in v if x['p4']]
        daily.append(dict(date=d, n=len(v), b5=m.brier([x['p5'] for x in v], [x['y'] for x in v]),
                          b4=m.brier([x['p4'] for x in h], [x['y'] for x in h]) if h else None))
    G = {g['id']: g for g in json.load(open(D + '/games_log.json'))}
    last = max(days); lastrows = days[last]
    graded = [dict(away=r['away'], home=r['home'], score=f"{G[r['id']]['ag']}-{G[r['id']]['hg']}", ot=G[r['id']]['ot'],
                   winner=G[r['id']]['winner'], p5=r['p5'], p4=r['p4'], tot5=r['tot5'], tot_act=r['act_total'],
                   sh_act=[G[r['id']]['a_sh'], G[r['id']]['h_sh']]) for r in lastrows]
    # $10 on the v5 pick at the last pregame Kalshi price (mid of bid/ask), before fees
    MK = {}
    for x in market:
        if x['source'] == 'Kalshi moneyline': MK[(x['date'], x['game'])] = x['home_prob']
    kd = {}
    for r in rows:
        hp = MK.get((r['date'], f"{r['away']}@{r['home']}"))
        if hp is None: continue
        pick_home = r['p5'] > .5; price = hp if pick_home else 1 - hp
        if not .02 <= price <= .98: continue
        won = (G[r['id']]['winner'] == (r['home'] if pick_home else r['away']))
        pnl = round(10 / price - 10, 2) if won else -10.0
        r['k_price'] = round(price, 3); r['k_pnl'] = pnl
        d = kd.setdefault(r['date'], dict(date=r['date'], games=len(days[r['date']]), bets=0, wins=0, pnl=0.0))
        d['bets'] += 1; d['wins'] += int(won); d['pnl'] = round(d['pnl'] + pnl, 2)
    kdays = sorted(kd.values(), key=lambda d: d['date']); cum = 0
    for d in kdays: cum = round(cum + d['pnl'], 2); d['cum'] = cum
    for g, r in zip(graded, lastrows):
        g['k_price'] = r.get('k_price'); g['k_pnl'] = r.get('k_pnl'); g['pick'] = r['home'] if r['p5'] > .5 else r['away']
    health = {}
    hp = os.path.join(D, 'health.json')
    if os.path.exists(hp):
        health = json.load(open(hp))
    out = dict(summary=S, daily=daily, graded=graded, graded_date=last, games=gms, players=allp,
               market=[x for x in market if x['date'] == slate['date']],
               lineups={t: lineups[t] for g in games for t in g if t in lineups},
               slate_label=slate['label'], slate_note=slate.get('note', ''), n_games=len(rows), target=300, refit='2026-11-23',
               player_cal=player_calibration(), health=health, kalshi_days=kdays,
               made=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'))
    os.makedirs(DOCS, exist_ok=True)
    json.dump(out, open(os.path.join(DOCS, 'dashboard.json'), 'w'), indent=1, default=float)
    t = open(os.path.join(ROOT, 'template.html')).read()
    open(os.path.join(DOCS, 'index.html'), 'w').write(t.replace('/*DATA*/null', json.dumps(out, default=float)))
    return out


def player_calibration():
    """Expected vs actual for the player props, over every graded row with a known result."""
    try:
        P = json.load(open(D + '/player_results.json'))
    except FileNotFoundError:
        return {}
    ok = [r for r in P if r.get('found') and r.get('points') is not None]
    k = [r for r in ok if r.get('shots') is not None]
    return dict(n=len(ok), pt_act=sum(r['points'] >= 1 for r in ok), pt_exp=round(sum(r['p_pt'] for r in ok), 1),
                g_act=sum(r['goals'] >= 1 for r in ok), g_exp=round(sum(r['p_g'] for r in ok), 1),
                n_shots=len(k), sh3_act=sum(r['shots'] >= 3 for r in k), sh3_exp=round(sum(r['sog3'] for r in k), 1))


if __name__ == '__main__':
    out = build(log='--grade' not in sys.argv)
    print('built', out['slate_label'], len(out['games']), 'games', len(out['players']), 'players;', out['n_games'], 'games logged; latest graded', out['graded_date'])
