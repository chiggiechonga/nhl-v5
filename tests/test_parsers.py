"""Parser tests on small hand-made samples shaped like the real feeds. Run: python -m unittest discover tests
The Daily Faceoff shapes are a best guess; the first real run (data/health.json, data/debug/) is the true test."""
import os, sys, json, unittest, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'auto')); sys.path.insert(0, ROOT)
import common, nhl_api, dailyfaceoff as df, kalshi


class T(unittest.TestCase):
    def test_team_codes(self):
        self.assertEqual([common.team(x) for x in ('NJ', 'tb', 'LA', 'SJ', 'Utah Mammoth', 'xx')], ['NJD', 'TBL', 'LAK', 'SJS', 'UTA', None])

    def test_schedule_and_started(self):
        js = {'gameWeek': [{'date': '2026-10-25', 'games': [
            {'id': 1, 'awayTeam': {'abbrev': 'NYI'}, 'homeTeam': {'abbrev': 'DAL'}, 'startTimeUTC': '2026-10-25T22:00:00Z', 'gameState': 'FUT', 'gameType': 2}]},
            {'date': '2026-10-26', 'games': []}]}
        g = nhl_api.games_on(js, '2026-10-25')
        self.assertEqual((g[0]['away'], g[0]['home']), ('NYI', 'DAL'))
        U = dt.timezone.utc
        self.assertFalse(nhl_api.started(g[0], dt.datetime(2026, 10, 25, 21, 0, tzinfo=U)))
        self.assertTrue(nhl_api.started(g[0], dt.datetime(2026, 10, 25, 22, 1, tzinfo=U)))

    def test_boxscore(self):
        box = {'gameState': 'OFF', 'gameOutcome': {'lastPeriodType': 'OT'},
               'awayTeam': {'abbrev': 'TB', 'score': 4, 'sog': 32}, 'homeTeam': {'abbrev': 'UTA', 'score': 5, 'sog': 28},
               'playerByGameStats': {'awayTeam': {'forwards': [{'name': {'default': 'B. Point'}, 'goals': 1, 'assists': 1, 'points': 2, 'sog': 4}], 'defense': []},
                                     'homeTeam': {'forwards': [{'name': {'default': 'C. Keller'}, 'goals': 0, 'assists': 1, 'points': 1, 'sog': 2}], 'defense': []}}}
        r = nhl_api.final_result(box)
        self.assertEqual((r['away'], r['home'], r['ag'], r['hg'], r['ot'], r['winner']), ('TBL', 'UTA', 4, 5, 'OT', 'UTA'))
        sk = nhl_api.skaters(box)
        self.assertEqual(nhl_api.match_player('Brayden Point', sk['TBL'])['points'], 2)
        self.assertIsNone(nhl_api.match_player('Nikita Kucherov', sk['TBL']))
        self.assertIsNone(nhl_api.final_result(dict(box, gameState='LIVE')))

    def test_goalies(self):
        nd = {'props': {'pageProps': {'data': [{'homeTeamName': 'Dallas Stars', 'awayTeamName': 'New York Islanders',
              'homeGoalieName': 'Jake Oettinger', 'awayGoalieName': 'Ilya Sorokin', 'homeNewsStrengthName': 'Confirmed', 'awayNewsStrengthName': 'Likely'}]}}}
        g = df.parse_goalies(nd)
        self.assertEqual(g['DAL'], ('Jake Oettinger', 'confirmed')); self.assertEqual(g['NYI'], ('Ilya Sorokin', 'likely'))
        self.assertEqual(df.parse_goalies({'a': 1}), {})

    def test_lines(self):
        pl = [{'name': 'Kirill Kaprizov', 'groupIdentifier': 'f1', 'categoryIdentifier': 'F'},
              {'name': 'Quinn Hughes', 'groupIdentifier': 'd1', 'categoryIdentifier': 'D'},
              {'name': 'Brock Faber', 'groupIdentifier': 'ir', 'categoryIdentifier': 'IR', 'injuryStatus': 'IR'},
              {'name': 'Maxim Shabanov', 'groupIdentifier': 'f4', 'categoryIdentifier': 'F', 'injuryStatus': 'day-to-day'}]
        lines, inj = df.parse_lines({'x': {'players': pl}})
        self.assertEqual(lines, ['Kirill Kaprizov', 'Quinn Hughes', 'Maxim Shabanov'])
        self.assertEqual(inj['Brock Faber'], 'IR'); self.assertEqual(inj['Maxim Shabanov'], 'DTD')

    def test_next_data(self):
        self.assertEqual(df.next_data('<script id="__NEXT_DATA__" type="application/json">{"a":1}</script>'), {'a': 1})
        with self.assertRaises(ValueError): df.next_data('<html></html>')

    def test_kalshi(self):
        ms = [{'ticker': 'KXNHLGAME-26OCT25NYIDAL-DAL', 'event_ticker': 'KXNHLGAME-26OCT25NYIDAL', 'yes_bid': 55, 'yes_ask': 57},
              {'ticker': 'KXNHLGAME-26OCT25NYIDAL-NYI', 'event_ticker': 'KXNHLGAME-26OCT25NYIDAL', 'yes_bid': 43, 'yes_ask': 45},
              {'ticker': 'KXNHLGAME-26OCT25TBLNJ-NJ', 'event_ticker': 'KXNHLGAME-26OCT25TBLNJ', 'yes_bid': 50, 'yes_ask': 52},
              {'ticker': 'KXNHLTOTAL-26OCT25NYIDAL-6', 'event_ticker': 'KXNHLTOTAL-26OCT25NYIDAL', 'floor_strike': 5.5, 'yes_bid': 50, 'yes_ask': 54}]
        r = kalshi.parse(ms, dt.date(2026, 10, 25))
        self.assertAlmostEqual(r['NYI@DAL']['home_prob'], 0.56); self.assertAlmostEqual(r['NYI@DAL']['over55'], 0.52)
        self.assertIn('TBL@NJD', r)
        self.assertEqual(kalshi.parse(ms, dt.date(2026, 10, 26)), {})


if __name__ == '__main__': unittest.main()
