"""SSI DATA quote-board projection. No EOD filler, price scaling or inferred returns."""
import copy
from datetime import datetime
from decimal import Decimal,InvalidOperation
import re
import unicodedata
from urllib.parse import parse_qs
from src import universe
from src.ssi_stream import LIVE,VN

def numeric(value, price=False):
    if price and value in ('ATO','ATC'):return value
    if value is None or isinstance(value,bool):return None
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):return None
    if not n.is_finite() or n<0 or (price and n==0):return None
    return str(value)

def search_text(value):
    text=unicodedata.normalize('NFD',str(value).casefold().replace('đ','d'))
    return ''.join(c for c in text if unicodedata.category(c)!='Mn')

def freshness(record, now):
    if not record:return {'status':'waiting','age_seconds':None}
    try:
        event=datetime.fromisoformat(record['event_time']);received=datetime.fromisoformat(record['received_at'])
        age=(now-event).total_seconds();receive_age=(now-received).total_seconds()
        if event>now or received>now or received<event:return {'status':'invalid_time','age_seconds':age}
        return {'status':'receiving' if age<=30 and receive_age<=30 else 'stale','age_seconds':round(age,3)}
    except (ValueError,KeyError,TypeError):return {'status':'invalid_time','age_seconds':None}

def board_row(meta, quote, trade, master, flag, now, connection, contract=None):
    qstate=freshness(quote,now);tstate=freshness(trade,now)
    known_times=[r['event_time'] for r in (quote,trade) if r]
    asof=max(known_times,default=None)
    # Master prices only accompany data from the same source trading date.
    md=master.get('data',{}) if master and asof and master['event_time'][:10]==asof[:10] else {}
    def levels(side):
        rows=(quote or {}).get(side,[])
        return [{'price':numeric(r[0],True),'quantity':numeric(r[1])} if isinstance(r,(list,tuple)) and len(r)==2 else {'price':None,'quantity':None} for r in (rows+[None,None,None])[:3]]
    td=(trade or {}).get('data',{})
    stream_open=connection not in ('disconnected','reconnecting','connecting')
    status=qstate['status'] if stream_open else 'offline' if quote or trade else 'waiting'
    if quote is None and trade is not None and stream_open:status=tstate['status']
    same_flag=flag if flag and asof and flag['event_time'][:10]==asof[:10] and flag['event_time']<=asof else None
    result={'symbol':meta['symbol'],'name':meta.get('symbolNameVi') or meta.get('symbolNameEn') or '',
            'board':meta.get('board'),'stock_type':meta.get('stockType') or 'unknown',
            'topic_supported':bool(re.fullmatch('[A-Z0-9]+',meta['symbol'])),
            'ceiling':numeric(md.get('ce'),True),'floor':numeric(md.get('fl'),True),'reference':numeric(md.get('ref'),True),
            'bids':levels('bids'),'asks':levels('asks'),
            'last_price':numeric(td.get('p'),True),'last_quantity':numeric(td.get('q')),'total_volume':numeric(td.get('v')),
            'high':numeric(td.get('h'),True),'low':numeric(td.get('l'),True),
            'foreign_buy':None,'foreign_sell':None,'foreign_room':None,
            'change':None,'change_pct':None,'change_reason':'Chưa xác minh đơn vị tương thích giữa trade và giá tham chiếu; không suy diễn +/- hoặc %.',
            'status':status,'quote_status':qstate['status'],'trade_status':tstate['status'],
            'quote_time':(quote or {}).get('event_time'),'trade_time':(trade or {}).get('event_time'),
            'master_time':(master or {}).get('event_time') if md else None,
            'received_at':max((r['received_at'] for r in (quote,trade) if r),default=None),
            'session':same_flag['flag'] if same_flag else None,'session_time':same_flag['event_time'] if same_flag else None,
            'age_seconds':qstate['age_seconds'],'source':'SSI DATA','unit_status':'source_native_unverified',
            'reason':'Mã metadata không hợp lệ với topic DATA.' if not re.fullmatch('[A-Z0-9]+',meta['symbol']) else None}
    # Color comparisons need verified reference and trade/quote conversions, not price magnitude.
    result['colors']={};c=contract or {}
    if c.get('status')=='VERIFIED' and meta['symbol'] in c.get('symbols',[]) and md:
        def classified(value,scale,source_time):
            try:
                if not source_time or source_time[:10]!=master['event_time'][:10]:return None
                price=Decimal(str(value))*Decimal(str(scale));refscale=Decimal(str(c['reference_price_scale']))
                ref=Decimal(str(md['ref']))*refscale;ceil=Decimal(str(md['ce']))*refscale;floor=Decimal(str(md['fl']))*refscale
                if not all(v.is_finite() and v>0 for v in (price,ref,ceil,floor)):return None
                return 'market-ceiling' if price==ceil else 'market-floor' if price==floor else 'market-reference' if price==ref else 'market-up' if price>ref else 'market-down'
            except (KeyError,TypeError,ValueError,InvalidOperation):return None
        result['colors']['bids']=[classified(r['price'],c.get('price_scale'),result['quote_time']) for r in result['bids']]
        result['colors']['asks']=[classified(r['price'],c.get('price_scale'),result['quote_time']) for r in result['asks']]
        result['colors']['last']=classified(result['last_price'],c.get('trade_price_scale'),result['trade_time'])
    return result

def board_payload(query, live=LIVE):
    try:
        parsed=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=8)
        if set(parsed)-{'scope','search','page','size','sort','direction','type','mode'} or any(len(v)!=1 for v in parsed.values()):raise ValueError('Invalid board query')
        p={k:v[0] for k,v in parsed.items()};scope=p.get('scope','INDEX:VN30');search=p.get('search','')
        mode=p.get('mode','DATA')
        if mode not in ('DATA','EOD'):raise ValueError('Invalid source mode')
        page=int(p.get('page','1'));size=int(p.get('size','30'));sort=p.get('sort','symbol');direction=p.get('direction','asc')
        if (scope not in ('ALL','HOSE','HNX','UPCOM') and not scope.startswith('INDEX:')) or page<1 or not 1<=size<=100 or len(search)>120 or sort not in ('symbol','board','name') or direction not in ('asc','desc'):raise ValueError('Unsupported board filter')
        directory=universe.catalog();needle=search_text(search)
        index_members=directory.get('index_memberships',{}).get(scope.removeprefix('INDEX:'))
        if scope.startswith('INDEX:') and index_members is None:raise ValueError('Chưa có thành phần chỉ số SSI đã kiểm chứng')
        members=[r for r in directory['securities'] if (scope=='ALL' or r.get('board')==scope or (index_members is not None and r['symbol'] in index_members)) and (not needle or needle in search_text(' '.join(str(r.get(k) or '') for k in ('symbol','symbolNameVi','symbolNameEn')))) and (not p.get('type') or r.get('stockType')==p['type'])]
        field='symbolNameVi' if sort=='name' else sort
        members.sort(key=lambda r:(str(r.get(field) or ''),r['symbol']),reverse=direction=='desc')
        total=len(members);pages=max(1,(total+size-1)//size);page=min(page,pages)
        visible=members[(page-1)*size:page*size]
        live.watch_board([r['symbol'] for r in visible])
        with live.lock:
            quotes=copy.deepcopy(live.quotes);trades=copy.deepcopy(live.trades);masters=copy.deepcopy(live.masters);flags=copy.deepcopy(live.flags);connection=live.state;contract=copy.deepcopy(getattr(live,'unit_contract',None))
        now=datetime.now(VN)
        rows=[board_row(r,quotes.get(r['symbol']),trades.get(r['symbol']),masters.get(r['symbol']),flags.get(r.get('board')),now,connection,contract) for r in visible]
        if mode=='EOD':
            rows=[]
            for meta in visible:
                row=board_row(meta,None,None,None,None,now,'disconnected')
                try:stored=universe.symbol_rows(meta['symbol'])
                except (OSError,ValueError,KeyError):stored=[]
                if stored:
                    last=stored[-1]
                    row.update(last_price=last['close_vnd'],last_quantity=None,total_volume=last['volume_shares'],high=last['high_vnd'],low=last['low_vnd'],status='eod',source='SSI Historical EOD',trade_status='eod',trade_time=last['date'],received_at=None,session='EOD '+last['date'])
                rows.append(row)
        return {'source':'SSI Historical EOD' if mode=='EOD' else 'SSI DATA WebSocket','mode':'EOD' if mode=='EOD' else 'STREAM_SOURCE_NATIVE','rows':rows,'total':total,'catalog_total':len(directory['securities']),
                'page':page,'pages':pages,'size':size,'scope':scope,'updated_at':now.isoformat(),
                'received_rows':sum(r['quote_time'] is not None or r['trade_time'] is not None for r in rows),
                'fresh_rows':sum(r['status']=='receiving' for r in rows),'connection':connection,
                'view_note':'Chỉ đăng ký các mã trên trang đang xem và mã sổ lệnh đang chọn; các trang còn lại vẫn chọn được. Không phải thống kê toàn thị trường.',
                'units_note':'Giá/KL nguyên đơn vị SSI gửi; chưa quy đổi nghìn đồng hay lô. Dấu — là thiếu dữ liệu; không dùng EOD để lấp bảng giá. +/- và % bị vô hiệu hóa đến khi xác minh đơn vị.'},200
    except (ValueError,TypeError,KeyError,OSError) as error:return {'error':str(error)},400
