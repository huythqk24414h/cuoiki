import sys,time,json,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.ssi_stream import LIVE
from src.quote_board import board_payload
LIVE.watch('SSI');initial,code=board_payload('scope=INDEX:VN30&size=30');assert code==200
LIVE.start()
try:
 time.sleep(20)
 result,code=board_payload('scope=INDEX:VN30&size=30');state=LIVE.status()
 try: subscriptions=LIVE.ws.list_subscription() if LIVE.ws else {}
 except Exception: subscriptions={'status':'unavailable'}
 assert code==200 and len(result['rows'])>1
 assert 'SSI' in LIVE.wanted
 evidence={'status':'PASS' if result['received_rows']>0 else 'BLOCKED_NO_TICKS','rows':len(result['rows']),'received_rows':result['received_rows'],'fresh_rows':result['fresh_rows'],'runtime':state,'subscriptions':subscriptions,'sample':result['rows'][:3],'scope':result['scope'],'ui_browser':'NOT_VERIFIED','note':'SSI DATA inputs only; lunch/old ticks remain STALE, never replaced with EOD'}
 (ROOT/'docs/QUOTE_BOARD_TEST.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(evidence,ensure_ascii=False))
finally:LIVE.stop()
