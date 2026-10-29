"""NHL model v5 — shot/xG-based Elo ratings, persistent log, Platt calibration, market benchmark.
Everything is deterministic and re-runnable:  python nhl_v5.py replay | report
Design rules: (1) log every projection and result, (2) do NOT retune parameters until the refit day,
(3) ratings update game-by-game (Elo style) on an xG proxy, never on goals alone.
"""
import json, math, os, copy
D=os.path.join(os.path.dirname(os.path.abspath(__file__)),'data')
L=lambda f:json.load(open(os.path.join(D,f)))
PRI=L('priors_2025.json'); EARLY=L('early_aggregates_oct14.json')
# ---------------- parameters (frozen until refit day Mon 2026-11-23) ----------------
PARAMS=dict(KG=0.03,   # goal-rate rating step per game (Bayes-optimal ~0.03-0.04 at n~6)
            KS=0.09,   # shot-rate rating step
            XG_SHOT_W=0.65,  # weight of shots*lg_sh% in the xG proxy (rest = actual goals)
            KEEP_G=0.65, KEEP_S=0.75,  # share of 2025-26 rating kept as prior
            HOME_G=0.09, HOME_S=0.55, B2B_S=0.98, SCALE=1.0,
            CAL_A=1.0, CAL_B=0.0)   # Platt calibration, identity until enough data
LG_G=sum(v[0] for v in PRI.values())/len(PRI)/82
LG_S=sum(v[2] for v in PRI.values())/len(PRI)          # sf already per game
SHP=(sum(v[0] for v in PRI.values())/82)/sum(v[2] for v in PRI.values())   # league shooting %

def xg(shots,goals,P): return P['XG_SHOT_W']*shots*SHP+(1-P['XG_SHOT_W'])*goals

def fresh(P=PARAMS):
    R={}
    for t,(gf,ga,sf,sa) in PRI.items():
        R[t]=dict(o=(xg(sf,gf/82,P)-LG_G)*P['KEEP_G'], d=(xg(sa,ga/82,P)-LG_G)*P['KEEP_G'],
                  so=(sf-LG_S)*P['KEEP_S'], sd=(sa-LG_S)*P['KEEP_S'], n=0)
    return R

def rates(R,away,home,P=PARAMS,b2b=()):
    lh=(LG_G+R[home]['o']+R[away]['d']+P['HOME_G'])*P['SCALE']
    la=(LG_G+R[away]['o']+R[home]['d']-P['HOME_G'])*P['SCALE']
    sh=(LG_S+R[home]['so']+R[away]['sd']+P['HOME_S'])*(P['B2B_S'] if home in b2b else 1)
    sa=(LG_S+R[away]['so']+R[home]['sd']-P['HOME_S'])*(P['B2B_S'] if away in b2b else 1)
    return max(lh,.8),max(la,.8),sh,sa

def pois(l,n=16):
    p=[math.exp(-l)]
    for i in range(1,n): p.append(p[-1]*l/i)
    return p
def grid(lh,la):
    ph=pt=p00=0.0; tot=[0.0]*34
    for m,w in((.85,.25),(1,.5),(1.15,.25)):
        x=pois(lh*m); y=pois(la*m)
        for i in range(16):
            for j in range(16):
                p=w*x[i]*y[j]; tot[i+j]+=p
                if i>j: ph+=p
                elif i==j: pt+=p
                if i==0 and j==0: p00+=p
    return ph,pt,tot,p00
def pl_probs(lh,la):
    """Puck line +1.5 cover probabilities from the same goal model (regulation margin; an OT/SO loss is a 1-goal loss).
    Returns (home +1.5 covers, away +1.5 covers). Pure addition: nothing about the win probability changes."""
    hm=am=0.0
    for m,w in((.85,.25),(1,.5),(1.15,.25)):
        x=pois(lh*m); y=pois(la*m)
        for i in range(16):
            for j in range(16):
                p=w*x[i]*y[j]
                if i-j>=-1: hm+=p      # home loses by at most 1 (or wins)
                if j-i>=-1: am+=p
    return hm,am
def logit(p): p=min(max(p,1e-6),1-1e-6); return math.log(p/(1-p))
sig=lambda z:1/(1+math.exp(-z))

def project(R,away,home,P=PARAMS,b2b=(),gf_a=1.0,gf_h=1.0):
    """gf_* = goalie factor of that team's goalie (1 = neutral); multiplies the OPPONENT's goal rate."""
    lh,la,sh,sa=rates(R,away,home,P,b2b); lh*=gf_a; la*=gf_h
    ph,pt,tot,p00=grid(lh,la)
    raw=ph+pt*(0.5+(lh/(lh+la)-0.5))        # OT/SO split leans to the stronger side
    p=sig(P['CAL_A']*logit(raw)+P['CAL_B'])
    ov=lambda x:sum(tot[k] for k in range(len(tot)) if k>x)
    return dict(away=away,home=home,lh=lh,la=la,sh=sh,sa=sa,p_home_raw=raw,p_home=p,total=lh+la,
                o45=ov(4),o55=ov(5),o65=ov(6),p00=p00,pl_h=pl_probs(lh,la)[0],pl_a=pl_probs(lh,la)[1])

def update(R,g,P=PARAMS):
    pr=rates(R,g['away'],g['home'],P)
    oh=xg(g['h_sh'],g['hg'],P); oa=xg(g['a_sh'],g['ag'],P)
    rh=oh-pr[0]; ra=oa-pr[1]
    R[g['home']]['o']+=P['KG']*rh; R[g['away']]['d']+=P['KG']*rh
    R[g['away']]['o']+=P['KG']*ra; R[g['home']]['d']+=P['KG']*ra
    qh=g['h_sh']-pr[2]; qa=g['a_sh']-pr[3]
    R[g['home']]['so']+=P['KS']*qh; R[g['away']]['sd']+=P['KS']*qh
    R[g['away']]['so']+=P['KS']*qa; R[g['home']]['sd']+=P['KS']*qa
    R[g['home']]['n']+=1; R[g['away']]['n']+=1

def seed_early(R,P=PARAMS):
    """Pre-Oct-15 games only exist as per-team averages: replay each as a game vs an average opponent."""
    for t,(gp,gf,ga,sf,sa) in EARLY.items():
        for _ in range(int(gp)):
            r=R[t]
            r['o']+=P['KG']*(xg(sf,gf,P)-(LG_G+r['o']))
            r['d']+=P['KG']*(xg(sa,ga,P)-(LG_G+r['d']))
            r['so']+=P['KS']*(sf-(LG_S+r['so'])); r['sd']+=P['KS']*(sa-(LG_S+r['sd']))
        r['n']+=int(gp)

# ---------------- scoring ----------------
def brier(ps,ys): return sum((p-y)**2 for p,y in zip(ps,ys))/len(ps)
def logloss(ps,ys): return -sum(y*math.log(max(p,1e-6))+(1-y)*math.log(max(1-p,1e-6)) for p,y in zip(ps,ys))/len(ps)
def platt_fit(ps,ys,a0=1.0,b0=0.0,lam=100.0,iters=200):
    """Ridge-to-identity Platt scaling. lam = pseudo-games of prior belief that the model is already calibrated."""
    a,b=a0,b0
    for _ in range(iters):
        ga=gb=0; haa=hab=hbb=0
        for p,y in zip(ps,ys):
            z=logit(p); q=sig(a*z+b); e=q-y; w=q*(1-q)
            ga+=e*z; gb+=e; haa+=w*z*z; hab+=w*z; hbb+=w
        ga+=lam*(a-a0)/ (lam if lam else 1)*1.0*0+ (a-1.0)*lam*0.02; gb+=b*lam*0.02
        haa+=lam*0.02; hbb+=lam*0.02
        det=haa*hbb-hab*hab
        if abs(det)<1e-12: break
        da=(ga*hbb-gb*hab)/det; db=(haa*gb-hab*ga)/det
        a-=da; b-=db
        if abs(da)+abs(db)<1e-8: break
    return a,b

def replay(P=PARAMS,verbose=False):
    G=L('games_log.json'); seeds={x['id']:x for x in L('predictions_log.json')}
    R=fresh(P); seed_early(R,P)
    rows=[]
    for g in sorted(G,key=lambda x:(x['date'],x['id'])):
        pr=project(R,g['away'],g['home'],P)
        y=1 if g['winner']==g['home'] else 0
        s=seeds.get(g['id'])
        rows.append(dict(id=g['id'],date=g['date'],away=g['away'],home=g['home'],y=y,p5=pr['p_home'],tot5=pr['total'],
                         sh5=pr['sh'],sa5=pr['sa'],act_total=g['ag']+g['hg'],act_sh=(g['h_sh'],g['a_sh']),
                         p4=s['p_home'] if s and s['model']=='v4-as-published' else None,tot4=s['total'] if s else None))
        update(R,g,P)
    return R,rows

def summarize(rows):
    out={}
    ps=[r['p5'] for r in rows]; ys=[r['y'] for r in rows]
    out['n']=len(rows); out['brier5']=brier(ps,ys); out['ll5']=logloss(ps,ys)
    out['acc5']=sum((p>.5)==(y==1) for p,y in zip(ps,ys))/len(ps)
    h=[r for r in rows if r['p4'] is not None]
    out['n_h2h']=len(h)
    if h:
        out['brier4_h2h']=brier([r['p4'] for r in h],[r['y'] for r in h]); out['brier5_h2h']=brier([r['p5'] for r in h],[r['y'] for r in h])
        out['ll4_h2h']=logloss([r['p4'] for r in h],[r['y'] for r in h]); out['ll5_h2h']=logloss([r['p5'] for r in h],[r['y'] for r in h])
        out['acc4_h2h']=sum((r['p4']>.5)==(r['y']==1) for r in h)/len(h); out['acc5_h2h']=sum((r['p5']>.5)==(r['y']==1) for r in h)/len(h)
    out['tot_bias5']=sum(r['tot5']-r['act_total'] for r in rows)/len(rows)
    out['tot_mae5']=sum(abs(r['tot5']-r['act_total']) for r in rows)/len(rows)
    tr=[r for r in rows if r['tot4']]
    out['tot_bias4']=sum(r['tot4']-r['act_total'] for r in tr)/len(tr)
    out['shot_mae5']=sum(abs(r['sh5']-r['act_sh'][0])+abs(r['sa5']-r['act_sh'][1]) for r in rows)/(2*len(rows))
    out['shot_bias5']=sum((r['sh5']-r['act_sh'][0])+(r['sa5']-r['act_sh'][1]) for r in rows)/(2*len(rows))
    return out

if __name__=='__main__':
    import sys
    R,rows=replay()
    s=summarize(rows); print(json.dumps(s,indent=1))
    print('coin-flip Brier = 0.2500, log loss = 0.6931')
