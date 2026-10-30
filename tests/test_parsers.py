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
        sp=[{'ticker':'KXNHLSPREAD-26OCT25NYIDAL-DAL1','event_ticker':'KXNHLSPREAD-26OCT25NYIDAL','yes_bid':30,'yes_ask':34},
            {'ticker':'KXNHLSPREAD-26OCT25NYIDAL-NYI1','event_ticker':'KXNHLSPREAD-26OCT25NYIDAL','yes_bid':18,'yes_ask':22},
            {'ticker':'KXNHLSPREAD-26OCT25NYIDAL-DAL2','event_ticker':'KXNHLSPREAD-26OCT25NYIDAL','yes_bid':10,'yes_ask':12}]
        r2=kalshi.parse(ms+sp, dt.date(2026,10,25))
        self.assertAlmostEqual(r2['NYI@DAL']['pl_a'],1-0.32)   # NYI +1.5 covers unless DAL wins by 2+
        self.assertAlmostEqual(r2['NYI@DAL']['pl_h'],1-0.20)
        self.assertNotIn('pl_h', r['TBL@NJD'])
        self.assertEqual(kalshi.parse(ms, dt.date(2026, 10, 26)), {})



class M(unittest.TestCase):
    def test_puckline_probs(self):
        import nhl_v5 as m
        hm, am = m.pl_probs(3.3, 3.0)
        self.assertTrue(.55 < am < .9 and .55 < hm < .9)
        self.assertGreater(hm + am, 1.2)   # both teams can cover +1.5 in the same game


class PL(unittest.TestCase):
    def test_parlay_days(self):
        import parlay
        def p(i, a, h, ph, o55, plh, pla, n=1): return dict(id=i, date='2026-10-30', model='v5', pass_no=n, made_at='2026-10-30T10:00Z', away=a, home=h, p_home=ph, o55=o55, pl_h=plh, pl_a=pla)
        P = [p('2026-10-30_AAA@BBB', 'AAA', 'BBB', .70, .55, .88, .60), p('2026-10-30_CCC@DDD', 'CCC', 'DDD', .52, .66, .73, .73),
             p('2026-10-30_EEE@FFF', 'EEE', 'FFF', .55, .52, .80, .70), p('2026-10-30_GGG@HHH', 'GGG', 'HHH', .60, .54, .85, .66)]
        G = [dict(id='2026-10-30_AAA@BBB', ag=1, hg=4, ot=None, winner='BBB'), dict(id='2026-10-30_CCC@DDD', ag=4, hg=3, ot='SO', winner='CCC'),
             dict(id='2026-10-30_EEE@FFF', ag=2, hg=3, ot='OT', winner='FFF'), dict(id='2026-10-30_GGG@HHH', ag=3, hg=1, ot=None, winner='GGG')]
        d, ty = parlay.days(P, [], G)
        self.assertEqual(len(d), 1); self.assertEqual(d[0]['n'], 4)
        self.assertTrue(all(l['model'] for l in d[0]['legs']))          # no Kalshi rows -> model odds, flagged
        self.assertEqual(sum(v['n'] for v in ty.values()), 4)
        self.assertEqual(d[0]['pnl'], round(10 * d[0]['odds'] - 10, 2) if d[0]['won'] else -10)
        # a game that is not final yet keeps the whole day out of the record
        self.assertEqual(parlay.days(P, [], G[:3])[0], [])
        # result rules
        g = dict(ag=4, hg=3, ot='SO', winner='AAA')
        self.assertTrue(parlay.leg_result(dict(kind='tot', over=True), 'AAA', 'BBB', g))      # 4-3 SO = 6 real goals (SO goal not counted): over 5.5
        self.assertFalse(parlay.leg_result(dict(kind='tot', over=False), 'AAA', 'BBB', g))
        self.assertTrue(parlay.leg_result(dict(kind='tot', over=False), 'AAA', 'BBB', dict(ag=3, hg=2, ot='SO', winner='AAA')))   # 3-2 SO = 4 goals
        self.assertTrue(parlay.leg_result(dict(kind='pl', team='BBB'), 'AAA', 'BBB', g))      # lost by 1
        self.assertFalse(parlay.leg_result(dict(kind='pl', team='BBB'), 'AAA', 'BBB', dict(ag=5, hg=3, ot=None, winner='AAA')))


if __name__ == '__main__': unittest.main()
