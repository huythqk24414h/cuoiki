"""Offline M0/M1/M2 logistic comparisons. Only consumes validated research-grid data."""
import numpy as np

FEATURES={
 'M0':['price','return_5s','matched_quantity_60s','slot_sin','slot_cos'],
 'M1':['price','return_5s','matched_quantity_60s','slot_sin','slot_cos','spread_bps','bid_depth','bid_depth_change_5s'],
 'M2':['price','return_5s','matched_quantity_60s','slot_sin','slot_cos','spread_bps','bid_depth','bid_depth_change_5s','imbalance','imbalance_change_5s']}

def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-35,35)))

def fit(x,y,penalty):
    mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale==0]=1
    a=np.column_stack([np.ones(len(x)),(x-mean)/scale]);w=np.zeros(a.shape[1])
    # Conservative Lipschitz step for stable batch optimization; intercept unpenalized.
    step=1/(np.linalg.norm(a,2)**2/(4*len(a))+penalty+1e-9)
    for _ in range(5000):
        gradient=a.T@(sigmoid(a@w)-y)/len(a)+penalty*np.r_[0,w[1:]]
        w-=step*gradient
        if np.max(np.abs(gradient))<1e-7:break
    else:raise ValueError('Logistic optimizer did not converge')
    return (mean,scale,w)

def predict(model,x):
    mean,scale,w=model
    return sigmoid(np.column_stack([np.ones(len(x)),(x-mean)/scale])@w)

def metrics(y,p):
    brier=float(np.mean((p-y)**2));bins=[]
    for lo in np.arange(0,1,.1):
        mask=(p>=lo)&(p<lo+.1)
        if mask.any():bins.append({'from':round(float(lo),1),'count':int(mask.sum()),'predicted':float(p[mask].mean()),'observed':float(y[mask].mean())})
    # Average precision with tied scores grouped, rather than an order-dependent ranking.
    positives=int(y.sum());ap=None
    if positives:
        ap=0.;previous_recall=0
        for score in sorted(set(p.tolist()),reverse=True):
            selected=p>=score;tp=float(y[selected].sum());recall=tp/positives
            ap+=(recall-previous_recall)*tp/int(selected.sum());previous_recall=recall
    return {'brier':brier,'average_precision':ap,'calibration':bins,'n':len(y),'positives':positives}

def evaluate(rows,seed=401101,bootstrap=500):
    """Same complete-case cohort and chronological day splits; no test-time tuning."""
    if not rows or any(r.get('research_validated') is not True for r in rows):raise ValueError('Validated research data required')
    rows=sorted(rows,key=lambda r:(r['timestamp'],r['symbol']))
    days=sorted({r['timestamp'][:10] for r in rows})
    if len(days)<10:raise ValueError('Too few days even for provisional evaluation; ten is not a power guarantee')
    tr=set(days[:int(len(days)*.6)]);va=set(days[int(len(days)*.6):int(len(days)*.8)]);te=set(days[int(len(days)*.8):])
    cohorts=[[r for r in rows if r['timestamp'][:10] in ds and r.get('label') in (0,1) and all(r.get(k) is not None and np.isfinite(float(r[k])) for k in FEATURES['M2']) and r.get('label_end','')[:10] in ds] for ds in (tr,va,te)]
    if any(len({r['label'] for r in group})<2 for group in cohorts):raise ValueError('Both outcomes required in each split')
    symbols=sorted({r['symbol'] for r in cohorts[0]})
    if any(r['symbol'] not in symbols for g in cohorts[1:] for r in g):raise ValueError('Unknown test symbol')
    results={};predictions={};y=[np.array([r['label'] for r in g],float) for g in cohorts]
    for name,fields in FEATURES.items():
        x=[np.array([[float(r[k]) for k in fields]+[float(r['symbol']==s) for s in symbols] for r in g]) for g in cohorts]
        choices=[]
        for penalty in (.001,.01,.1,1.):
            model=fit(x[0],y[0],penalty);score=metrics(y[1],predict(model,x[1]))['brier'];choices.append((score,penalty,model))
        _,penalty,model=min(choices,key=lambda v:v[0]);p=predict(model,x[2]);predictions[name]=p
        results[name]={'penalty':penalty,**metrics(y[2],p)}
    test_days=np.array([r['timestamp'][:10] for r in cohorts[2]]);unique=sorted(set(test_days));rng=np.random.default_rng(seed);deltas=[]
    for _ in range(bootstrap):
        ids=np.concatenate([np.flatnonzero(test_days==d) for d in rng.choice(unique,len(unique),replace=True)])
        deltas.append(float(np.mean((predictions['M2'][ids]-y[2][ids])**2-(predictions['M1'][ids]-y[2][ids])**2)))
    return {'models':results,'delta_brier_M2_minus_M1':results['M2']['brier']-results['M1']['brier'],
            'day_bootstrap_95_ci':np.quantile(deltas,[.025,.975]).tolist(),'test_days':unique,'seed':seed,
            'warning':'Probabilities not claimed calibrated merely because logistic is used. Event merging/false alarms per hour/lead-time and frozen pilot review still required.'}
