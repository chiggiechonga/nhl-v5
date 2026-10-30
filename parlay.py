"""Cheat-sheet parlay: one leg per game, tracked from the frozen prediction log so it can be graded later.

Selection (same rule as the page): each game has three candidate legs, favorite ML, underdog +1.5, over/under 5.5. A game gets the
bet type where the model is strongest compared with the other games that day (z-score within the type). Prices are the last saved
pregame Kalshi price for that leg; if none was saved the model's own fair price is used and the leg is flagged `model`.
A day only counts once every game that day is final, and only if every game has a logged pass with the +1.5 fields (pl_h / pl_a).
Nothing here touches model parameters."""
import re


def cands(p, mk):
    """p = latest logged v5 pass for a game; mk = latest Kalshi row (or None)."""
    home_fav = p['p_home'] >= .5
    fav, dog = (p['home'], p['away']) if home_fav else (p['away'], p['home'])
    over = p['o55'] >= .5
    mk = mk or {}
    return [
        dict(kind='ml', team=fav, p=max(p['p_home'], 1 - p['p_home']), mk=(mk.get('home_prob') if home_fav else (None if mk.get('home_prob') is None else 1 - mk['home_prob']))),
        dict(kind='pl', team=dog, p=p['pl_a'] if home_fav else p['pl_h'], mk=mk.get('pl_a') if home_fav else mk.get('pl_h')),
        dict(kind='tot', over=over, p=p['o55'] if over else 1 - p['o55'], mk=(None if mk.get('over55') is None else (mk['over55'] if over else 1 - mk['over55']))),
    ]


def select(all_cands):
    """all_cands = list (one per game) of candidate lists. Returns the chosen leg per game, with decimal odds."""
    st = {}
    for kind in ('ml', 'pl', 'tot'):
        ps = [c['p'] for cs in all_cands for c in cs if c['kind'] == kind]
        mu = sum(ps) / len(ps); sd = (sum((x - mu) ** 2 for x in ps) / len(ps)) ** .5 or 1
        st[kind] = (mu, sd)
    out = []
    for cs in all_cands:
        best = max(cs, key=lambda c: (c['p'] - st[c['kind']][0]) / st[c['kind']][1])
        real = best['mk'] is not None and .02 < best['mk'] < .98
        best = dict(best, price=best['mk'] if real else best['p'], model=not real)
        best['dec'] = 1 / best['price']
        out.append(best)
    return out


def label(leg, away, home):
    if leg['kind'] == 'ml': return f"{leg['team']} ML"
    if leg['kind'] == 'pl': return f"{leg['team']} +1.5"
    return f"{away}/{home} {'O' if leg['over'] else 'U'}5.5"


def leg_result(leg, away, home, g):
    """g = games_log row (ag, hg, ot, winner). Returns True/False."""
    if leg['kind'] == 'ml': return g['winner'] == leg['team']
    if leg['kind'] == 'pl':
        margin = g['hg'] - g['ag'] if leg['team'] == home else g['ag'] - g['hg']
        return margin >= -1                      # an OT/SO loss is a 1-goal loss
    tot = g['ag'] + g['hg'] - (1 if g.get('ot') == 'SO' else 0)   # the shootout goal does not count toward totals
    return tot > 5 if leg['over'] else tot < 6


def o55_of(row):
    if row.get('over55') is not None: return row['over55']
    m = re.search(r'O5\.5 (?:goals )?(\d+)%', row.get('note', ''))
    return int(m.group(1)) / 100 if m else None


def days(P, M, G, stake=10.0, manual=()):
    """P predictions_log, M market_log, G games_log -> list of graded days + per-type hit rates."""
    Gd = {g['id']: g for g in G}
    mk = {}
    for r in M:
        if r['source'] == 'Kalshi moneyline':
            mk[(r['date'], r['game'])] = dict(home_prob=r['home_prob'], over55=o55_of(r), pl_h=r.get('pl_h'), pl_a=r.get('pl_a'))
    latest = {}
    for p in P:
        if p['model'] != 'v5' or 'pl_h' not in p: continue
        k = p['id']
        if k not in latest or (p['pass_no'], p['made_at']) > (latest[k]['pass_no'], latest[k]['made_at']): latest[k] = p
    dates = sorted({p['date'] for p in P if p['model'] == 'v5'})
    res, types, cum = [], {t: [0, 0] for t in ('ml', 'pl', 'tot')}, 0.0
    for d in dates:
        ids = sorted({p['id'] for p in P if p['model'] == 'v5' and p['date'] == d})
        if not ids or any(i not in latest for i in ids) or any(i not in Gd for i in ids): continue   # incomplete or not all final yet
        ps = [latest[i] for i in ids]
        legs = select([cands(p, mk.get((d, f"{p['away']}@{p['home']}"))) for p in ps])
        rows = []
        for p, l in zip(ps, legs):
            ok = leg_result(l, p['away'], p['home'], Gd[p['id']])
            types[l['kind']][0] += 1; types[l['kind']][1] += int(ok)
            rows.append(dict(label=label(l, p['away'], p['home']), kind=l['kind'], dec=round(l['dec'], 3), model=l['model'], hit=ok, pnl=round(stake * l['dec'] - stake, 2) if ok else -stake))
        D = 1.0
        for r in rows: D *= r['dec']
        won = all(r['hit'] for r in rows)
        pnl = round(stake * D - stake, 2) if won else -stake
        cum = round(cum + pnl, 2)
        res.append(dict(date=d, legs=rows, n=len(rows), hits=sum(r['hit'] for r in rows), odds=round(D, 2), won=won, pnl=pnl, cum=cum))
    # tickets entered by hand from a screenshot (days the log could not rebuild); graded by the same rules from games_log
    have = {r['date'] for r in res}
    for mrow in manual:
        d = mrow['date']
        if d in have: continue
        gids = [f"{d}_{l['game']}" for l in mrow['legs']]
        if any(i not in Gd for i in gids): continue          # not all final yet
        rows = []
        for l, gid in zip(mrow['legs'], gids):
            away, home = l['game'].split('@')
            ok = leg_result(l, away, home, Gd[gid])
            types[l['kind']][0] += 1; types[l['kind']][1] += int(ok)
            rows.append(dict(label=label(l, away, home), kind=l['kind'], dec=l['dec'], model=l['model'], hit=ok, pnl=round(stake * l['dec'] - stake, 2) if ok else -stake))
        D = mrow.get('odds_shown') or 1.0
        if not mrow.get('odds_shown'):
            for r in rows: D *= r['dec']
        won = all(r['hit'] for r in rows)
        res.append(dict(date=d, legs=rows, n=len(rows), hits=sum(r['hit'] for r in rows), odds=round(D, 2), won=won,
                        pnl=round(stake * D - stake, 2) if won else -stake, source=mrow.get('source', 'manual')))
    res.sort(key=lambda r: r['date']); cum = 0.0
    for r in res: cum = round(cum + r['pnl'], 2); r['cum'] = cum
    c2 = 0.0
    for r in res:
        r['singles'] = round(sum(l['pnl'] for l in r['legs']), 2); c2 = round(c2 + r['singles'], 2); r['singles_cum'] = c2
    return res, {k: dict(n=v[0], hit=v[1]) for k, v in types.items()}
