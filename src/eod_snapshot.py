"""Offline-only validation of frozen EOD CSV and its provenance manifest."""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

MAX_DATE = date(2026, 11, 4)
COLUMNS = ['symbol', 'date', 'open_vnd', 'high_vnd', 'low_vnd', 'close_vnd',
           'volume_shares', 'turnover_vnd', 'price_adjustment', 'upstream_source', 'source_url']


def _number(value, name):
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'{name}: invalid decimal') from exc
    if not result.is_finite() or abs(result) > Decimal('1e30'):
        raise ValueError(f'{name}: nonfinite or excessive number')
    return result


def _url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username and not parsed.password


def validate_snapshot(folder):
    """Return data only after independent checksum/schema/provenance/coverage checks.

    Never trusts PHASE1_HANDOFF.json or a stored quality_gate flag. Does no I/O
    other than reading local files. Any invalid row rejects the complete snapshot.
    """
    manifest = {}
    result = dict(passed=False, status='BLOCKED', manifest=manifest, rows=[], index_rows=[],
                  coverage_by_symbol={}, issues=[])
    try:
        folder = Path(folder)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('Manifest must be an object')
        result['manifest'] = manifest
        if manifest.get('dataset_type') != 'historical_eod_snapshot':
            raise ValueError('Wrong dataset_type')
        cutoff = date.fromisoformat(manifest['asof_date'])
        if cutoff > MAX_DATE or manifest.get('asof_timezone') != 'Asia/Ho_Chi_Minh':
            raise ValueError('Wrong cutoff or timezone')
        requested = manifest.get('symbols_requested')
        loaded = manifest.get('symbols_loaded')
        if not isinstance(requested, list) or not requested or len(set(requested)) != len(requested):
            raise ValueError('Invalid requested symbols')
        if any(not isinstance(s, str) or not re.fullmatch('[A-Z0-9]{1,12}', s) for s in requested):
            raise ValueError('Invalid symbol name')
        if not isinstance(loaded, list) or len(set(loaded)) != len(loaded) or not set(loaded).issubset(requested):
            raise ValueError('Invalid loaded symbols')
        if manifest.get('units') != {'price': 'VND/share', 'volume': 'share', 'turnover': 'VND'}:
            raise ValueError('Incorrect equity units')
        if manifest.get('refresh_policy') != 'manual_one_shot':
            raise ValueError('Snapshot must be manual_one_shot')
        if not loaded:
            if (folder / 'ohlcv.csv').exists():
                raise ValueError('CSV exists but manifest declares no loaded symbols')
            result['issues'] = list(manifest.get('issues') or ['No validated market observations.'])
            return result
        if not isinstance(manifest.get('retrieved_at_utc'), str):
            raise ValueError('Missing retrieval timestamp')
        retrieval = datetime.fromisoformat(manifest['retrieved_at_utc'].replace('Z', '+00:00'))
        if retrieval.utcoffset() is None or retrieval.utcoffset().total_seconds() != 0:
            raise ValueError('retrieved_at_utc must have UTC timezone')
        sources = manifest.get('upstream_sources')
        if not isinstance(sources, list) or not sources:
            raise ValueError('Missing upstream sources')
        registry = {}
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get('id'), str) or not source.get('id') or not isinstance(source.get('usage_note'), str) or not source.get('usage_note'):
                raise ValueError('Missing source id or usage note')
            if not _url(source.get('source_url', '')) or not _url(source.get('documentation_url', '')):
                raise ValueError('Missing source URL or documentation URL')
            registry[source['id']] = source
        if manifest.get('adjustment_policy') not in ('provider_adjusted', 'unadjusted'):
            raise ValueError('Adjustment policy not established')
        checksums = manifest.get('file_sha256') or {}
        for name in checksums:
            if name not in ('ohlcv.csv', 'index_ohlcv.csv'):
                raise ValueError('Unrecognized dataset file')
            path = folder / name
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != checksums[name]:
                raise ValueError(f'Checksum mismatch: {name}')
        if 'ohlcv.csv' not in checksums:
            raise ValueError('Missing equity checksum')
        rows, seen, grouped = [], set(), {}
        with (folder / 'ohlcv.csv').open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != COLUMNS:
                raise ValueError('CSV schema/order does not match contract')
            for line, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f'CSV row {line}: malformed columns')
                symbol = row['symbol']
                if symbol not in loaded:
                    raise ValueError(f'Unexpected symbol at row {line}')
                session = date.fromisoformat(row['date'])
                if session.isoformat() != row['date'] or session > cutoff or session.weekday() > 4:
                    raise ValueError(f'Invalid/future session at row {line}')
                key = (symbol, session)
                if key in seen:
                    raise ValueError(f'Duplicate symbol/date at row {line}')
                seen.add(key)
                o, h, l, c = [_number(row[k], k) for k in COLUMNS[2:6]]
                volume = _number(row['volume_shares'], 'volume_shares')
                if min(o, h, l, c) <= 0 or h < max(o, l, c) or l > min(o, h, c):
                    raise ValueError(f'Invalid OHLC at row {line}')
                if volume < 0 or volume != volume.to_integral_value():
                    raise ValueError(f'Invalid volume at row {line}')
                if row['turnover_vnd'] and _number(row['turnover_vnd'], 'turnover_vnd') < 0:
                    raise ValueError(f'Invalid turnover at row {line}')
                source = registry.get(row['upstream_source'])
                if not source or row['source_url'] != source['source_url']:
                    raise ValueError(f'Unregistered source URL at row {line}')
                if row['price_adjustment'] != manifest['adjustment_policy']:
                    raise ValueError(f'Mixed adjustment policy at row {line}')
                grouped.setdefault(symbol, []).append(row['date'])
                rows.append(row)
        if not rows or set(grouped) != set(loaded):
            raise ValueError('Empty CSV or declared symbol has no rows')
        coverage = {s: {'rows': len(ds), 'first_available_session': min(ds),
                        'last_available_session': max(ds)} for s, ds in sorted(grouped.items())}
        if coverage != manifest.get('coverage_by_symbol') or manifest.get('row_count') != len(rows):
            raise ValueError('Manifest coverage/count does not match CSV')
        if rows != sorted(rows, key=lambda r: (r['symbol'], r['date'])):
            raise ValueError('CSV rows must be sorted by symbol/date')
        lookback = manifest.get('lookback_sessions_requested')
        if not isinstance(lookback, int) or isinstance(lookback, bool) or not 1 <= lookback <= 1000:
            raise ValueError('Invalid lookback')
        partial = set(loaded) != set(requested) or any(c['rows'] < lookback or c['last_available_session'] < cutoff.isoformat() for c in coverage.values())
        # Optional index CSV is intentionally not ingested by this equity contract.
        # Reject it unless a separately versioned contract has been implemented.
        if (folder / 'index_ohlcv.csv').exists():
            raise ValueError('Index file present without supported points contract')
        result.update(passed=True, status='PARTIAL' if partial else 'VALID', rows=rows,
                      coverage_by_symbol=coverage, issues=list(manifest.get('issues') or []))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        result['issues'] = [str(exc)]
    return result
