"""Append final results to the log.  Usage: python grade_day.py results.json
results.json = list of {date, away, home, ag, hg, a_sh, h_sh, ot (null|'OT'|'SO'), winner (only needed for SO)}"""
import json, sys, nhl_v5 as m
D=m.D; G=json.load(open(D+'/games_log.json')); have={g['id'] for g in G}
new=json.load(open(sys.argv[1])); n=0
for g in new:
    g['id']=f"{g['date']}_{g['away']}@{g['home']}"
    g.setdefault('ot',None); g['winner']=g.get('winner') or (g['home'] if g['hg']>g['ag'] else g['away'])
    if g['id'] not in have: G.append(g); n+=1
json.dump(G,open(D+'/games_log.json','w'),indent=1); print('added',n,'total',len(G))
