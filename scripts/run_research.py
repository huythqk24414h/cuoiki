"""Real-data-only offline pipeline; fail closed before fitting when prerequisites are unmet."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.research_core import audit_research,load_contract,replay
report=audit_research()
if report['blockers']:
    print(json.dumps(report));sys.exit(2)
from src.research_dataset import build_grid,label_dataset
from src.research_models import evaluate
protocol=json.loads((ROOT/'config/research_protocol.json').read_text());contract=load_contract()
events,manifest=replay((ROOT/'data/live_snapshots').glob('*.jsonl'))
grid=build_grid(events,contract,protocol);labeled=label_dataset(grid,protocol)
result=evaluate(labeled,protocol['seed']);result.update(raw_manifest=manifest,protocol=protocol)
out=ROOT/'data/research';out.mkdir(exist_ok=True)
(out/'evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Real-data evaluation saved; review diagnostics before any H1 conclusion.')
