"""Project a slate, append to the prediction log. Usage: edit SLATE below (or import and call project_slate)."""
import json, math, datetime
import nhl_v5 as m, unicodedata
norm=lambda x:' '.join(unicodedata.normalize('NFKD',x).encode('ascii','ignore').decode().lower().replace('.','').replace('-',' ').split())
def _key(x):
    t=norm(x).split()
    return (t[0][:1],' '.join(t[1:])) if len(t)>1 else (t[0][:1] if t else '',' '.join(t))
def lineup_match(name,names):
    """True if `name` is in `names`: exact (normalised) match, or same first initial + same last name (Zack/Zachary Bolduc)."""
    n=norm(name)
    if n in {norm(x) for x in names}: return True
    k=_key(name); return any(_key(x)==k for x in names)
D=m.D
GOALIE_SV={ # name:(saves25,sa25,saves26,sa26)  — only goalies with data; others neutral
 'Luukkonen':(846,930,56,69)}
def gfac(name):
    s=GOALIE_SV.get(name)
    if not s: return 1.0,False
    sv=(0.6*s[0]+s[2]+0.905*500)/(0.6*s[1]+s[3]+500)
    return 1+0.6*((1-sv)/(1-0.905)-1),True
def nbin_ge(es,k,shape=8):
    return 1-sum(math.exp(math.lgamma(x+shape)-math.lgamma(shape)-math.lgamma(x+1)+shape*math.log(shape/(shape+es))+x*math.log(es/(shape+es))) for x in range(k))
TRIM={2:.94,3:.90,4:.80,5:.72}
def players_for(R,gm,gf_by_team,players,top=5,lineups=None):
    out=[]
    for side in('away','home'):
        t=gm[side]; o=gm['home'] if side=='away' else gm['away']; home=side=='home'
        lam=gm['lh'] if home else gm['la']; S=gm['sh'] if home else gm['sa']; hf=1.03 if home else .97
        opp_gf=gf_by_team[o]
        cand=[]
        lu=(lineups or {}).get(t); inn=list(lu['lines']) if lu else None
        inj={norm(k):v for k,v in lu['inj'].items()} if lu else {}
        injk={_key(k):v for k,v in lu['inj'].items()} if lu else {}
        for p in players:
            if p['team']!=t: continue
            st=inj.get(norm(p['name'])) or injk.get(_key(p['name']),'')
            if lu and (not lineup_match(p['name'],inn) or st.startswith('IR') or st=='OUT'): continue
            n=p['gp26']; w=n/(n+25)
            if p['gp25']>0:
                gr=(1-w)*p['g25']/p['gp25']+w*(p['g26']/n if n else p['g25']/p['gp25'])
                ar=(1-w)*p['a25']/p['gp25']+w*(p['a26']/n if n else p['a25']/p['gp25'])
                sr=(1-w)*p['s25']/p['gp25']+w*(p['s26']/n if n else p['s25']/p['gp25'])
            else:
                gr=(p['g26']/n)*.5+.1 if n else .1; ar=(p['a26']/n)*.5+.15 if n else .15; sr=(p['s26']/n)*.6+.8 if n else .8
            adj=((m.LG_G+R[o]['d'])/m.LG_G)*0.9+0.1
            eg=gr*adj*hf*0.87*opp_gf**0.8; ea=ar*adj*hf*0.87*opp_gf**0.8
            es=sr*(S/m.PRI[p['old']][2])**0.9*hf**0.5
            ep=eg+ea
            cand.append(dict(name=p['name'],team=t,opp=o,pos=p['pos'],p_pt=round(1-math.exp(-ep),4),p_g=round(1-math.exp(-eg),4),
                 ep=round(ep,3),sog=round(es,2),**{f'sog{k}_raw':round(nbin_ge(es,k),4) for k in(2,3,4)},**{f'sog{k}':round(nbin_ge(es,k)*TRIM[k],4) for k in(2,3,4)},
                 dtd=(st=='DTD'),basis=f"2025-26 {p['gp25']:.0f} GP + 2026-27 {n:.0f} GP (stats as of {p.get('asof','Oct 14')})"))
        cand.sort(key=lambda c:-c['ep']); out+=cand[:top]
    return out
def project_slate(date,slate,goalies,status,b2b=(),market=None,write=True,lineups=None,only=None):
    """only = set of game ids to LOG (None = all). Every game is still projected for the page."""
    R,_=m.replay()
    players=json.load(open(D+'/players_base.json'))
    gms=[];allp=[]
    for a,h in slate:
        ga,gh=goalies[a],goalies[h]; fa,ka=gfac(ga); fh,kh=gfac(gh)
        pr=m.project(R,a,h,b2b=b2b,gf_a=fa,gf_h=fh)
        pr.update(goalie_a=ga,goalie_h=gh,goalie_status_a=status.get(a,'unconfirmed'),goalie_status_h=status.get(h,'unconfirmed'),goalie_data_a=ka,goalie_data_h=kh,
                  id=f'{date}_{a}@{h}',date=date)
        P0=dict(m.PARAMS,HOME_G=0,HOME_S=0)          # same model with home ice switched off, then back-to-back, then goalies, one at a time
        p0=m.project(R,a,h,P=P0)['p_home']; p1=m.project(R,a,h)['p_home']; p2=m.project(R,a,h,b2b=b2b)['p_home']
        pr['why']=dict(neutral=round(p0,4),home=round(p1-p0,4),b2b=round(p2-p1,4),goalie=round(pr['p_home']-p2,4),b2b_teams=[t for t in (a,h) if t in b2b],
                       goalie_adj=bool(ka or kh))
        gms.append(pr)
        allp+=players_for(R,pr,{a:fa,h:fh},players,lineups=lineups)
    if write:
        P=json.load(open(D+'/predictions_log.json'))
        npass=1+len({x['made_at'] for x in P if x['date']==date and x['model']=='v5'})
        now=datetime.datetime.now(datetime.UTC).isoformat(timespec='minutes')+'Z'
        for g in (x for x in gms if only is None or x['id'] in only):
            P.append(dict(id=g['id'],date=date,model='v5',pass_no=npass,made_at=now,away=g['away'],home=g['home'],p_home=round(g['p_home'],4),total=round(g['total'],3),
                shots_h=round(g['sh'],2),shots_a=round(g['sa'],2),o55=round(g['o55'],4),goalie_a=g['goalie_a'],goalie_h=g['goalie_h'],goalie_status_a=g['goalie_status_a'],goalie_status_h=g['goalie_status_h'],roster_snapshot={t:(lineups or {}).get(t) for t in(g['away'],g['home'])},
                players=[q for q in allp if q['team'] in(g['away'],g['home'])],params=m.PARAMS))
        json.dump(P,open(D+'/predictions_log.json','w'),indent=1)
    return R,gms,allp
