"""Validate offline snapshot; never fetches or modifies files."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.eod_snapshot import validate_snapshot


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'data' / 'demo')
    args = parser.parse_args()
    result = validate_snapshot(args.data_dir)
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'index_rows')}, ensure_ascii=False, indent=2))
    sys.exit(0 if result['passed'] else 1)
