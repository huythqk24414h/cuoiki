"""Offline audit/replay; will not substitute EOD for intraday or fabricate H1 output."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.research_core import audit_research,replay
report=audit_research()
out=ROOT/'data/research';out.mkdir(exist_ok=True)
events,manifest=replay((ROOT/'data/live_snapshots').glob('*.jsonl'))
with (out/'replayed.jsonl').open('w',encoding='utf-8') as f:
    for e in events:f.write(json.dumps(e,ensure_ascii=False)+'\n')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(ROOT/'docs/RESEARCH_READINESS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
