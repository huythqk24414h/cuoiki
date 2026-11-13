"""Bounded actual runtime + HTTP verification. Explicitly not browser acceptance."""
import sys,time,json,threading
from pathlib import Path
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.ssi_stream import LIVE
from run import Handler

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    def get(path):
        with urlopen(base+path,timeout=30) as response:return json.load(response)
    report={'browser':'BLOCKED_PERMISSION_POLICY','screenshots':0,'checks':[]}
    try:
        LIVE.watch('SSI');LIVE.start();time.sleep(20)
        state=get('/api/market/status');book=get('/api/market/book?symbol=SSI')
        report['runtime']=state;report['book_state']={k:book.get(k) for k in ('available','status','reason','event_time','received_at','latency_ms','session')}
        report['checks'].append({'name':'actual selected-symbol DATA stream and persistence','status':'PASS' if state['quote_events']>0 and state['persisted_snapshots']>0 and not state['safe_error'] else 'FAIL'})
        for asset in ['/vendor/lightweight-charts.js','/vendor/echarts.js','/chart-kit.js','/market-ui.js','/']:
            with urlopen(base+asset) as response:
                if response.status!=200 or not response.read():raise ValueError('Asset unavailable')
        report['checks'].append({'name':'actual HTTP assets with local libraries','status':'PASS'})
        sheet=get('/api/market/insights?symbol=SSI&date=2026-11-04')
        if sheet['status']!='DESCRIPTIVE' or len(sheet['paragraphs'])<4:raise ValueError('Missing facts')
        alerts=get('/api/market/alerts?symbol=SSI')
        event=alerts['rows'][0];evidence=get('/api/market/event-evidence?symbol=SSI&date='+event['timestamp'])
        if not evidence['event_date_exact'] or evidence['facts']['rv20']!=event['value'] or any(r['date']>event['timestamp'] for r in evidence['context']):raise ValueError('Evidence mismatch/lookahead')
        report['checks'].append({'name':'actual fact sheet and event evidence match engine/no lookahead','status':'PASS','event':event['id']})
    finally:
        LIVE.stop()
        LIVE._rest_refresh()  # Verify fallback separately after socket closes: no competing SSI session.
        report['rest_fallback']=LIVE.rest_fallback
        report['checks'].append({'name':'actual REST delayed fallback, never LIVE book','status':'PASS' if LIVE.rest_fallback['status']=='cached_summary' else 'BLOCKED'})
        server.shutdown();server.server_close();thread.join()
        (ROOT/'docs/REALTIME_RECOVERY_EVIDENCE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
