"""Read-only intraday cache. Shares the DATA auth session; never builds minutes from EOD."""
import json,re,threading,time
from pathlib import Path
from datetime import datetime,timedelta
from decimal import Decimal
from urllib.parse import parse_qs
from src.ssi_stream import LIVE,VN
from src.ssi_client import safe_error
from scripts.expand_ssi_market import save,read

ROOT=Path(__file__).resolve().parents[1]/'data/intraday'
_lock=threading.Lock();_pending=set();_attempt={};_errors={}

def normalize(raw,symbol):
    out={}
    for r in raw:
        if r.get('symbol')!=symbol:raise ValueError('Wrong symbol')
        dt=datetime.fromisoformat(str(r['tradingDate']).replace('/','-'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=VN)
        dt=dt.astimezone(VN)
        values=[Decimal(str(r[k])) for k in ('open','high','low','close','volume')]
        o,h,l,c,v=values
        if not all(x.is_finite() for x in values) or min(o,h,l,c)<=0 or h<max(o,c,l) or l>min(o,c,h) or v<0:raise ValueError('Invalid intraday OHLC')
        row=dict(timestamp=dt.isoformat(),open=str(o),high=str(h),low=str(l),close=str(c),volume=str(v))
        key=row['timestamp']
        if key in out and out[key]!=row:raise ValueError('Conflicting intraday duplicate')
        out[key]=row
    return sorted(out.values(),key=lambda r:r['timestamp'])

def aggregate(rows,resolution):
    minutes={'15m':15,'1h':60,'4h':240}[resolution];groups={}
    for r in rows:
        dt=datetime.fromisoformat(r['timestamp']);minute=dt.hour*60+dt.minute
        # Independent morning/afternoon buckets: no candle bridges lunch or dates.
        anchor=555 if minute<690 else 780
        if dt.weekday()>4 or not (555<=minute<690 or 780<=minute<870):continue
        bucket=anchor+(minute-anchor)//minutes*minutes
        key=dt.replace(hour=bucket//60,minute=bucket%60,second=0,microsecond=0).isoformat()
        groups.setdefault(key,[]).append(r)
    return [dict(timestamp=k,open=g[0]['open'],close=g[-1]['close'],high=str(max(Decimal(x['high']) for x in g)),low=str(min(Decimal(x['low']) for x in g)),volume=str(sum(Decimal(x['volume']) for x in g)),observed_minutes=len(g),nominal_minutes=minutes,partial=len(g)<minutes) for k,g in sorted(groups.items())]

def refresh(symbol):
    try:
        client=getattr(LIVE,'data_client',None)
        if client is None:raise ValueError('DATA_SESSION_NOT_AVAILABLE')
        now=datetime.now(VN);start=now-timedelta(days=3);raw=[];pages=[]
        for page in range(1,11):
            params={'symbol':symbol,'timeFrame':'1m','from':start.strftime('%Y/%m/%d 00:00:00'),'to':now.strftime('%Y/%m/%d %H:%M:%S'),'pageIndex':page,'pageSize':1000}
            response=client.get('/api/v3/data/ohlc',params);data=response.get('data',[])
            if not isinstance(data,list):raise ValueError('Invalid response')
            pages.append({'params':params,'response':response});raw.extend(data)
            if len(data)<1000:break
        else:raise ValueError('Pagination incomplete')
        rows=normalize(raw,symbol)
        save(ROOT/(symbol+'.json'),{'source':'SSI 1m OHLC','retrieved_at':now.isoformat(),'rows':rows,'raw_pages':pages,'units':'source native; adjustment unknown'})
        _errors.pop(symbol,None)
    except Exception as e:_errors[symbol]=safe_error(e) if not isinstance(e,ValueError) else {'reason':str(e)}
    finally:
        with _lock:_pending.discard(symbol)

def payload(query):
    try:
        p=parse_qs(query,strict_parsing=True)
        if set(p)-{'symbol','resolution'} or any(len(v)!=1 for v in p.values()):raise ValueError('Invalid query')
        symbol=p.get('symbol',['SSI'])[0];res=p.get('resolution',['15m'])[0]
        from src.universe import catalog
        if not re.fullmatch('[A-Z0-9]{1,20}',symbol) or symbol not in {r['symbol'] for r in catalog()['securities'] if r.get('board')=='HOSE'}:raise ValueError('Select a HOSE symbol')
        if res not in ('15m','1h','4h'):raise ValueError('Unsupported intraday resolution')
        with _lock:
            if symbol not in _pending and time.monotonic()-_attempt.get(symbol,-1000)>=60:
                _pending.add(symbol);_attempt[symbol]=time.monotonic();threading.Thread(target=refresh,args=(symbol,),daemon=True).start()
        try:data=read(ROOT/(symbol+'.json'))
        except FileNotFoundError:data={'rows':[],'retrieved_at':None}
        return {'source':'SSI 1m OHLC','symbol':symbol,'resolution':res,'rows':aggregate(data['rows'],res),'retrieved_at':data['retrieved_at'],'last_source_time':data['rows'][-1]['timestamp'] if data['rows'] else None,'refreshing':symbol in _pending,'error':_errors.get(symbol),'status':'INTRADAY_CACHED' if data['rows'] else 'WAITING_FOR_SSI','refresh_seconds':60,'note':'Nến tổng hợp từ phút thật, tách nghỉ trưa. 4H có thể thiếu kỳ. Không phải đo độ sâu hoặc dự báo 60 giây.'},200
    except (ValueError,KeyError,OSError) as e:return {'error':str(e)},400
