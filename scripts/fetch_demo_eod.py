"""Explicit one-shot EOD download via documented Vnstock Market interface.

Optional dependency only for acquisition, never imported by the local server:
pip install --extra-index-url https://vnstocks.com/api/packages vnstock==5.2.1
No source credentials, hidden endpoint scraping, SSI calls or database.
"""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.eod_snapshot import COLUMNS, MAX_DATE, validate_snapshot

DOC_URL = 'https://www.vnstocks.com/docs/vnstock/thi-truong-market'
SOURCE_URL = 'https://trading.vietcap.com.vn/'
TERMS_URL = 'https://www.vietcap.com.vn/dieu-khoan-su-dung-chinh-sach-bao-mat'
METHOD_URL = 'https://raw.githubusercontent.com/thinh-vu/vnstock/main/vnstock/explorer/vci/quote.py'


def run_worker_bounded(command):
    """Retry a worker timeout once, with provider-safe backoff; never retry denials.

    Nonzero worker exits (including entitlement/rate/source errors) are returned
    directly for diagnosis, rather than repeatedly hitting an unavailable source.
    """
    for attempt in range(2):
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=45,
                                     env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            return process, attempt
        except subprocess.TimeoutExpired as exc:
            if attempt:
                exc.retries_used = attempt
                raise
            print('Worker timeout; one retry after 10 seconds.', flush=True)
            time.sleep(10)


def fetch_worker(symbol, start, end, source='vci'):
    local_package = ROOT / '.tools' / 'vnstock'
    if local_package.is_dir():
        sys.path.insert(0, str(local_package))
    # Keep optional library state within project, not in the user's global profile.
    os.environ.setdefault('VNSTOCK_HOME', str(ROOT / '.tools' / 'vnstock-state'))
    import vnstock
    from vnstock import Market
    frame = Market().equity(symbol).ohlcv(start=start, end=end, interval='1D', source=source, floating=None)
    if frame.attrs.get('source') != source:
        raise ValueError('Unexpected upstream; no automatic source mixing allowed')
    records = []
    for _, row in frame.iterrows():
        timestamp = row['time']
        if timestamp.tzinfo is None:
            raise ValueError('Naive provider time is not accepted')
        session = timestamp.tz_convert('Asia/Ho_Chi_Minh').date().isoformat()
        records.append({'symbol': symbol, 'date': session,
                        **{f'{k}_vnd': str(Decimal(str(row[k])) * 1000) for k in ('open', 'high', 'low', 'close')},
                        'volume_shares': str(row['volume']), 'turnover_vnd': '',
                        'price_adjustment': 'provider_adjusted', 'upstream_source': source, 'source_url': SOURCE_URL if source == 'vci' else 'https://www.kbsec.com.vn/'})
    print('__EOD__' + json.dumps({'version': vnstock.__version__, 'attrs': frame.attrs, 'records': records}, ensure_ascii=False, default=str))


def run_fetch(args):
    asof = date.fromisoformat(args.asof)
    if asof > MAX_DATE:
        raise ValueError('asof cannot exceed 2026-11-04')
    if not 1 <= args.lookback <= 1000:
        raise ValueError('lookback must be between 1 and 1000 sessions')
    symbols = list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(',') if s.strip()))
    if not symbols or any(not s.isalnum() or len(s) > 12 for s in symbols):
        raise ValueError('Invalid symbols')
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).exists() for name in ('ohlcv.csv', 'index_ohlcv.csv')):
        raise ValueError('Existing snapshot protected. Choose a new --out-dir for a new acquisition.')
    start = (asof - timedelta(days=args.lookback * 2 + 20)).isoformat()
    records, issues, attempts = [], [], []
    retry_count = 0
    versions, metadata = set(), []
    excluded = {'after_cutoff': 0, 'before_selected_window': 0, 'identical_duplicates': 0}
    for index, symbol in enumerate(symbols):
        if index:
            time.sleep(10)  # Provider robots crawl-delay reported by the public wrapper.
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', symbol, '--worker-start', start, '--asof', asof.isoformat()]
        attempt = {'symbol': symbol, 'method': 'Market().equity(symbol).ohlcv', 'source': 'vci', 'url': SOURCE_URL}
        try:
            process, retries_used = run_worker_bounded(command)
            retry_count += retries_used
            attempt['retries_used'] = retries_used
            marker = next((line[len('__EOD__'):] for line in process.stdout.splitlines() if line.startswith('__EOD__')), None)
            if process.returncode or not marker:
                raise RuntimeError((process.stderr or process.stdout)[-1000:])
            result = json.loads(marker)
            versions.add(result['version'])
            metadata.append({'symbol': symbol, 'attrs': result['attrs']})
            by_date = {}
            for row in result['records']:
                if date.fromisoformat(row['date']) > asof:
                    excluded['after_cutoff'] += 1
                    continue
                if row['date'] in by_date:
                    if row != by_date[row['date']]:
                        raise ValueError('Conflicting duplicate session; rejecting symbol')
                    excluded['identical_duplicates'] += 1
                by_date[row['date']] = row
            chosen = sorted(by_date.values(), key=lambda row: row['date'])[-args.lookback:]
            excluded['before_selected_window'] += max(0, len(by_date) - len(chosen))
            records.extend(chosen)
            attempt.update(status='downloaded', rows=len(chosen), last_session=chosen[-1]['date'] if chosen else None)
            print(f'{symbol}: {len(chosen)} sessions, last={attempt["last_session"]}', flush=True)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            if isinstance(exc, subprocess.TimeoutExpired):
                attempt['retries_used'] = getattr(exc, 'retries_used', 0)
                retry_count += attempt['retries_used']
            attempt.update(status='blocked', error=str(exc))
            issues.append(f'{symbol}: {str(exc)}')
            print(f'{symbol}: BLOCKED', flush=True)
        attempts.append(attempt)
    records.sort(key=lambda row: (row['symbol'], row['date']))
    loaded = sorted({r['symbol'] for r in records})
    coverage = {}
    for symbol in loaded:
        dates = [r['date'] for r in records if r['symbol'] == symbol]
        coverage[symbol] = {'rows': len(dates), 'first_available_session': min(dates), 'last_available_session': max(dates)}
    cross_checks = []
    if loaded:
        symbol = loaded[0]
        time.sleep(10)
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', symbol,
                   '--worker-source', 'kbs', '--worker-start', (asof - timedelta(days=7)).isoformat(), '--asof', asof.isoformat()]
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=45,
                                     env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            marker = next((line[len('__EOD__'):] for line in process.stdout.splitlines() if line.startswith('__EOD__')), None)
            if process.returncode or not marker:
                raise RuntimeError((process.stderr or process.stdout)[-500:])
            comparison = json.loads(marker)
            main_rows = {r['date']: r for r in records if r['symbol'] == symbol}
            fields = ['open_vnd','high_vnd','low_vnd','close_vnd','volume_shares']
            observations = []
            for row in comparison['records']:
                if row['date'] in main_rows:
                    matches = {f: Decimal(row[f]) == Decimal(main_rows[row['date']][f]) for f in fields}
                    observations.append({'symbol': symbol, 'date': row['date'], 'fields_match': matches,
                                         'reference': {f: row[f] for f in fields}})
            cross_checks.append({'reference_source': 'kbs', 'source_url': 'https://www.kbsec.com.vn/',
                                 'method': 'Documented Market equity ohlcv source=kbs; sample only, never overwrites VCI',
                                 'status': 'MATCH' if observations and all(all(o['fields_match'].values()) for o in observations) else 'DIFFERENCE_OR_EMPTY',
                                 'observations': observations, 'metadata': comparison['attrs']})
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            cross_checks.append({'reference_source': 'kbs', 'status': 'BLOCKED', 'details': str(exc)})
    checksums = {}
    if records:
        with (out / 'ohlcv.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader(); writer.writerows(records)
        checksums['ohlcv.csv'] = sha256((out / 'ohlcv.csv').read_bytes()).hexdigest()
    usage = ('Local personal academic research/display only. Vietcap terms permit downloading information for personal use; '
             'redistribution/publication/commercial use is not granted. Vnstock software permission does not grant upstream data rights. '
             'Do not publish or bundle this snapshot for third parties without checking permissions.')
    manifest = {'schema_version': '1.0', 'dataset_type': 'historical_eod_snapshot', 'asof_date': asof.isoformat(),
                'asof_timezone': 'Asia/Ho_Chi_Minh', 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                'symbols_requested': symbols, 'symbols_loaded': loaded, 'lookback_sessions_requested': args.lookback,
                'units': {'price': 'VND/share', 'volume': 'share', 'turnover': 'VND'},
                'adjustment_policy': 'provider_adjusted', 'coverage_by_symbol': coverage, 'row_count': len(records),
                'file_sha256': checksums, 'refresh_policy': 'manual_one_shot', 'issues': issues,
                'missing_values': {'turnover_vnd': len(records)}, 'rows_excluded': excluded,
                'upstream_sources': [{'id': 'vci', 'name': 'Vietcap via Vnstock', 'source_url': SOURCE_URL,
                    'documentation_url': DOC_URL, 'terms_url': TERMS_URL, 'usage_note': usage,
                    'access_method': 'POST via documented Vnstock Market interface',
                    'legacy_published_endpoint': 'https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart',
                    'endpoint_evidence_url': METHOD_URL,
                    'endpoint_note': 'Endpoint evidenced by official source-available legacy client, not exposed in v5 runtime attrs; current route reported as market.equity.ohlcv.',
                    'price_conversion': 'documented adjusted thousand VND multiplied by Decimal(1000)',
                    'volume_policy': 'provider reported shares; not multiplied by price',
                    'adjustment_note': 'As retrieved provider-adjusted prices; revisions/corporate actions may change historical values later.'}],
                'acquisition': {'wrapper': 'vnstock', 'versions': sorted(versions), 'attempts': attempts,
                                'request_metadata': metadata, 'timeout_seconds_per_symbol': 45, 'retry_count': retry_count,
                                'maximum_timeout_retries_per_symbol': 1, 'timeout_backoff_seconds': 10,
                                'rate_limit_seconds_between_symbols': 10},
                'cross_checks': cross_checks, 'quality_checks': {}}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    result = validate_snapshot(out)
    manifest['quality_checks'] = {'passed': result['passed'], 'status': result['status'], 'details': result['issues']}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    handoff = {'phase': 'data_acquisition', 'status': result['status'], 'asof_date': asof.isoformat(),
               'timezone': 'Asia/Ho_Chi_Minh', 'manifest_path': 'data/demo/manifest.json',
               'ohlcv_path': 'data/demo/ohlcv.csv' if result['passed'] else None, 'index_path': None,
               'loaded_symbols': loaded if result['passed'] else [], 'coverage_by_symbol': coverage if result['passed'] else {},
               'quality_gate': {'passed': result['passed'], 'validator_command': 'python scripts/validate_demo_eod.py --data-dir data/demo',
                                'details': 'Independent local schema/checksum/provenance validation. Crosschecks reported separately.'},
               'issues': result['issues'], 'next_step': 'PROMPT_2'}
    (out / 'PHASE1_HANDOFF.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'passed': result['passed'], 'rows': len(records), 'coverage': coverage}, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--asof', default='2026-11-04')
    parser.add_argument('--lookback', type=int, default=90)
    parser.add_argument('--symbols', default='FPT,VNM,HPG,SSI,VCB,MWG')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'data' / 'demo')
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--worker-start', help=argparse.SUPPRESS)
    parser.add_argument('--worker-source', choices=('vci','kbs'), default='vci', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        fetch_worker(args.worker, args.worker_start, args.asof, args.worker_source)
    else:
        sys.exit(run_fetch(args))
