"""One-second verified depth sampling and retrospective 60s outcome, never a forecast."""
import threading,time,json,re
from collections import deque
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from src.ssi_stream import LIVE,VN
from src.research_core import load_contract,displayed_depth,label_window

_lock=threading.RLock();_thread=None;_lease={};_rows={};_status={}

def outcome(rows):
    if len(rows)<161:return {'state':'WARMUP','reason':'Cần 100 quan sát cơ sở và cửa sổ tương lai đủ 60 giây.'}
    index=len(rows)-61;anchor=rows[index]
    base=[Decimal(str(r['bid_depth'])) for r in rows[:index] if r['valid'] and r['session_id']==anchor['session_id']]
    if len(base)<100:return {'state':'WARMUP','reason':'Thiếu cơ sở hợp lệ trong cùng phiên.'}
    base.sort();threshold=base[int((len(base)-1)*.1)]
    label=label_window(rows,index,threshold)
    return {'state':'CENSORED' if label is None else 'OBSERVED_LOW_DEPTH' if label else 'NO_OBSERVED_EVENT','anchor_time':anchor['timestamp'],'observed_until':rows[-1]['timestamp'],'threshold':str(threshold),'label':label,'forecast':False,'horizon_seconds':60,'minimum_duration_seconds':15,'baseline_n':len(base),'method':'Phân vị quá khứ thực nghiệm 10%; quy tắc mô tả chưa hiệu chỉnh. Không phải xác suất M2.'}

def sample(symbol,now):
    timestamp=now.replace(microsecond=0).isoformat();session=now.date().isoformat()+('AM' if now.hour<12 else 'PM')
    row={'timestamp':timestamp,'symbol':symbol,'session_id':session,'valid':False}
    try:
        contract=load_contract()
        if symbol not in contract['symbols']:raise ValueError('Mã chưa thuộc quy ước đã xác minh')
        with LIVE.lock:
            c=LIVE.quotes.get(symbol);flag=LIVE.flag;ft=LIVE.flag_time
            if c is None:raise ValueError('Chưa nhận quote')
            minute=now.hour*60+now.minute
            if now.weekday()>4 or not (555<=minute<690 or 780<=minute<870) or flag!='LO' or not ft or ft.date()!=now.date():raise ValueError('Ngoài phiên liên tục hoặc cờ phiên chưa xác minh')
            event=datetime.fromisoformat(c['event_time']);received=datetime.fromisoformat(c['received_at'])
            if ft>event or not 0<=(now-event).total_seconds()<=5 or not 0<=(now-received).total_seconds()<=5:raise ValueError('Quote cũ hoặc thời gian không hợp lệ')
            result=displayed_depth(c['bids'],c['asks'],contract)
        row.update(result,valid=True);_status[symbol]=None
    except FileNotFoundError:_status[symbol]='Chưa có quy ước đơn vị và cấu trúc SSI được xác minh. Chưa tính độ sâu.'
    except (OSError,ValueError,KeyError,TypeError) as e:_status[symbol]=str(e)
    return row

def loop():
    while True:
        time.sleep(max(.01,1-time.time()%1))
        with _lock:
            symbols=[s for s,t in _lease.items() if t>time.monotonic()]
            if not symbols:return
            now=datetime.now(VN)
            for s in symbols:
                row=sample(s,now);_rows.setdefault(s,deque(maxlen=3600)).append(row)
                folder=Path(__file__).resolve().parents[1]/'data/depth_watch';folder.mkdir(exist_ok=True)
                try:
                    with (folder/(now.date().isoformat()+'.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
                except OSError:_status[s]='Không lưu được nhật ký; chưa xác nhận bằng chứng'

def payload(query):
    global _thread
    p=parse_qs(query);s=p.get('symbol',['SSI'])[0]
    if set(p)-{'symbol'} or len(p.get('symbol',[]))>1 or not re.fullmatch('[A-Z0-9]{1,20}',s):return {'error':'Invalid symbol'},400
    from src.universe import catalog
    if s not in {r['symbol'] for r in catalog()['securities'] if r.get('board')=='HOSE'}:return {'error':'Chỉ hỗ trợ HOSE'},400
    with _lock:
        now=time.monotonic();active=[k for k,v in _lease.items() if v>now]
        if s not in active and len(active)>=10:return {'error':'Tối đa 10 mã đang theo dõi'},429
        LIVE.watch(s);_lease[s]=now+30
        if not _thread or not _thread.is_alive():_thread=threading.Thread(target=loop,daemon=True);_thread.start()
        rows=list(_rows.get(s,[]));result=outcome(rows)
        if _status.get(s):result={'state':'BLOCKED','reason':_status[s]}
        return {'symbol':s,**result,'samples':len(rows),'valid_samples':sum(r['valid'] for r in rows),'latest':rows[-1] if rows else None,'prediction_available':False,'h1':'NOT_TESTED'},200
