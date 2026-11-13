"""Independent SSI validation/quality CLI. No network or auth imports executed."""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ssi_snapshot import validate_ssi_snapshot


def quality(folder):
    gate=validate_ssi_snapshot(folder)
    rows=gate['rows']
    value_rows=[r for r in rows if r['source_value_vnd']]
    equals=sum(Decimal(r['source_value_vnd'])==Decimal(r['close_vnd'])*Decimal(r['volume_shares']) for r in value_rows)
    return {'checked_at_utc':datetime.now(timezone.utc).isoformat(),'passed':gate['passed'],'status':gate['status'],
            'row_count':len(rows),'coverage_by_symbol':gate['coverage_by_symbol'],'issues':gate['issues'],
            'checks':['raw and CSV checksum','raw→normalized equality','unique symbol/date','date cutoff',
                      'finite positive coherent OHLC','integer nonnegative volume','declared source/units/timezone','coverage'],
            'diagnostics':{'missing_value_field':len(rows)-len(value_rows),'value_equals_close_times_volume':equals,
                           'actual_turnover_unverified':len(rows),'value_observations':len(value_rows),'value_semantics':'SSI source-reported value, not independently audited cash turnover. Do not infer true turnover merely from a populated field.',
                           'weekend_observations':sum(datetime.fromisoformat(r['date']).weekday()>4 for r in rows),
                           'calendar_note':'No invented holiday rows; calendar completeness has not been independently checked against exchange holiday schedule.'}}


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=ROOT/'data/ssi_snapshots')
    parser.add_argument('--report',action='store_true');args=parser.parse_args()
    report=quality(args.data_dir)
    if args.report:(args.data_dir/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));sys.exit(0 if report['passed'] else 1)
