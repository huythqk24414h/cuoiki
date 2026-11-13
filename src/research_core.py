"""Research contracts, immutable receive-order replay and censored 60s labels.

EOD is never an input substitute. Fixtures for tests are never published as evidence.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

ROOT=Path(__file__).resolve().parents[1]

def load_contract(path=None):
    p=Path(path or ROOT/'config/ssi_unit_contract.json')
    c=json.loads(p.read_text(encoding='utf-8'))
    if c.get('status')!='VERIFIED' or not c.get('reviewer') or not c.get('verified_at') or c.get('board')!='HOSE' or not c.get('symbols') or c.get('quote_is_full_snapshot') is not True:
        raise ValueError('Unit/schema contract not independently verified')
    for name in ('price_scale','quantity_scale'):
        n=Decimal(str(c.get(name)))
        if not n.is_finite() or n<=0:raise ValueError('Invalid unit conversion')
    if not c.get('evidence'):raise ValueError('Missing evidence')
    for e in c['evidence']:
        source=(ROOT/e['file']).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file() or sha256(source.read_bytes()).hexdigest()!=e.get('sha256'):raise ValueError('Evidence hash/path mismatch')
    return c

def displayed_depth(bids,asks,contract):
    """Research measure includes verified absent levels; executable spread may be absent."""
    scale=Decimal(str(contract['price_scale']));quantity_scale=Decimal(str(contract['quantity_scale']))
    totals=[];best=[]
    for side,entries in (('bids',bids),('asks',asks)):
        if not isinstance(entries,list) or len(entries)<3:raise ValueError('Incomplete three-level snapshot')
        positive=[];absent=False;depth=Decimal(0)
        for entry in entries[:3]:
            if not isinstance(entry,(list,tuple)) or len(entry)!=2:raise ValueError('Malformed level')
            p,q=[Decimal(str(x)) for x in entry]
            if not p.is_finite() or not q.is_finite() or min(p,q)<0:raise ValueError('Invalid level')
            if p==q==0:
                if not contract.get('zero_pair_means_absent_level'):raise ValueError('Zero semantics unverified')
                absent=True;continue
            if p<=0 or q<=0 or q!=q.to_integral_value() or absent:raise ValueError('Invalid/gapped levels')
            positive.append(p*scale);depth+=p*scale*q*quantity_scale
        if positive!=sorted(set(positive),reverse=side=='bids'):raise ValueError('Wrong level order')
        totals.append(depth);best.append(positive[0] if positive else None)
    bid,ask=totals;b,a=best
    if b is not None and a is not None and b>=a:raise ValueError('Crossed/locked')
    return {'bid_depth':str(bid),'ask_depth':str(ask),'imbalance':str((bid-ask)/(bid+ask)) if bid+ask>0 else None,
            'spread_bps':str((a-b)/((a+b)/2)*10000) if b is not None and a is not None else None,
            'empty_bid':bid==0,'empty_ask':ask==0}

def replay(paths):
    """Arrival order, stable ties by explicit sequence then file/line; flag late source events."""
    records=[];manifest={}
    for path in sorted(map(Path,paths)):
        blob=path.read_bytes();manifest[str(path.name)]=sha256(blob).hexdigest()
        for line_no,line in enumerate(blob.decode('utf-8').splitlines(),1):
            if not line.strip():continue
            r=json.loads(line);received=datetime.fromisoformat(r['received_at'])
            if received.utcoffset() is None:raise ValueError('Naive receive time')
            records.append((received,r.get('sequence',0),str(path),line_no,r))
    records.sort(key=lambda r:r[:4]);last={};out=[]
    for received,seq,path,line,r in records:
        topic=r['topic'];data=r.get('data',{});key=(topic,data.get('s',data.get('b')))
        try:event=datetime.strptime(data['t'],'%Y/%m/%d %H:%M:%S').replace(tzinfo=received.tzinfo)
        except (KeyError,TypeError,ValueError):event=None
        # SSI source timestamp is explicitly Vietnam wall time, independent of stored receive offset.
        if event is not None:
            from src.ssi_stream import VN
            event=event.replace(tzinfo=VN)
        late=bool(event and key in last and event<last[key])
        future=bool(event and event>received+timedelta(seconds=5))
        if event is not None and not late:last[key]=event
        out.append({**r,'file':Path(path).name,'line':line,'late':late,'future_source_time':future})
    return out,{'raw_sha256':manifest,'events':len(out),'order':'received_at, sequence, filename, line','late_events':sum(r['late'] for r in out)}

def label_window(rows,index,threshold,horizon=60,duration=15,step=1):
    """Rows are validated receive-time grid states; never fill missing future coverage as 0."""
    t=rows[index];start=datetime.fromisoformat(t['timestamp']);limit=start+timedelta(seconds=horizon)
    if not t.get('valid') or Decimal(str(t['bid_depth']))<=Decimal(str(threshold)):return None
    future=rows[index+1:index+1+horizon//step]
    if len(future)!=horizon//step:return None
    previous=start;low_start=None;found=False
    for r in future:
        now=datetime.fromisoformat(r['timestamp'])
        if not r.get('valid') or r.get('session_id')!=t.get('session_id') or r.get('symbol')!=t.get('symbol') or now-previous!=timedelta(seconds=step) or now>limit:return None
        if Decimal(str(r['bid_depth']))<=Decimal(str(threshold)):
            if low_start is None:low_start=now
            if (now-low_start).total_seconds()>=duration:found=True
        else:low_start=None
        previous=now
    return int(found)

def audit_research():
    paths=list((ROOT/'data/live_snapshots').glob('*.jsonl'));events,manifest=replay(paths)
    counts={};days=set();symbols=set()
    for r in events:
        kind=r['topic'].split('.')[0];counts[kind]=counts.get(kind,0)+1
        days.add(r['received_at'][:10]);s=r.get('data',{}).get('s')
        if s:symbols.add(s)
    blockers=[]
    try:load_contract()
    except (OSError,ValueError,KeyError,ArithmeticError) as e:blockers.append('UNIT_SCHEMA_CONTRACT_UNVERIFIED')
    protocol=json.loads((ROOT/'config/research_protocol.json').read_text())
    if not protocol['locked'] or not protocol['symbols']:blockers.append('RESEARCH_SAMPLE_PROTOCOL_NOT_LOCKED')
    if counts.get('trade',0)==0:blockers.append('NO_RECORDED_TRADE_FOR_M0')
    if len(days)<protocol['minimum_days_for_evaluation']:blockers.append('INSUFFICIENT_INTRADAY_DAYS')
    return {'status':'BLOCKED' if blockers else 'READY_FOR_DATA_VALIDATION','blockers':blockers,'counts':counts,'recorded_days':sorted(days),'symbols':sorted(symbols),'manifest':manifest,
            'h1':'NOT_TESTED','prediction_available':False,'note':'RV20 events are descriptive EOD; no H1 result or probability is generated.'}
