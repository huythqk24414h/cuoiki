"""Explicit SSI auth/list/date probe. Only safe status/market payloads are persisted."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ssi_client import SSIReadonly, safe_error


def main():
    report = {'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'sdk_version': '3.3.2',
              'source': 'SSI FastConnect V3', 'asof': '2026-11-04', 'steps': [], 'status': 'BLOCKED'}
    out = ROOT / 'data/ssi_snapshots'
    out.mkdir(parents=True, exist_ok=True)
    client = None
    try:
        client = SSIReadonly()
        client.authenticate()
        report['steps'].append({'step': 'auth', 'status': 'PASS'})
        securities = client.get('/api/v3/data/securitiesByBoard', {'board': 'HOSE'})
        if not isinstance(securities, list):
            raise ValueError('Unexpected securities schema')
        (out / 'securities.json').write_text(json.dumps(securities,ensure_ascii=False),encoding='utf-8')
        report['steps'].append({'step': 'HOSE_list', 'status': 'PASS', 'items': len(securities),
                                'note': 'Instrument count, not count of actively trading common stocks.'})
        first, last = '2026-10-01T00:00:00+07:00', '2026-11-04T23:59:59+07:00'
        try:
            raw = client.ohlc('SSI',first,last,size=100)
            date_format = 'YYYY/MM/DD HH:MM:SS'
        except Exception as error:
            report['steps'].append({'step':'ohlc_datetime','status':'FAIL',**safe_error(error)})
            if getattr(error,'status_code',None) != 400:
                raise
            # API reference specifies date-only for daily. One documented fallback, no guessing.
            raw = client.ohlc('SSI',first,last,size=100,daily=True)
            date_format = 'YYYY/MM/DD'
        rows = raw.get('data') if isinstance(raw,dict) else None
        if not isinstance(rows,list) or not rows:
            raise ValueError('No OHLC rows returned')
        (out / 'probe_ohlc_raw.json').write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
        report['steps'].append({'step':'ohlc_date_fix','status':'PASS','rows':len(rows),
                                'date_format':date_format,'row_keys':list(rows[0]),'sample':rows[0]})
        report['status']='PARTIAL'
        from src.ssi_client import sdk
        _,_,Stream = sdk()
        counts = {}
        shapes = []
        valid_quotes = []
        connection = []
        with Stream(client.auth) as stream:
            ws=stream.streaming
            ws.on_connection=lambda event: connection.append(event.state)
            def on_data(message):
                name=type(message).__name__
                counts[name]=counts.get(name,0)+1
                if isinstance(message,dict):
                    data=message.get('data',message)
                    import re
                    status=str(message.get('status',''))
                    shapes.append({'keys':list(message),'data_keys':list(data) if isinstance(data,dict) else [],
                                   'status':status if re.fullmatch('[A-Za-z0-9_ -]{0,40}',status) else 'REDACTED',
                                   'code':message.get('code') if isinstance(message.get('code'),int) else None})
                    if isinstance(data,dict) and all(k in data for k in ['s','t','bids','asks']):
                        valid_quotes.append({k:data[k] for k in ['s','t','bids','asks']})
            ws.on_data=on_data
            ws.connect()
            ws.subscribe_symbol_quote(['SSI'])
            ws.wait(timeout_ms=12000)
            report['steps'].append({'step':'DATA_quote_websocket','status':'RECEIVED_QUOTES_UNVERIFIED' if valid_quotes else 'CONNECTED_NO_TICKS',
                                    'connection_events':connection,'message_counts':counts,
                                    'message_shapes':shapes[:5],'valid_quote_count':len(valid_quotes),
                                    'note':'No Trading subscription. No validated live book claimed.'})
    except Exception as error:
        report['steps'].append({'step':'probe_stopped','status':'BLOCKED',**safe_error(error)})
    finally:
        if client:
            report['http_observations']=client.evidence
            client.close()
        (out/'probe_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
