"""Local readonly SSI snapshot views; no provider calls on page/filter requests."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from urllib.parse import parse_qs

from src.eod_analytics import demo_payload, enrich_rows
from src.ssi_snapshot import validate_ssi_snapshot
from src.ssi_stream import LIVE
from src import universe, history_store
from src.eod_analytics import select_range, RANGES
from datetime import date

FOLDER=Path(__file__).resolve().parents[1]/'data/ssi_snapshots'


def market_status():
    # A saved successful probe is evidence, not an active stream or active token.
    report={}
    try:report=json.loads((FOLDER/'probe_report.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):pass
    if not isinstance(report,dict):report={}
    steps=[]
    allowed_steps={'auth','HOSE_list','ohlc_datetime','ohlc_date_fix','DATA_quote_websocket','probe_stopped'}
    allowed_states={'PASS','FAIL','BLOCKED','PARTIAL','CONNECTED_NO_TICKS','RECEIVED_QUOTES_UNVERIFIED'}
    for step in report.get('steps',[]) if isinstance(report,dict) else []:
        if isinstance(step,dict) and step.get('step') in allowed_steps:
            steps.append({'step':step['step'],'status':step.get('status') if step.get('status') in allowed_states else 'UNKNOWN'})
    state=LIVE.status()
    return {'source':'SSI FastConnect V3',
            'asof':state['last_event_at'][:10] if state['last_event_at'] else None,
            'snapshot_asof':history_store.info()['actual_last'],'updated_at':state['last_event_at'] or report.get('retrieved_at_utc'),
            'probe_at':report.get('retrieved_at_utc'),'unit':None,
            'historical_probe':steps,
            'reason':'Trạng thái DATA tách biệt snapshot EOD; chỉ gắn LIVE khi book đủ điều kiện.',
            'database':'disabled',**state}


def historical_alerts(snapshot):
    events=[];evaluated=0
    if snapshot['passed']:
        for symbol in snapshot['manifest']['symbols_loaded']:
            for row in enrich_rows([r for r in snapshot['rows'] if r['symbol']==symbol]):
                if row['relative_volume20'] is None:continue
                evaluated+=1
                ratio=Decimal(row['relative_volume20'])
                if ratio>=2:
                    events.append({'id':symbol+'-'+row['date'],'symbol':symbol,'timestamp':row['date'],
                                   'indicator':'relative_volume20','value':row['relative_volume20'],'unit':'lần',
                                   'threshold':'2','priority':'cao' if ratio>=3 else 'theo_doi',
                                   'formula':'Volume[t] / ((Volume[t-1] + ... + Volume[t-20]) / 20); loại phiên hiện tại',
                                   'baseline':row['volume_avg20_previous'],'volume':row['volume_shares'],
                                   'source':'SSI FastConnect V3','status':'historical_observation'})
    return {'source':'SSI FastConnect V3','asof':'2026-11-04','unit':'lần','updated_at':snapshot.get('manifest',{}).get('retrieved_at_utc'),
            'snapshot_sha256':snapshot.get('manifest',{}).get('file_sha256',{}).get('ohlcv_daily.csv'),
            'status':'evaluated' if evaluated else 'unavailable','evaluated_observations':evaluated,
            'rule':{'name':'RV20 ≥ 2','version':'1.0','min_prior_sessions':20,'threshold':'2',
                    'rationale':'Ngưỡng mô tả do người nghiên cứu chọn: khối lượng ít nhất gấp đôi TB20, không phải ngưỡng dự báo đã hiệu chỉnh.'},
            'rows':sorted(events,key=lambda r:(r['timestamp'],r['symbol']),reverse=True),
            'message':'Không có sự kiện theo quy tắc trong phạm vi đã kiểm tra.' if evaluated and not events else 'Chưa đánh giá' if not evaluated else 'Sự kiện mô tả lịch sử; không có thông báo đẩy.'}


def market_payload(route,query):
    if route=='/api/market/depth-warning':
        from src.depth_watch import payload
        return payload(query)
    if route=='/api/market/intraday':
        from src.intraday import payload
        return payload(query)
    if route=='/api/market/research':
        if query:return {'error':'No query supported'},400
        from src.research_core import audit_research
        return audit_research(),200

    if route=='/api/market/board':
        from src.quote_board import board_payload
        return board_payload(query)
    try:history=history_store.info();history_folder,quality=history_store.active()
    except (OSError,ValueError,KeyError):return {'error':'Historical revision failed integrity gate','status':'BLOCKED'},503
    snapshot=validate_ssi_snapshot(FOLDER)
    metadata=snapshot['manifest']
    base={'source':'SSI FastConnect V3','asof':history['actual_last'],'updated_at':metadata.get('retrieved_at_utc'),
          'status':snapshot['status'],'unit':metadata.get('units'),'available':snapshot['passed']}
    if route=='/api/market/meta' and quality is not None:
        if query:return {'error':'Unsupported query'},400
        manifest={'dataset_type':'ssi_history_revision','row_count':quality['rows'],'asof_date':quality['query_end'],'asof_timezone':'Asia/Ho_Chi_Minh','symbols_loaded':quality['symbols_loaded'],'retrieved_at_utc':quality['verified_at'],'adjustment_policy':'unknown','file_sha256':{},'upstream_sources':[{'id':'ssi_v3','name':'SSI FastConnect V3','source_url':'https://api.ssi.com.vn/api/v3/data/ohlc','documentation_url':'https://developers.ssi.com.vn/docs/sdk/python/service-classes'}]}
        return {**base,'available':True,'status':'VALIDATED_CONTENT_UNITS_UNVERIFIED','asof_date':quality['query_end'],'last_available_session':quality['last'],'timezone':'Asia/Ho_Chi_Minh','loaded_symbols':quality['symbols_loaded'],'coverage_by_symbol':quality['coverage_by_symbol'],'manifest':manifest,'historical_range':history,'issues':[]},200
    if route in ('/api/market/insights','/api/market/event-evidence'):
        try:
            params=parse_qs(query,strict_parsing=True,max_num_fields=3)
            if set(params)-{'symbol','date'} or any(len(v)!=1 for v in params.values()):raise ValueError('Invalid facts query')
            symbol=params.get('symbol',[''])[0];day=params.get('date',[history['actual_last']])[0];date.fromisoformat(day)
            rows=universe.symbol_rows(symbol) or [r for r in snapshot['rows'] if r['symbol']==symbol]
            enriched=enrich_rows([r for r in rows if r['date']<=day])
            try:indices=(history_store.index_data('VNINDEX') or universe.read_verified(universe.ROOT/'indices/VNINDEX.json'))['rows']
            except (OSError,ValueError):indices=[]
            from src.insights import fact_sheet
            facts=fact_sheet(enriched,indices)
            facts['context']=enriched[-30:];facts['event_date_exact']=bool(enriched and enriched[-1]['date']==day)
            return facts,200
        except (ValueError,OSError,KeyError) as error:return {'error':str(error)},400
    if route in ('/api/market/catalog','/api/market/coverage','/api/market/index','/api/market/series','/api/market/rankings'):
        try:
            params=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=10)
            if any(len(v)!=1 for v in params.values()):raise ValueError('Duplicate query')
            p={k:v[0] for k,v in params.items()}
            if set(p)-{'symbol','range','from','to','resolution','scope','type','metric'}:raise ValueError('Unsupported query')
            cat=universe.catalog()
            if route.endswith('/catalog'):return {**cat,'cutoff':history['actual_last'],'historical_range':history},200
            scope=p.get('scope','ALL');end=p.get('to') or history['actual_last'];date.fromisoformat(end)
            if route.endswith('/coverage'):return universe.coverage(end,scope),200
            if route.endswith('/index'):
                code=p.get('symbol','VNINDEX')
                codes={r.get('index') for r in cat['indexes']}
                if code not in codes:raise ValueError('Index outside SSI metadata')
                try:data=history_store.index_data(code) or universe.read_verified(universe.ROOT/'indices'/f'{code}.json')
                except FileNotFoundError:data={'code':code,'rows':[],'reason':'Chưa thu thập/kiểm chứng chuỗi indexSummary'}
                dated=[{**r,'date':str(r.get('tradingDate',''))[:10].replace('/','-')} for r in data['rows'] if str(r.get('tradingDate',''))[:10].replace('/','-')<=end]
                dated.sort(key=lambda r:r['date'])
                selected,_,_=select_range(dated,p.get('range','MAX'))
                data['rows']=[r for r in selected if r['date']>=p.get('from',history['start'])]
                return {**data,'coverage_gate':universe.coverage(end,scope)['gate'],'source':data.get('source','SSI indexSummary'),'cutoff':history['actual_last']},200
            if route.endswith('/rankings'):
                cov=universe.coverage(end,scope)
                return {**base,'rows':[],'coverage':cov,'available':False,'message':cov['gate']['reason']},200
            symbol=p.get('symbol','')
            valid={r['symbol'] for r in cat['securities']}|set(metadata.get('symbols_loaded',[]))
            if symbol not in valid:raise ValueError('Unknown SSI symbol')
            rows=universe.symbol_rows(symbol)
            if not rows:rows=[r for r in snapshot['rows'] if r['symbol']==symbol]
            enriched=enrich_rows(rows);range_id=p.get('range','1M')
            if range_id not in RANGES:raise ValueError('Invalid range')
            if p.get('from'):date.fromisoformat(p['from'])
            if p.get('from','0001-01-01')>end:raise ValueError('Reversed dates')
            # Range is anchored to chosen end; warmup is calculated BEFORE any slicing.
            selected,start,last=select_range([r for r in enriched if r['date']<=end],range_id)
            selected=[r for r in selected if r['date']>=p.get('from','0001-01-01')]
            daily_summary=selected[-1] if selected else None
            resolution=p.get('resolution','1D')
            selected=universe.resample(selected,resolution)
            try:acquisition=universe.read_verified((history_folder or universe.ROOT)/'checkpoint.json').get(symbol,{})
            except (OSError,ValueError):acquisition={}
            reason='Không có dữ liệu trong khoảng; chọn MAX hoặc mã khác.'
            if acquisition.get('state')=='ERROR':reason='Dữ liệu bị chặn: '+str(acquisition.get('validation_reason') or acquisition.get('code') or acquisition.get('error_type'))+'. Chọn mã khác; không tự sửa số liệu nguồn.'
            elif acquisition.get('state')=='NO_HISTORY':reason='SSI trả về lịch sử rỗng cho khoảng thu thập; không suy diễn là ngừng giao dịch. Chọn mã khác.'
            return {**base,'available':True,'rows':selected,'summary':daily_summary,'symbol':symbol,'range':range_id,'resolution':resolution,'last_available_session':last,'range_start':start,'message':None if selected else reason,'acquisition_state':acquisition.get('state'),'unit_status':'source native; expanded price units not independently verified','loaded_symbols':list(valid)},200
        except (ValueError,OSError,KeyError,TypeError) as error:return {'error':str(error)},400
    if route in ('/api/health','/api/market/status'):
        if query:return {'error':'Unsupported query'},400
        return {**market_status(),'snapshot_status':snapshot['status'],'snapshot_available':snapshot['passed']},200
    if route=='/api/market/book':
        params=parse_qs(query,keep_blank_values=True)
        if set(params)-{'symbol'} or any(len(v)!=1 for v in params.values()):return {'error':'Invalid book query'},400
        symbol=params.get('symbol',['SSI'])[0]
        if symbol not in {r['symbol'] for r in universe.catalog()['securities']}|set(metadata.get('symbols_loaded',[])):return {'error':'Unsupported symbol'},400
        if not LIVE.watch(symbol):return {**base,'available':False,'symbol':symbol,'status':'unsupported_topic','reason':'SSI REST có tên này nhưng DATA topic chỉ chấp nhận mã chữ/số. Chọn mã giao dịch hợp lệ.','bids':[],'asks':[]},200
        book=LIVE.book(symbol)
        return {**base,**book,'asof':book['event_time'][:10] if book.get('event_time') else None,
                'updated_at':book.get('received_at'),'snapshot_asof':history['actual_last']},200
    if route=='/api/market/alerts':
        if query:
            try:
                parsed=parse_qs(query,strict_parsing=True,max_num_fields=4)
                if set(parsed)-{'symbol','from','to'} or any(len(v)!=1 for v in parsed.values()):raise ValueError('Invalid alert query')
                p={k:v[0] for k,v in parsed.items()};symbol=p.get('symbol','')
                rows=universe.symbol_rows(symbol) or [r for r in snapshot['rows'] if r['symbol']==symbol]
                if symbol not in {r['symbol'] for r in universe.catalog()['securities']}|set(metadata.get('symbols_loaded',[])):raise ValueError('Unknown symbol')
                result=historical_alerts({'passed':True,'rows':rows,'manifest':{'symbols_loaded':[symbol]}})
                first=p.get('from') or history['start'];last=p.get('to') or history['actual_last'];date.fromisoformat(first);date.fromisoformat(last)
                result['rows']=[r for r in result['rows'] if first<=r['timestamp']<=last]
                result.update(scope=[symbol],scope_note='Chỉ mã được chọn; không phải cảnh báo toàn thị trường',snapshot_sha256=None)
                return result,200
            except (ValueError,OSError,KeyError) as error:return {'error':str(error)},400
        return historical_alerts(snapshot),200
    if route in ('/api/market/symbols','/api/market/provenance'):
        if query:return {'error':'Unsupported query'},400
        return {**base,'symbols':metadata.get('symbols_loaded',[]),'manifest':metadata,'issues':snapshot['issues']},200
    mapped=route.replace('/api/market/','/api/demo/')
    payload,code=demo_payload(mapped,query,FOLDER,snapshot_override=snapshot)
    return {**base,**payload},code
