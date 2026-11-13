"""Verified local universe, conservative point-in-time coverage and EOD resampling."""
import json, re, time
from pathlib import Path
from hashlib import sha256
from decimal import Decimal
from datetime import date, timedelta
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]/'data/ssi_universe_20261104'
_coverage_cache={}

def read_verified(path):
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=path.with_suffix('.sha256').read_text():raise ValueError('Checksum mismatch')
    return json.loads(raw)

def catalog():
    try:
        result=read_verified(ROOT/'catalog.json')
        try:result['index_memberships']=read_verified(ROOT/'memberships.json')['current_members']
        except (OSError,ValueError,KeyError):result['index_memberships']={}
        return result
    except (OSError,ValueError):return {'securities':[],'indexes':[],'historical_eligibility_verified':False}

def canonical_row(row,symbol,start='2026-01-01',end='2026-11-04'):
    if row.get('symbol')!=symbol:raise ValueError('Wrong symbol')
    day=str(row['tradingDate'])[:10].replace('/','-');date.fromisoformat(day)
    if not start<=day<=end:raise ValueError('Out of range')
    nums=[Decimal(str(row[k])) for k in ('open','high','low','close','volume')]
    o,h,l,c,v=nums
    if not all(n.is_finite() for n in nums) or min(o,h,l,c)<=0 or h<max(o,l,c) or l>min(o,h,c) or v<0 or v!=v.to_integral_value():raise ValueError('Invalid OHLCV')
    return {'symbol':symbol,'date':day,**{k+'_vnd':str(row[k]) for k in ('open','high','low','close')},'volume_shares':str(v),'turnover_vnd':'','source_value_vnd':str(row.get('value') or ''),'price_adjustment':'unknown','upstream_source':'ssi_v3','source_url':'https://api.ssi.com.vn/api/v3/data/ohlc','unit_status':'source_native_unverified'}

def symbol_rows(symbol):
    if not re.fullmatch('[A-Z0-9 _-]{1,40}',symbol):raise ValueError('Invalid symbol')
    from src import history_store
    extended=history_store.rows(symbol)
    if extended is not None:return extended
    try:return read_verified(ROOT/'symbols'/f'{symbol}.json')['rows']
    except FileNotFoundError:return []

def coverage_gate(n, denominator, verified=False, publish=.95, partial=.8):
    if not 0<=partial<=publish<=1:raise ValueError('Invalid thresholds')
    ratio=n/denominator if denominator else 0
    allowed=verified and denominator>0 and 0<=n<=denominator and ratio>=partial
    return {'n':n,'denominator':denominator,'ratio':ratio,'eligible_denominator_verified':verified,'publish_threshold':publish,'partial_threshold':partial,'allowed':allowed,'status':'FULL' if allowed and ratio>=publish else 'PARTIAL' if allowed else 'BLOCKED','reason':None if allowed else 'Không đủ độ bao phủ hoặc chưa xác minh danh mục đang giao dịch theo phiên.'}

def coverage(day='2026-11-04',scope='ALL'):
    from src import history_store
    folder,quality=history_store.active()
    if quality is not None and scope in quality['coverage_by_scope']:
        summary=quality['coverage_by_scope'][scope]
        return {**summary,'date':day,'scope':scope,'gate':coverage_gate(summary['by_session'].get(day,0),summary['catalog_count'],False),
                'denominator_note':'Current SSI directory only, not historical eligibility denominator. Validated immutable history revision.'}
    key=(day,scope)
    if key in _coverage_cache and time.monotonic()-_coverage_cache[key][0]<20:return _coverage_cache[key][1]
    cat=catalog();index_members=set(cat.get('index_memberships',{}).get(scope.removeprefix('INDEX:'),[])) if scope.startswith('INDEX:') else set()
    members=[s for s in cat['securities'] if scope=='ALL' or s.get('board')==scope or s['symbol'] in index_members]
    seen={s['symbol'] for s in members};n=0;byday=Counter();success=empty=errors=0;first=None;last=None
    for symbol in seen:
        try:
            rows=symbol_rows(symbol)
            if not rows:empty+=1;continue
            success+=1
            for r in rows:byday[r['date']]+=1
            n+=any(r['date']==day for r in rows)
            first=min(first or rows[0]['date'],rows[0]['date']);last=max(last or rows[-1]['date'],rows[-1]['date'])
        except (OSError,ValueError,KeyError):errors+=1
    # Current directory membership is NOT a historical denominator; never turn it into one.
    gate=coverage_gate(n,len(seen),False)
    try:states=read_verified(ROOT/'checkpoint.json')
    except (OSError,ValueError):states={}
    result={'date':day,'scope':scope,'catalog_count':len(seen),'loaded_symbols':success,'missing_or_empty':empty,'invalid_symbols':errors,'processing_states':dict(Counter(states.get(s,{}).get('state','PENDING') for s in seen)),'first':first,'last':last,'sessions':len(byday),'by_session':dict(sorted(byday.items())),'gate':gate,'denominator_note':'M là danh mục hiện tại, chỉ dùng kiểm toán; chưa phải mẫu số đang niêm yết/giao dịch của phiên t.','by_board_type':dict(Counter(str(s.get('board'))+':'+str(s.get('stockType') or 'unknown') for s in members))}
    _coverage_cache[key]=(time.monotonic(),result)
    return result

def resample(rows,resolution):
    if resolution=='1D':return rows
    if resolution not in ('1W','1M'):raise ValueError('Intraday unavailable: only daily source stored')
    groups={}
    for r in rows:
        d=date.fromisoformat(r['date']);key=d.replace(day=1) if resolution=='1M' else d-timedelta(days=d.weekday())
        groups.setdefault(str(key),[]).append(r)
    out=[]
    for rs in groups.values():
        out.append({**rs[-1],'period_start':rs[0]['date'],'open_vnd':rs[0]['open_vnd'],'high_vnd':str(max(Decimal(r['high_vnd']) for r in rs)),'low_vnd':str(min(Decimal(r['low_vnd']) for r in rs)),'volume_shares':str(sum(Decimal(r['volume_shares']) for r in rs)),'source_value_vnd':'','resolution':resolution,'partial_period_possible':True})
    return out
