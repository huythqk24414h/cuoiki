"""Independent raw→normalized SSI integrity gate, local files only."""
import csv
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

def validate_ssi_snapshot(folder):
    result = {'passed': False, 'status': 'BLOCKED', 'rows': [], 'manifest': {}, 'coverage_by_symbol': {}, 'issues': []}
    try:
        folder = Path(folder)
        m = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        json.dumps(m, allow_nan=False)
        if not (m['dataset_type'] == 'ssi_historical_eod' and m['asof_date'] == '2026-11-04'):
            raise ValueError('SSI snapshot invariant failed')
        if not m['endpoint'] == 'https://api.ssi.com.vn/api/v3/data/ohlc':
            raise ValueError('SSI snapshot invariant failed')
        if not (m['asof_timezone'] == 'Asia/Ho_Chi_Minh' and m['adjustment_policy'] == 'unknown'):
            raise ValueError('SSI snapshot invariant failed')
        if not m['units'] == {'price': 'VND/share', 'volume': 'share', 'turnover': 'VND'}:
            raise ValueError('SSI snapshot invariant failed')
        if not datetime.fromisoformat(m['retrieved_at_utc']).utcoffset() is not None:
            raise ValueError('SSI snapshot invariant failed')
        if not (m['unit_evidence']['checks'] and all((c['OHLCV_matches_VCI_VND'] is True for c in m['unit_evidence']['checks']))):
            raise ValueError('SSI snapshot invariant failed')
        path = folder / 'ohlcv_daily.csv'
        if not sha256(path.read_bytes()).hexdigest() == m['file_sha256']['ohlcv_daily.csv']:
            raise ValueError('CSV checksum mismatch')
        raw = {}
        for filename, digest in m['raw_sha256'].items():
            if not re.fullmatch('[A-Z0-9]{1,12}_[1-9][0-9]*\\.json', filename):
                raise ValueError('SSI snapshot invariant failed')
            blob = (folder / 'raw' / filename).read_bytes()
            if not sha256(blob).hexdigest() == digest:
                raise ValueError('Raw checksum mismatch')
            envelope = json.loads(blob)
            if not envelope['range'] == m['query_range']:
                raise ValueError('SSI snapshot invariant failed')
            for row in envelope['response']['data']:
                key = (row['symbol'], datetime.strptime(row['tradingDate'][:10], '%Y/%m/%d').date().isoformat())
                if key in raw:
                    if not raw[key] == row:
                        raise ValueError('Conflicting raw duplicate')
                raw[key] = row
        with path.open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        if not (rows and len(rows) == m['row_count']):
            raise ValueError('SSI snapshot invariant failed')
        seen = set()
        coverage = {}
        canonical = []
        for row in rows:
            symbol, day = (row['symbol'], row['trading_date'])
            key = (symbol, day)
            if not symbol in m['symbols_loaded']:
                raise ValueError('SSI snapshot invariant failed')
            if not (date.fromisoformat(day).isoformat() == day and '2026-01-01' <= day <= '2026-11-04'):
                raise ValueError('SSI snapshot invariant failed')
            if not key not in seen:
                raise ValueError('Duplicate normalized row')
            seen.add(key)
            if not (row['source'] == 'SSI FastConnect V3' and row['timeframe'] == '1d'):
                raise ValueError('SSI snapshot invariant failed')
            if not (row['timezone'] == 'Asia/Ho_Chi_Minh' and row['adjustment_status'] == 'unknown'):
                raise ValueError('SSI snapshot invariant failed')
            if not row['raw_unit'] == row['normalized_unit'] == 'VND/share':
                raise ValueError('SSI snapshot invariant failed')
            o, h, l, c = [Decimal(row[k]) for k in ['open', 'high', 'low', 'close']]
            if not all((n.is_finite() and 0 < n <= Decimal('1e15') for n in [o, h, l, c])):
                raise ValueError('SSI snapshot invariant failed')
            if not (h >= max(o, l, c) and l <= min(o, h, c)):
                raise ValueError('Invalid OHLC')
            v = Decimal(row['volume'])
            if not (v.is_finite() and v >= 0 and (v == v.to_integral_value())):
                raise ValueError('SSI snapshot invariant failed')
            if row['value']:
                value = Decimal(row['value'])
                if not (value.is_finite() and value >= 0):
                    raise ValueError('SSI snapshot invariant failed')
            original = raw[key]
            for field in ['open', 'high', 'low', 'close', 'volume']:
                if not Decimal(row[field]) == Decimal(str(original[field])):
                    raise ValueError('Raw/normalized invariant failed')
            if not row['value'] == ('' if original.get('value') is None else str(original['value'])):
                raise ValueError('SSI snapshot invariant failed')
            ds = coverage.setdefault(symbol, [])
            ds.append(day)
            canonical.append({'symbol': symbol, 'date': day, **{k + '_vnd': row[k] for k in ['open', 'high', 'low', 'close']}, 'volume_shares': row['volume'], 'turnover_vnd': '', 'source_value_vnd': row['value'], 'price_adjustment': 'unknown', 'upstream_source': 'ssi_v3', 'source_url': m['endpoint']})
        if not seen == set(raw):
            raise ValueError('Raw observations lost or invented')
        actual = {s: {'rows': len(ds), 'first_available_session': min(ds), 'last_available_session': max(ds)} for s, ds in coverage.items()}
        if not (actual == m['coverage_by_symbol'] and set(actual) == set(m['symbols_loaded'])):
            raise ValueError('SSI snapshot invariant failed')
        if not rows == sorted(rows, key=lambda r: (r['symbol'], r['trading_date'])):
            raise ValueError('SSI snapshot invariant failed')
        m = {**m, 'upstream_sources': [{'id': 'ssi_v3', 'name': 'SSI FastConnect V3', 'source_url': m['endpoint'], 'documentation_url': m['documentation_url'], 'usage_note': m['usage_note']}], 'missing_values': {'turnover_vnd': len(rows), 'source_value_vnd': sum((not r['value'] for r in rows))}, 'value_semantics': 'Retained as source_value_vnd (source-reported proxy); actual turnover_vnd unverified and unavailable.', 'value_diagnostics': {'observations': sum(bool(r['value']) for r in rows), 'equal_close_times_volume': sum(bool(r['value']) and Decimal(r['value']) == Decimal(r['close']) * Decimal(r['volume']) for r in rows)}}
        result.update(passed=True, status='PARTIAL' if m['errors'] or any((c['last_available_session'] < '2026-11-04' for c in actual.values())) else 'VALID', rows=canonical, manifest=m, coverage_by_symbol=actual)
    except (OSError, ValueError, TypeError, KeyError, AssertionError, ArithmeticError) as error:
        result['issues'] = [str(error) or 'SSI snapshot schema/invariant failed']
    return result
