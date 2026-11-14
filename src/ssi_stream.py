"""In-memory DATA-only subscription. Fail closed on partial/stale/unverified books."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, localcontext, InvalidOperation
import threading
import os
from hashlib import sha256
import json
import re
import queue
import time
from pathlib import Path

from src.ssi_client import SSIReadonly, credentials, sdk, safe_error

VN=timezone(timedelta(hours=7))
def stream_symbols():
    from src.universe import catalog
    # Explicit opt-in watchlist; otherwise current SSI metadata, never a hardcoded sample.
    configured=os.environ.get('SSI_STREAM_SYMBOLS','').split(',')
    valid={r['symbol'] for r in catalog()['securities']}
    # REST directory includes index aliases containing spaces; DATA topics cannot accept them.
    return sorted(s for s in valid & set(configured) if re.fullmatch('[A-Z0-9]+',s)) if any(configured) else []


def book_metrics(candidate, scale, session, now):
    if scale not in (Decimal(1),Decimal(1000)):
        raise ValueError('Đơn vị giá quote chưa được xác minh; không tự suy đoán từ độ lớn giá.')
    event=datetime.fromisoformat(candidate['event_time']);received=datetime.fromisoformat(candidate['received_at'])
    local_time=event.astimezone(VN)
    minute=local_time.hour*60+local_time.minute
    if local_time.weekday()>4 or not (555<=minute<690 or 780<=minute<870):
        raise ValueError('Quote ngoài giờ phiên liên tục HOSE.')
    if session!='LO' or received<event or event>now+timedelta(seconds=5) or received>now+timedelta(seconds=5):
        raise ValueError('Chưa xác nhận phiên liên tục hoặc thời gian không hợp lệ.')
    if (now-event).total_seconds()>30 or (now-received).total_seconds()>30:
        raise ValueError('Quote đã cũ quá 30 giây.')
    levels=[]
    for side in ['bids','asks']:
        entries=candidate[side]
        if len(entries)<3:raise ValueError('Thiếu snapshot hai phía đủ ba mức; không ghép delta chưa xác minh.')
        out=[]
        for price,quantity in entries[:3]:
            try:p,q=Decimal(str(price))*scale,Decimal(str(quantity))
            except (InvalidOperation,TypeError):raise ValueError('Quote chứa trường số không hợp lệ.')
            if not p.is_finite() or not q.is_finite() or not 0<p<=Decimal('1e15') or not 0<q<=Decimal('1e15') or q!=q.to_integral_value():
                raise ValueError('Giá/khối lượng quote không hợp lệ.')
            out.append({'price':str(p),'quantity':str(q)})
        prices=[Decimal(row['price']) for row in out]
        if len(set(prices))!=3 or prices!=sorted(prices,reverse=side=='bids'):raise ValueError('Thứ tự mức giá không hợp lệ.')
        levels.append(out)
    bids,asks=levels
    if Decimal(bids[0]['price'])>=Decimal(asks[0]['price']):raise ValueError('Sổ lệnh khóa hoặc chéo.')
    with localcontext() as ctx:
        ctx.prec=64
        bid=sum(Decimal(r['price'])*Decimal(r['quantity']) for r in bids)
        ask=sum(Decimal(r['price'])*Decimal(r['quantity']) for r in asks)
        mid=(Decimal(bids[0]['price'])+Decimal(asks[0]['price']))/2
        return {'bid_depth_vnd':str(bid),'ask_depth_vnd':str(ask),'total_depth_vnd':str(bid+ask),
                'engine_version':'ssi-book-0.1.0',
                'input_hash':sha256(json.dumps({'symbol':candidate['symbol'],'event_time':candidate['event_time'],
                                               'received_at':candidate['received_at'],'bids':bids,'asks':asks},
                                              sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'spread_vnd_per_share':str(Decimal(asks[0]['price'])-Decimal(bids[0]['price'])),
                'bid_displayed_shares':str(sum(Decimal(row['quantity']) for row in bids)),
                'ask_displayed_shares':str(sum(Decimal(row['quantity']) for row in asks)),
                'spread_bps':str((Decimal(asks[0]['price'])-Decimal(bids[0]['price']))/mid*10000),
                'imbalance':str((bid-ask)/(bid+ask)),'bids':bids,'asks':asks}


class DataStream:
    def __init__(self, research=False):
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.ws=None
        self.state='disconnected';self.quotes={};self.flag=None;self.flag_time=None
        self.last_event=None;self.error=None;self.quote_count=0;self.ack=None
        self.subscription_status={}
        self.active_symbols=set(stream_symbols());self.wanted=set(self.active_symbols)
        self.attempts=0;self.next_retry_at=None;self.disabled_reason=None
        self.pending=queue.Queue(maxsize=10000);self.persisted=0;self.dropped=0
        self.rest_last_attempt=None;self.rest_fallback={'status':'not_needed','mode':'REST_DELAYED','interval_seconds':900}
        self.watch_groups={'book':set(self.wanted),'board':set()};self.board_lease_until=0
        self.trades={};self.masters={};self.flags={};self.trade_count=0;self.master_count=0
        # Deliberately not configured from price magnitude or an EOD bar.
        # A verified live schema/unit investigation must set this, not a UI toggle.
        self.verified_price_scale=None
        self.unit_contract=None
        self.research=research;self.raw_sequence=0;self.connection_epoch=0;self.typed_count=0

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            if not all(credentials()[k] for k in ['SSI_API_KEY','SSI_API_SECRET']):
                self.disabled_reason='Thiếu SSI_API_KEY hoặc SSI_API_SECRET trong cấu hình máy chủ.';return
            try:
                from src.research_core import load_contract
                self.unit_contract=load_contract();self.verified_price_scale=Decimal(str(self.unit_contract['price_scale']))
            except (OSError,ValueError,KeyError,ArithmeticError):self.unit_contract=None;self.verified_price_scale=None
            if self.research:
                try:
                    sample=json.loads((Path(__file__).resolve().parents[1]/'config/research_sample.json').read_text())
                    self.watch_groups['research']=set(sample['symbols']);self._wanted_now()
                except (OSError,ValueError,KeyError):pass
            self.stop_event.clear();self.state='connecting'
            self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def watch(self,symbol):
        if not re.fullmatch('[A-Z0-9]+',symbol):return False
        with self.lock:
            self.watch_groups['book']={symbol};self._wanted_now();self.active_symbols.add(symbol)
        return True

    def watch_board(self,symbols):
        valid={s for s in symbols if isinstance(s,str) and re.fullmatch('[A-Z0-9]+',s)}
        with self.lock:
            self.watch_groups['board']=valid;self.board_lease_until=time.monotonic()+30
            self._wanted_now();self.active_symbols.update(valid)
        return valid

    def _wanted_now(self):
        if time.monotonic()>self.board_lease_until:self.watch_groups['board']=set()
        self.wanted=set().union(*self.watch_groups.values())
        return set(self.wanted)

    def _raw(self,frame):
        """Only public DATA payloads; retain decimal strings and never merge partial deltas."""
        topic=str(frame.get('topic','')).lower();data=frame.get('data')
        if not isinstance(data,dict):return
        now=datetime.now(VN).isoformat()
        fields=('b','t','f') if topic=='market.flag' else ('s','t','bids','asks') if topic.startswith('quote.') else ('s','t','p','q','v','o','h','l','a','si') if topic.startswith('trade.') else ('s','b','t','ce','fl','ref')
        if not (topic=='market.flag' or topic.startswith(('quote.','trade.','market.'))):return
        with self.lock:
            self.raw_sequence+=1
            raw_record={'topic':topic,'data':{k:data[k] for k in fields if k in data},'received_at':now,'sequence':self.raw_sequence,'connection_epoch':self.connection_epoch}
        try:self.pending.put_nowait(raw_record)
        except queue.Full:self.dropped+=1
        if topic=='market.flag':
            from ssi_sdk.models import MarketFlagMessage
            self._data(MarketFlagMessage.from_dict(data))
        elif topic.startswith(('trade.','market.')):
            symbol=data.get('s')
            with self.lock:
                if symbol not in self.active_symbols:return
                try:event=datetime.strptime(data['t'],'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN).isoformat()
                except (KeyError,TypeError,ValueError):return
                record={'symbol':symbol,'event_time':event,'received_at':now,'data':{k:data[k] for k in (('s','t','p','q','v','o','h','l','a','si') if topic.startswith('trade.') else ('s','b','t','ce','fl','ref')) if k in data}}
                store=self.trades if topic.startswith('trade.') else self.masters
                previous=store.get(symbol)
                if previous and event<previous['event_time']:return
                store[symbol]=record
                if topic.startswith('trade.'):
                    self.trade_count+=1;self.last_event=now;self.state='connected_unverified'
                else:self.master_count+=1
            return
        elif topic.startswith('quote.'):
            symbol=data.get('s')
            with self.lock:
                if symbol not in self.active_symbols:return
                try:event=datetime.strptime(data['t'],'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN).isoformat()
                except (KeyError,TypeError,ValueError):return
                previous=self.quotes.get(symbol)
                if previous and event<previous['event_time']:return
                self.quote_count+=1;self.last_event=now;self.state='connected_unverified'
                sides={}
                for side in ('bids','asks'):
                    values=data.get(side)
                    sides[side]=values if isinstance(values,list) and all(isinstance(r,(list,tuple)) and len(r)==2 for r in values) else []
                self.subscription_status['quote']='receiving'
                self.quotes[symbol]={'symbol':symbol,'event_time':event,'received_at':now,**sides}
        else:return

    def _flush(self):
        batch=[]
        while not self.pending.empty():
            try:batch.append(self.pending.get_nowait())
            except queue.Empty:break
        if not batch:return
        folder=Path(__file__).resolve().parents[1]/'data/live_snapshots';folder.mkdir(exist_ok=True)
        try:
            with (folder/(datetime.now(VN).date().isoformat()+'.jsonl')).open('a',encoding='utf-8') as handle:
                for item in batch:handle.write(json.dumps(item,ensure_ascii=False)+'\n')
            self.persisted+=len(batch)
        except OSError:self.dropped+=len(batch)

    def _connection(self,event):
        with self.lock:
            self.state='connected_no_ticks' if event.state in ('connected','reconnected') else 'disconnected'
            self.connection_epoch+=1
            try:self.pending.put_nowait({'topic':'collector.connection','received_at':datetime.now(VN).isoformat(),'data':{'state':event.state},'connection_epoch':self.connection_epoch})
            except queue.Full:self.dropped+=1
            self.quotes.clear();self.flag=None;self.flag_time=None
            self.trades.clear();self.masters.clear();self.flags.clear()
            if event.state in ('connected','reconnected'):self.next_retry_at=None
            self.subscription_status={};self.error=None

    def _ack(self,topic,frame):
        status=str(frame.get('status','unknown')).lower() if isinstance(frame,dict) else 'unknown'
        accepted=status in ('ok','success','200')
        rejected=status in ('error','failed','fail','denied','forbidden') or (status.isdigit() and int(status)>=400)
        with self.lock:
            self.subscription_status[topic]='accepted' if accepted else 'rejected' if rejected else 'unknown'
            if rejected:
                self.error={'error_type':'DATA_SUBSCRIPTION_REJECTED','http_status':None,'code':topic.upper()+'_REJECTED'}
                if topic=='quote':self.state='connected_scope_rejected';self.quotes.clear()

    def _data(self,message):
        from ssi_sdk.models import QuoteMessage, MarketFlagMessage
        now=datetime.now(VN)
        with self.lock:
            if isinstance(message,MarketFlagMessage):
                try:
                    event=datetime.strptime(message.trading_time,'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN)
                    old=self.flags.get(message.board)
                    if not old or event.isoformat()>=old['event_time']:
                        self.flags[message.board]={'flag':message.flag,'event_time':event.isoformat(),'received_at':now.isoformat()}
                except ValueError:pass
            if isinstance(message,MarketFlagMessage) and message.board=='HOSE':
                try:
                    self.flag_time=datetime.strptime(message.trading_time,'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN)
                    self.flag=message.flag
                except ValueError:self.flag=None;self.flag_time=None
            if isinstance(message,QuoteMessage) and message.symbol in getattr(self,'active_symbols',[]):
                self.quote_count+=1;self.last_event=now.isoformat();self.state='connected_unverified'
                self.quotes.pop(message.symbol,None)
                try:event=datetime.strptime(message.trading_time,'%Y/%m/%d %H:%M:%S').replace(tzinfo=VN)
                except ValueError:return
                self.quotes[message.symbol]={'symbol':message.symbol,'event_time':event.isoformat(),'received_at':now.isoformat(),
                    'bids':list(zip(message.bid_prices,message.bid_volumes)),
                    'asks':list(zip(message.ask_prices,message.ask_volumes))}

    def _typed_observer(self,message):
        self.typed_count+=1  # SDK typed dispatch preserved; raw branch owns canonical state.

    def _run(self):
        delay=2
        while not self.stop_event.is_set():
            self.attempts+=1;self._session()
            if self.stop_event.is_set():break
            self._rest_refresh()
            with self.lock:
                self.state='reconnecting';self.next_retry_at=(datetime.now(VN)+timedelta(seconds=delay)).isoformat()
            if self.stop_event.wait(delay):break
            delay=min(delay*2,60)
        self._flush()

    def _rest_refresh(self):
        """Provider-cached summary fallback, never a replacement live order book."""
        now=time.monotonic()
        if self.rest_last_attempt is not None and now-self.rest_last_attempt<self.rest_fallback['interval_seconds']:return
        self.rest_last_attempt=now;client=None
        try:
            client=SSIReadonly();client.authenticate()
            rows=client.get('/api/v3/data/indexSummary',{'index':'VNINDEX'})
            if not isinstance(rows,list):raise ValueError('Invalid REST summary')
            record={'source':'SSI indexSummary REST','mode':'REST_DELAYED','received_at':datetime.now(VN).isoformat(),'rows':rows,'note':'REST có thể được SSI cache; không phải quote hoặc LIVE.'}
            folder=Path(__file__).resolve().parents[1]/'data/live_rest';folder.mkdir(exist_ok=True)
            (folder/'latest_index.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
            self.rest_fallback.update(status='cached_summary',received_at=record['received_at'])
        except Exception as error:
            details=safe_error(error);self.rest_fallback.update(status='unavailable',safe_error=details)
            if details['http_status']==429:self.rest_fallback['interval_seconds']=1800
        finally:
            if client:client.close()

    def _session(self):
        client=None
        try:
            client=SSIReadonly();client.authenticate()
            if self.stop_event.is_set():return
            self.data_client=client
            _,_,Stream=sdk()
            with Stream(client.auth) as stream:
                self.ws=stream.streaming;self.ws.on_connection=self._connection;self.ws.on_data=self._typed_observer
                sdk_handler=self.ws._handle_data
                def dispatch(frame):
                    self._raw(frame);sdk_handler(frame)
                self.ws._ws.on('DATA',dispatch)  # Pinned SDK3.3.2 raw DATA boundary, tested by actual probe.
                self.ws.connect()
                subscribed=set();retry_at={}
                self.ws.subscribe_market_flag(on_response=lambda frame:self._ack('market_flag',frame))
                while not self.stop_event.wait(1):
                    if self.ws.last_error:raise self.ws.last_error
                    with self.lock:wanted=self._wanted_now()
                    remove=subscribed-wanted;add=wanted-subscribed
                    if remove:
                        self.ws.unsubscribe_symbol_quote(sorted(remove));self.ws.unsubscribe_symbol_trade(sorted(remove));self.ws.unsubscribe_market(sorted(remove))
                    subscribed-=remove
                    for symbol in sorted(add):
                        if time.monotonic()<retry_at.get(symbol,0):continue
                        try:
                            self.ws.subscribe_symbol_quote([symbol]);self.ws.subscribe_symbol_trade([symbol]);self.ws.subscribe_market([symbol])
                            subscribed.add(symbol);retry_at.pop(symbol,None)
                        except Exception as error:
                            with self.lock:self.error=safe_error(error)
                            retry_at[symbol]=time.monotonic()+5
                            continue
                    with self.lock:self.active_symbols=set(subscribed)
                    self._flush()
        except Exception as error:
            with self.lock:self.error=safe_error(error);self.state='disconnected';self.quotes.clear()
        finally:
            self.data_client=None
            if client:client.close()
            with self.lock:self.ws=None;self.state='disconnected';self.quotes.clear()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=3)

    def status(self):
        with self.lock:
            state=self.state
            if state!='disconnected' and self.quotes:
                books=[self.book(symbol) for symbol in self.quotes]
                if any(book['available'] for book in books):state='live'
                elif all(book['status']=='stale' for book in books):state='stale'
            return {'connection':self.state,'status':state,'stream_active':bool(self.thread and self.thread.is_alive()),
                    'last_event_at':self.last_event,'quote_events':self.quote_count,'safe_error':self.error,
                    'subscription_status':dict(self.subscription_status),
                    'unit_verified':self.verified_price_scale is not None,'disabled_reason':self.disabled_reason,
                    'attempts':self.attempts,'next_retry_at':self.next_retry_at,'watched_symbols':sorted(self.wanted),
                    'persisted_snapshots':self.persisted,'persistence_drops':self.dropped,
                    'trade_events':self.trade_count,'master_events':self.master_count,
                    'rest_fallback':dict(self.rest_fallback),
                    'measurement_status':'VERIFIED' if self.verified_price_scale is not None else 'UNVERIFIED_UNITS',
                    'measurement_reason':'Đơn vị quote và khối lượng chưa có bằng chứng độc lập; kết nối mở không đồng nghĩa chỉ báo LIVE.'}

    def book(self,symbol):
        with self.lock:
            now=datetime.now(VN);candidate=self.quotes.get(symbol)
            result={'source':'SSI DATA','symbol':symbol,'status':self.state,'available':False,'bids':[],'asks':[],
                    'event_time':None,'received_at':None,'latency_ms':None,'unit':'VND/share only after verification','session':self.flag}
            if not candidate:
                result['reason']=self.disabled_reason or ('Đang tự kết nối lại; chờ lần thử kế tiếp '+str(self.next_retry_at) if self.state=='reconnecting' else 'Kết nối đang mở, đang chờ bản tin của mã đã chọn.' if self.state.startswith('connected') else 'Chưa nhận bản tin. Kiểm tra kết nối trong Data Quality; hệ thống sẽ tự thử lại khi lỗi.')
                return result
            result.update(event_time=candidate['event_time'],received_at=candidate['received_at'])
            result['latency_ms']=(datetime.fromisoformat(candidate['received_at'])-datetime.fromisoformat(candidate['event_time'])).total_seconds()*1000
            result['checks']={'units_verified':self.verified_price_scale is not None,'session_flag_received':bool(self.flag_time),'three_levels':len(candidate['bids'])>=3 and len(candidate['asks'])>=3,'source_fresh':(now-datetime.fromisoformat(candidate['event_time'])).total_seconds()<=30}
            result['unverified_levels']={'bids':[[str(p),str(q)] for p,q in candidate['bids'][:3]],
                                         'asks':[[str(p),str(q)] for p,q in candidate['asks'][:3]],
                                         'price_unit':'unverified','quantity_unit':'unverified',
                                         'parser':'SSI raw DATA quote; full received sides retained, no delta merge'}
            try:
                if self.state=='disconnected':raise ValueError('DATA đã mất kết nối.')
                if not self.flag_time or self.flag_time.date()!=now.date() or (now-self.flag_time).total_seconds()>4*3600:
                    raise ValueError('Chưa có cờ phiên HOSE mới được xác minh.')
                if self.flag_time>datetime.fromisoformat(candidate['event_time']):
                    raise ValueError('Cờ phiên xảy ra sau snapshot quote.')
                if not self.unit_contract or symbol not in self.unit_contract['symbols']:raise ValueError('Mã nằm ngoài hợp đồng đơn vị/schema đã kiểm chứng.')
                normalized={**candidate,**{side:[[p,str(Decimal(str(q))*Decimal(str(self.unit_contract['quantity_scale'])))] for p,q in candidate[side]] for side in ('bids','asks')}}
                metrics=book_metrics(normalized,self.verified_price_scale,self.flag,now)
                result.update(metrics,available=True,status='live',unit='VND/share',
                              latency_ms=(datetime.fromisoformat(candidate['received_at'])-datetime.fromisoformat(candidate['event_time'])).total_seconds()*1000)
            except ValueError as error:
                stale=(now-datetime.fromisoformat(candidate['event_time'])).total_seconds()>30
                result.update(status='stale' if stale else 'unverified',reason=str(error))
            return result


LIVE=DataStream(research=True)


def start_live_stream():
    if os.environ.get('SSI_ENABLE_STREAM','1')=='1':LIVE.start()
    else:LIVE.disabled_reason='SSI_ENABLE_STREAM=0: kết nối DATA được tắt trong cấu hình chạy hiện tại.'
