"""Allowlisted submission package, never .env/.tools/raw private data/nested ZIPs."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import sys,json,argparse
parser=argparse.ArgumentParser();parser.add_argument('--include-sample',action='store_true');args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.ssi_client import credentials
keys=[v.encode() for k,v in credentials().items() if k in ('SSI_API_KEY','SSI_API_SECRET') and v]
allowed={'src','web','scripts','tests','docs','config','report'}
files=[p for p in ROOT.rglob('*') if p.is_file() and (p.relative_to(ROOT).parts[0] in allowed or len(p.relative_to(ROOT).parts)==1)]
files=[p for p in files if p.name=='.env.example' or (not p.name.startswith('.env') and '__pycache__' not in p.parts and p.suffix not in ('.zip','.pyc') and not p.name.endswith('.tmp'))]
if args.include_sample:
    files=[p for p in files if p.relative_to(ROOT).as_posix() not in ('config/history_active.json','config/history_active.sha256')]
    files.extend(p for folder in ('data/ssi_snapshots','data/demo') for p in (ROOT/folder).rglob('*') if p.is_file())
    files.extend(p for p in (ROOT/'data/ssi_universe_20261104').glob('*') if p.is_file())
    files.extend(p for p in (ROOT/'data/ssi_universe_20261104/indices').glob('*') if p.is_file())
for p in files:
    if any(key in p.read_bytes() for key in keys):raise ValueError('Secret scan failed; path suppressed')
out=ROOT.parent/('liquidity-lab_LOCAL_SAMPLE.zip' if args.include_sample else 'liquidity-lab_SUBMISSION_SAFE.zip');temp=out.with_suffix('.tmp')
with ZipFile(temp,'w',ZIP_DEFLATED) as z:
    for p in files:z.write(p,'liquidity-lab/'+p.relative_to(ROOT).as_posix())
temp.replace(out)
with ZipFile(out) as z:
    if any(n.endswith('/.env') for n in z.namelist()):raise ValueError('Archive gate failed')
print(json.dumps({'status':'PASS','files':len(files),'archive':str(out),'research_result':'NOT_TESTED','raw_data_included':args.include_sample}))
