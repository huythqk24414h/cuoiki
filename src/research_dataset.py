"""Receive-time as-of grid. No lookahead, no missing=zero, no cross-session labels."""
import math
from datetime import datetime,timedelta
from decimal import Decimal
from src.research_core import displayed_depth,label_window

def build_grid(events,contract,protocol):
    if not set(protocol['symbols'])<=set(contract['symbols']):raise ValueError('Sample outside verified contract')
    if protocol.get('grid_seconds')!=1:raise ValueError('Only one-second grid validated')
    if not events:return []
    events=sorted(events,key=lambda e:(e['received_at'],e.get('sequence',0)))
    first=datetime.fromisoformat(events[0]['received_at']);last=datetime.fromisoformat(events[-1]['received_at'])
    clock=first.replace(microsecond=0)+timedelta(seconds=1);pointer=0;state={};flag=None;session=0;rows=[];history={}
    while clock<=last:
        while pointer<len(events) and datetime.fromisoformat(events[pointer]['received_at'])<=clock:
            e=events[pointer];pointer+=1;topic=e['topic'];d=e.get('data',{})
            if topic=='collector.connection':state={};flag=None;session+=1;continue
            if e.get('late') or e.get('future_source_time'):continue
            if topic=='market.flag' and d.get('b')=='HOSE':
                if d.get('f')!=(flag or {}).get('f'):session+=1
                flag=d;continue
            symbol=d.get('s')
            if symbol not in protocol['symbols']:continue
            state.setdefault(symbol,{})[topic.split('.')[0]]=e
        for symbol in protocol['symbols']:
            item=state.get(symbol,{});r={'timestamp':clock.isoformat(),'symbol':symbol,'session_id':str(clock.date())+':'+str(session),'valid':False}
            try:
                from src.ssi_stream import VN
                minute=clock.hour*60+clock.minute
                if clock.weekday()>4 or not (555<=minute<690 or 780<=minute<870):raise ValueError('Outside continuous HOSE window')
                if not flag or flag['f']!='LO':raise ValueError('Session unknown')
                ftime=datetime.strptime(flag['t'],'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN)
                quote=item['quote'];qt=datetime.strptime(quote['data']['t'],'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN)
                if ftime.date()!=clock.date() or ftime>qt or not 0<=(clock-qt).total_seconds()<=protocol['maximum_quote_age_seconds']:raise ValueError('Stale/session')
                metrics=displayed_depth(quote['data'].get('bids'),quote['data'].get('asks'),contract);r.update(metrics,valid=True)
                trade=item.get('trade');p=v=None
                if trade:
                    tt=datetime.strptime(trade['data']['t'],'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN)
                    if 0<=(clock-tt).total_seconds()<=protocol['maximum_quote_age_seconds']:
                        p=float(Decimal(str(trade['data']['p']))*Decimal(str(contract['price_scale'])))
                        v=float(Decimal(str(trade['data']['v']))*Decimal(str(contract['quantity_scale'])))
                previous=history.get((symbol,clock-timedelta(seconds=5)));base=history.get((symbol,clock-timedelta(seconds=60)))
                r.update(price=p,return_5s=None,matched_quantity_60s=None,bid_depth_change_5s=None,imbalance_change_5s=None,
                         slot_sin=math.sin(2*math.pi*(clock.hour*3600+clock.minute*60+clock.second)/86400),slot_cos=math.cos(2*math.pi*(clock.hour*3600+clock.minute*60+clock.second)/86400),cumulative_volume=v)
                if previous and previous.get('session_id')==r['session_id'] and previous['valid']:
                    if p and previous.get('price'):r['return_5s']=100*(p/previous['price']-1)
                    r['bid_depth_change_5s']=float(r['bid_depth'])-float(previous['bid_depth'])
                    if r['imbalance'] is not None and previous['imbalance'] is not None:r['imbalance_change_5s']=float(r['imbalance'])-float(previous['imbalance'])
                if base and base.get('session_id')==r['session_id'] and v is not None and base.get('cumulative_volume') is not None and v>=base['cumulative_volume']:r['matched_quantity_60s']=v-base['cumulative_volume']
                r['research_validated']=True
            except (ValueError,KeyError,TypeError,ArithmeticError):r['valid']=False
            history[(symbol,clock)]=r;rows.append(r)
        clock+=timedelta(seconds=1)
    return rows

def label_dataset(rows,protocol):
    import numpy as np
    days=sorted({r['timestamp'][:10] for r in rows});train=set(days[:int(len(days)*.6)])
    if len(days)<protocol['minimum_days_for_evaluation']:raise ValueError('Insufficient days')
    thresholds={}
    for symbol in protocol['symbols']:
        for slot in range(24):
            values=[float(r['bid_depth']) for r in rows if r['symbol']==symbol and r['valid'] and r['timestamp'][:10] in train and int(r['timestamp'][11:13])==slot]
            if len(values)>=protocol['minimum_baseline_observations']:thresholds[(symbol,slot)]=float(np.quantile(values,protocol['low_quantile']))
    out=[]
    for symbol in protocol['symbols']:
        group=[r for r in rows if r['symbol']==symbol]
        for i,r in enumerate(group):
            threshold=thresholds.get((symbol,int(r['timestamp'][11:13])))
            target=label_window(group,i,threshold,protocol['horizon_seconds'],protocol['minimum_low_duration_seconds']) if threshold is not None else None
            out.append({**r,'label':target,'label_end':(datetime.fromisoformat(r['timestamp'])+timedelta(seconds=protocol['horizon_seconds'])).isoformat(),'baseline_threshold':threshold})
    return out
