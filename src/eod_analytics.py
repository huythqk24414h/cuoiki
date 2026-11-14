"""Pure EOD descriptions and local snapshot API payloads; never contacts a provider.

Prices retain their provider-adjusted, as-retrieved policy. Historical calculations
use preceding observations only; this is not a point-in-time corporate-action feed.
"""
import calendar
import json
from datetime import date, timedelta
from decimal import Decimal, localcontext
from urllib.parse import parse_qs

from src.eod_snapshot import validate_snapshot

RANGES = ('1D','5D','1W','1M','3M','6M','YTD','1Y','3Y','5Y','MAX','ALL','CUSTOM')
RANK_METRICS = ('volume', 'return_pct', 'relative_volume20')


def _text(value):
    return format(value, 'f') if value is not None else None


def enrich_rows(rows):
    """Enrich one symbol without mutating input; outputs use exact decimal strings.

    relative_volume20 uses the previous 20 sessions, excluding the current volume.
    volatility20_pct is sample stddev of the last 20 close-to-close returns in
    percentage points, including this session. It is not annualized.
    """
    if len({r['symbol'] for r in rows}) > 1 or len({r['price_adjustment'] for r in rows}) > 1:
        raise ValueError('Không được trộn mã hoặc chính sách điều chỉnh giá.')
    ordered = sorted(rows, key=lambda r: r['date'])
    out, volumes, returns = [], [], []
    previous_close = None
    with localcontext() as context:
        context.prec = 28
        for row in ordered:
            close, volume = Decimal(row['close_vnd']), Decimal(row['volume_shares'])
            change = ((close / previous_close) - 1) * 100 if previous_close else None
            if change is not None:
                returns.append(change)
            average = sum(volumes[-20:]) / Decimal(20) if len(volumes) >= 20 else None
            relative = volume / average if average is not None and average > 0 else None
            # Days to sell 100,000 shares at 5% of the preceding 20-session ADV.
            capacity_days = Decimal(100000) / (average * Decimal('0.05')) if average else None
            volatility = None
            if len(returns) >= 20:
                sample = returns[-20:]
                mean = sum(sample) / Decimal(20)
                volatility = (sum((r - mean) ** 2 for r in sample) / Decimal(19)).sqrt()
            reasons = {}
            if change is None:
                reasons['return_pct'] = 'Cần giá đóng cửa của phiên trước trong snapshot.'
            if average is None:
                reasons['volume_avg20_previous'] = 'Cần đủ 20 phiên khối lượng trước phiên đang xem.'
                reasons['relative_volume20'] = reasons['volume_avg20_previous']
            elif average == 0:
                reasons['relative_volume20'] = 'Khối lượng trung bình 20 phiên trước bằng 0; không chia cho 0.'
            if capacity_days is None:
                reasons['liquidation_days_100k_5pct'] = 'Cần 20 phiên trước có khối lượng bình quân dương.'
            if volatility is None:
                reasons['volatility20_pct'] = 'Cần 20 lợi suất, tương ứng ít nhất 21 giá đóng cửa.'
            out.append({**row, 'return_pct': _text(change),
                        'volume_avg20_previous': _text(average), 'relative_volume20': _text(relative),
                        'liquidation_days_100k_5pct': _text(capacity_days),
                        'volatility20_pct': _text(volatility), 'missing_reasons': reasons})
            volumes.append(volume)
            previous_close = close
    return out


def select_range(rows, range_id):
    """Calendar-month range anchored at the symbol's actual last available session."""
    if range_id not in RANGES:
        raise ValueError('Khoảng ngày chỉ nhận 1M, 3M hoặc ALL.')
    if not rows:
        return [], None, None
    end = date.fromisoformat(rows[-1]['date'])
    if range_id in ('ALL','MAX','CUSTOM'):
        start = date.fromisoformat(rows[0]['date'])
    elif range_id == 'YTD':
        start = date(end.year, 1, 1)
    elif range_id in ('1D','5D'):
        count=1 if range_id=='1D' else 5
        start=date.fromisoformat(rows[max(0,len(rows)-count)]['date'])
    elif range_id=='1W':
        start=end-timedelta(days=7)
    else:
        absolute_month = end.year * 12 + end.month - 1 - {'1M':1,'3M':3,'6M':6,'1Y':12,'3Y':36,'5Y':60}[range_id]
        year, month0 = divmod(absolute_month, 12)
        month = month0 + 1
        start = date(year, month, min(end.day, calendar.monthrange(year, month)[1]))
    selected = [r for r in rows if r['date'] >= start.isoformat()]
    return selected, start.isoformat(), end.isoformat()


def _query(query, allowed):
    try:
        parsed = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=8)
    except ValueError as exc:
        raise ValueError('Tham số truy vấn không hợp lệ.') from exc
    if set(parsed) - set(allowed) or any(len(v) != 1 for v in parsed.values()):
        raise ValueError('Tham số lạ hoặc trùng lặp không được phép.')
    return {k: v[0] for k, v in parsed.items()}


def demo_payload(route, query, folder, snapshot_override=None):
    """Return (JSON payload, HTTP status). Reads and revalidates local files only."""
    routes = {
        '/api/demo/meta': (), '/api/demo/health': (),
        '/api/demo/ohlcv': ('symbol', 'range'), '/api/demo/summary': ('symbol', 'range'),
        '/api/demo/rankings': ('metric',),
    }
    if route not in routes:
        return {'error': 'Không tìm thấy.'}, 404
    try:
        params = _query(query, routes[route])
        if 'range' in params and params['range'] not in RANGES:
            raise ValueError('Khoảng ngày chỉ nhận 1M, 3M hoặc ALL.')
        if 'metric' in params and params['metric'] not in RANK_METRICS:
            raise ValueError('Chỉ xếp hạng theo volume, return_pct hoặc relative_volume20.')
        if 'symbol' in params and (not params['symbol'] or len(params['symbol']) > 12 or
                                  not params['symbol'].isascii() or not params['symbol'].isalnum()):
            raise ValueError('Mã không hợp lệ.')
    except ValueError as exc:
        return {'error': str(exc)}, 400
    try:
        snapshot = snapshot_override if snapshot_override is not None else validate_snapshot(folder)
        if snapshot['passed']:
            json.dumps(snapshot['manifest'], allow_nan=False)
    except (ValueError, TypeError, OSError, AttributeError):
        snapshot = {'passed': False, 'status': 'BLOCKED', 'issues': ['Không đọc được metadata snapshot.']}
    available = snapshot['passed']
    # Unvalidated metadata is never passed into JSON serialization or the UI.
    manifest = snapshot.get('manifest', {}) if available else {}
    common = {'available': available, 'status': snapshot['status'],
              'issues': snapshot.get('issues', []), 'asof_date': manifest.get('asof_date'),
              'timezone': manifest.get('asof_timezone', 'Asia/Ho_Chi_Minh'),
              'loaded_symbols': manifest.get('symbols_loaded', []),
              'coverage_by_symbol': snapshot.get('coverage_by_symbol', {}),
              'units': manifest.get('units', {}),
              'last_available_session': max((c['last_available_session'] for c in
                  snapshot.get('coverage_by_symbol', {}).values()), default=None)}
    if route in ('/api/demo/meta', '/api/demo/health'):
        return {**common, 'manifest': manifest, 'quality_gate': {'passed': available}}, 200
    if not available:
        return {**common, 'rows': [], 'summary': None,
                'message': 'Chưa có snapshot đã kiểm chứng. Chạy validator hoặc nhập dữ liệu hợp lệ.'}, 200
    symbols = common['loaded_symbols']
    if route == '/api/demo/rankings':
        metric = params.get('metric', 'volume')
        summaries = [enrich_rows([r for r in snapshot['rows'] if r['symbol'] == s])[-1] for s in symbols]
        field = 'volume_shares' if metric == 'volume' else metric
        summaries.sort(key=lambda r: (r[field] is not None, Decimal(r[field] or 0)), reverse=True)
        return {**common, 'metric': metric, 'scope': 'loaded_symbols', 'rows': summaries}, 200
    symbol = params.get('symbol', symbols[0])
    if symbol not in symbols:
        return {'error': 'Mã nằm ngoài danh sách snapshot đã kiểm chứng.'}, 400
    range_id = params.get('range', 'ALL')
    enriched = enrich_rows([r for r in snapshot['rows'] if r['symbol'] == symbol])
    selected, start, end = select_range(enriched, range_id)
    payload = {**common, 'symbol': symbol, 'range': range_id, 'range_start': start,
               'range_end': end, 'last_available_session': end,
               'summary': selected[-1] if selected else None}
    if route == '/api/demo/ohlcv':
        payload['rows'] = selected
    return payload, 200
