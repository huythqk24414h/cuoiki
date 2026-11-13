"""Bounded readonly DATA diagnostic. Only public quote/flag/market payloads saved."""
import sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.ssi_client import SSIReadonly,sdk,safe_error
from datetime import datetime,timezone

def main():
    client=SSIReadonly();frames=[];events=[];acks=[]
    report={'started_at':datetime.now(timezone.utc).isoformat()}
    try:
        client.authenticate();report['auth']='PASS';_,_,Stream=sdk()
        with Stream(client.auth) as stream:
            ws=stream.streaming
            ws.on_data=lambda _:None
            ws.on_connection=lambda e:events.append({'state':e.state,'error':safe_error(e.error) if getattr(e,'error',None) else None})
            def receive(frame):
                topic=str(frame.get('topic','')).lower()
                if topic.startswith(('quote.','market.')) and isinstance(frame.get('data'),dict):frames.append({'topic':frame['topic'],'data':frame['data'],'received_at':datetime.now(timezone.utc).isoformat()})
            ws._ws.on('DATA',receive)
            ws.connect()
            ws.subscribe_symbol_quote(['SSI'],on_response=lambda f:acks.append({'topic':'quote','status':f.get('status')}))
            ws.subscribe_market(['SSI'])
            ws.subscribe_market_flag(on_response=lambda f:acks.append({'topic':'flag','status':f.get('status')}))
            time.sleep(25)
            report.update(is_connected=ws.is_connected,last_error=safe_error(ws.last_error) if ws.last_error else None,reconnect_count=ws.reconnect_count)
    except Exception as e:report['error']=safe_error(e)
    finally:
        report.update(events=events,acks=acks,frame_count=len(frames),http=client.evidence)
        out=ROOT/'data/live_diagnostics';out.mkdir(exist_ok=True)
        (out/'public_frames.json').write_text(json.dumps(frames,ensure_ascii=False),encoding='utf-8')
        (ROOT/'docs/LIVE_DIAGNOSTIC.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));client.close()

if __name__=='__main__':main()
