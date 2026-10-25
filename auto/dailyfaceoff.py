"""Daily Faceoff scraper (starting goalies + line combinations).

Daily Faceoff is a Next.js site: each page embeds its data as JSON in <script id="__NEXT_DATA__">. The page layout is not a
public API, so the parsers below are deliberately tolerant (they search the JSON for the right shapes instead of assuming
exact paths). If a parse comes back empty, run.py records it in data/health.json, writes a small structure outline to
data/debug/ so the parser can be fixed from the repo, and falls back to 'TBD / unconfirmed' + the last saved lineup.
It never invents a goalie."""
import json, re, time
from common import get, team, norm, SLUG

NEXT = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
STATUS = {'confirmed': 'confirmed', 'likely': 'likely', 'unconfirmed': 'unconfirmed', 'expected': 'likely', 'projected': 'unconfirmed'}


def next_data(html):
    m = NEXT.search(html)
    if not m: raise ValueError('no __NEXT_DATA__ block in page')
    return json.loads(m.group(1))


def walk(o, path=()):
    """Yield (path, value) for every dict/list node."""
    yield path, o
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, path + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from walk(v, path + (i,))


def outline(o, depth=4, max_items=3):
    """Small structural sketch of a JSON blob (keys + types), for debugging parsers."""
    if depth == 0: return type(o).__name__
    if isinstance(o, dict): return {k: outline(v, depth - 1, max_items) for k, v in list(o.items())[:40]}
    if isinstance(o, list): return [outline(v, depth - 1, max_items) for v in o[:max_items]] + (['...%d items' % len(o)] if len(o) > max_items else [])
    return o if isinstance(o, (int, float, bool)) or o is None else (o[:40] if isinstance(o, str) else type(o).__name__)


def _strength(v):
    return STATUS.get(norm(str(v)).split(' ')[0] if v else '', 'unconfirmed')


def parse_goalies(nd):
    """__NEXT_DATA__ -> {team_code: (goalie_name, status)} for every game found on the page."""
    out = {}
    for _, node in walk(nd):
        if not isinstance(node, dict): continue
        keys = {k.lower(): k for k in node}
        for side in ('home', 'away'):
            gk = next((keys[k] for k in keys if k.startswith(side) and 'goalie' in k and 'name' in k), None)
            tk = next((keys[k] for k in keys if k.startswith(side) and 'team' in k and 'name' in k), None)
            ck = next((keys[k] for k in keys if k.startswith(side) and 'team' in k and ('abbr' in k or 'code' in k)), None)
            sk = next((keys[k] for k in keys if k.startswith(side) and ('strength' in k or 'status' in k)), None)
            if not gk or not node.get(gk) or not (tk or ck): continue
            code = team(node.get(ck)) if ck else None
            code = code or (team(node.get(tk)) if tk else None)
            if code: out[code] = (str(node[gk]).strip(), _strength(node.get(sk)) if sk else 'unconfirmed')
    return out


def fetch_goalies(date):
    html = get(f'https://www.dailyfaceoff.com/starting-goalies/{date}', as_json=False)
    nd = next_data(html)
    return parse_goalies(nd), nd


def parse_lines(nd):
    """__NEXT_DATA__ of a team line-combinations page -> (lines[list of names], inj{name: status}).
    Players in forward/defense groups are 'in the lineup'; players in injury groups or carrying an injury status go to inj."""
    lines, inj = [], {}
    cands = []
    for _, node in walk(nd):
        if isinstance(node, list) and node and all(isinstance(x, dict) for x in node) and any('name' in x for x in node):
            if any(k for x in node for k in x if 'group' in k.lower() or 'category' in k.lower() or 'injur' in k.lower()):
                cands.append(node)
    for lst in cands:
        for p in lst:
            nm = p.get('name')
            if isinstance(nm, dict): nm = nm.get('default')
            if not nm: continue
            grp = str(p.get('groupIdentifier') or p.get('group') or '').lower()
            cat = str(p.get('categoryIdentifier') or p.get('category') or '').lower()
            injs = p.get('injuryStatus') or p.get('injury') or p.get('status')
            if isinstance(injs, dict): injs = injs.get('name') or injs.get('status')
            ist = norm(str(injs)) if injs else ''
            if re.fullmatch(r'[fd]\d?', grp) or (cat in ('f', 'd', 'forward', 'defense', 'forwards', 'defence') and grp not in ('ir', 'injured', 'out')):
                if nm not in lines: lines.append(nm)
            if grp in ('ir', 'injured', 'injuries') or ist:
                st = 'IR' if grp == 'ir' or 'ir' == ist or 'reserve' in ist else ('DTD' if 'day' in ist or ist == 'dtd' else ('OUT' if 'out' in ist else (ist.upper() or 'OUT')))
                inj[nm] = st
    return lines, inj


def fetch_lines(code):
    html = get(f'https://www.dailyfaceoff.com/teams/{SLUG[code]}/line-combinations', as_json=False)
    nd = next_data(html)
    lines, inj = parse_lines(nd)
    return lines, inj, nd
