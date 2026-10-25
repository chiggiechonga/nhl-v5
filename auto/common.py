"""Shared helpers: HTTP, team codes, name normalisation, health log."""
import json, os, re, sys, time, unicodedata, datetime as dt
import urllib.request, urllib.error
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
sys.path.insert(0, ROOT)

UA = 'Mozilla/5.0 (compatible; nhl-v5-bot; +https://github.com/chiggiechonga/nhl-v5)'
ET = ZoneInfo('America/New_York')
PT = ZoneInfo('America/Los_Angeles')

TEAMS = ['ANA', 'BOS', 'BUF', 'CAR', 'CBJ', 'CGY', 'CHI', 'COL', 'DAL', 'DET', 'EDM', 'FLA', 'LAK', 'MIN', 'MTL', 'NJD',
         'NSH', 'NYI', 'NYR', 'OTT', 'PHI', 'PIT', 'SEA', 'SJS', 'STL', 'TBL', 'TOR', 'UTA', 'VAN', 'VGK', 'WPG', 'WSH']
# other spellings of team codes -> model codes
ALIAS = {'NJ': 'NJD', 'TB': 'TBL', 'LA': 'LAK', 'SJ': 'SJS', 'TBL': 'TBL', 'VEG': 'VGK', 'LV': 'VGK', 'WAS': 'WSH',
         'MON': 'MTL', 'UTAH': 'UTA', 'UTM': 'UTA'}
FULL = {  # Daily Faceoff / full names -> code
    'anaheim ducks': 'ANA', 'boston bruins': 'BOS', 'buffalo sabres': 'BUF', 'carolina hurricanes': 'CAR',
    'columbus blue jackets': 'CBJ', 'calgary flames': 'CGY', 'chicago blackhawks': 'CHI', 'colorado avalanche': 'COL',
    'dallas stars': 'DAL', 'detroit red wings': 'DET', 'edmonton oilers': 'EDM', 'florida panthers': 'FLA',
    'la kings': 'LAK', 'los angeles kings': 'LAK', 'minnesota wild': 'MIN', 'montreal canadiens': 'MTL',
    'montréal canadiens': 'MTL', 'new jersey devils': 'NJD', 'nashville predators': 'NSH', 'new york islanders': 'NYI',
    'ny islanders': 'NYI', 'new york rangers': 'NYR', 'ny rangers': 'NYR', 'ottawa senators': 'OTT',
    'philadelphia flyers': 'PHI', 'pittsburgh penguins': 'PIT', 'seattle kraken': 'SEA', 'san jose sharks': 'SJS',
    'st. louis blues': 'STL', 'st louis blues': 'STL', 'tampa bay lightning': 'TBL', 'toronto maple leafs': 'TOR',
    'utah mammoth': 'UTA', 'utah hockey club': 'UTA', 'vancouver canucks': 'VAN', 'vegas golden knights': 'VGK',
    'winnipeg jets': 'WPG', 'washington capitals': 'WSH'}
SLUG = {  # code -> Daily Faceoff team slug
    'ANA': 'anaheim-ducks', 'BOS': 'boston-bruins', 'BUF': 'buffalo-sabres', 'CAR': 'carolina-hurricanes',
    'CBJ': 'columbus-blue-jackets', 'CGY': 'calgary-flames', 'CHI': 'chicago-blackhawks', 'COL': 'colorado-avalanche',
    'DAL': 'dallas-stars', 'DET': 'detroit-red-wings', 'EDM': 'edmonton-oilers', 'FLA': 'florida-panthers',
    'LAK': 'los-angeles-kings', 'MIN': 'minnesota-wild', 'MTL': 'montreal-canadiens', 'NJD': 'new-jersey-devils',
    'NSH': 'nashville-predators', 'NYI': 'new-york-islanders', 'NYR': 'new-york-rangers', 'OTT': 'ottawa-senators',
    'PHI': 'philadelphia-flyers', 'PIT': 'pittsburgh-penguins', 'SEA': 'seattle-kraken', 'SJS': 'san-jose-sharks',
    'STL': 'st-louis-blues', 'TBL': 'tampa-bay-lightning', 'TOR': 'toronto-maple-leafs', 'UTA': 'utah-mammoth',
    'VAN': 'vancouver-canucks', 'VGK': 'vegas-golden-knights', 'WPG': 'winnipeg-jets', 'WSH': 'washington-capitals'}


def team(x):
    """Any spelling -> model team code, or None."""
    if not x: return None
    k = str(x).strip()
    if k.upper() in TEAMS: return k.upper()
    if k.upper() in ALIAS: return ALIAS[k.upper()]
    return FULL.get(k.lower())


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return ' '.join(s.replace('.', '').replace('-', ' ').replace("'", '').split())


def name_key(full):
    """(first initial, last name incl. suffix words) e.g. 'Joel Eriksson Ek' -> ('j','eriksson ek')."""
    t = norm(full).split()
    if len(t) < 2: return (t[0][:1] if t else '', ' '.join(t))
    return (t[0][:1], ' '.join(t[1:]))


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def et_today(now=None):
    return (now or now_utc()).astimezone(ET).date()


def get(url, as_json=True, retries=3, timeout=30, headers=None, pause=0.0):
    """GET with retries. Raises the last error."""
    h = {'User-Agent': UA, 'Accept': 'application/json, text/html;q=0.9, */*;q=0.5'}
    h.update(headers or {})
    last = None
    for i in range(retries):
        try:
            if pause: time.sleep(pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read().decode('utf-8', 'replace')
            return json.loads(body) if as_json else body
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def load(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p): return default
    return json.load(open(p))


def save(name, obj, indent=1):
    json.dump(obj, open(os.path.join(DATA, name), 'w'), indent=indent, ensure_ascii=False, default=float)


class Health:
    """Collects what worked and what didn't; written to data/health.json and shown on the page."""
    def __init__(self, mode):
        self.d = dict(mode=mode, at=now_utc().isoformat(timespec='minutes'), ok=[], problems=[])

    def ok(self, msg): self.d['ok'].append(msg); print('OK  ', msg)

    def problem(self, msg): self.d['problems'].append(msg); print('FAIL', msg)

    def write(self):
        old = load('health.json', {}) or {}
        hist = old.get('history', [])[-9:]
        hist.append(dict(mode=self.d['mode'], at=self.d['at'], n_ok=len(self.d['ok']), problems=self.d['problems']))
        out = dict(self.d); out['history'] = hist
        save('health.json', out)
