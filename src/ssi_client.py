"""SSI V3 market-data boundary. No trading/account/OTP operations exposed."""
from datetime import datetime
import logging
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'/api/v3/data/ohlc', '/api/v3/data/securitiesByBoard'}
ALLOWED.update({'/api/v3/data/indexList', '/api/v3/data/indexSummary', '/api/v3/data/securitiesSummary'})


def credentials():
    values = {}
    path = ROOT / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip() in ('SSI_API_KEY', 'SSI_API_SECRET', 'SSI_CLIENT_ID'):
                values[key.strip()] = value.strip().strip('"').strip("'")
    return {key: os.environ.get(key, values.get(key, '')) for key in
            ('SSI_API_KEY', 'SSI_API_SECRET', 'SSI_CLIENT_ID')}


def sdk():
    local = ROOT / '.tools/ssi'
    if local.is_dir():
        sys.path.insert(0, str(local))
    from ssi_sdk import Auth, Config, Stream
    return Auth, Config, Stream


def date_range(start, end, daily=False):
    first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if first.utcoffset() is None or last.utcoffset() is None:
        raise ValueError('Require aware dates in Vietnam timezone.')
    from datetime import timedelta
    if first.utcoffset() != timedelta(hours=7) or last.utcoffset() != timedelta(hours=7) or first > last:
        raise ValueError('Invalid Vietnam range.')
    fmt = '%Y/%m/%d' if daily else '%Y/%m/%d %H:%M:%S'
    return first.strftime(fmt), last.strftime(fmt)


def safe_error(error):
    code = str(getattr(error, 'code', '') or '')
    return {'error_type': type(error).__name__, 'http_status': getattr(error, 'status_code', None),
            'code': code if re.fullmatch(r'[A-Za-z0-9_]{0,40}', code) else 'REDACTED'}


class SSIReadonly:
    def __init__(self):
        keys = credentials()
        if not keys['SSI_API_KEY'] or not keys['SSI_API_SECRET']:
            raise ValueError('BLOCKED_CREDENTIALS')
        Auth, Config, _ = sdk()
        logging.getLogger('ssi_sdk').setLevel(logging.CRITICAL)
        self.auth = Auth(Config(api_key=keys['SSI_API_KEY'], api_secret=keys['SSI_API_SECRET'],
                               client_id=keys['SSI_CLIENT_ID'], timeout_ms=15000, max_retries=1,
                               rate_limit_per_second=5, log_level='CRITICAL', auto_reconnect=True))
        self.evidence = []
        # Pinned SDK3.3.2 uses httpx. Observe only method/path/status, never bodies/URLs/headers with auth.
        def observe(response):
            path=response.request.url.path
            if path in ALLOWED or path=='/api/v3/auth/token':
                item={'method':response.request.method,'endpoint':path,'http_status':response.status_code}
                for header in ['x-request-id','x-ratelimit-limit','x-ratelimit-remaining']:
                    value=response.headers.get(header,'')
                    if value and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',value):item[header]=value
                self.evidence.append(item)
        self.auth.rest_client._get_client().event_hooks['response'].append(observe)
        self.last_call = 0

    def authenticate(self):
        self.auth.authenticate()  # No OTP: Market Data only. Never persist token.

    def get(self, endpoint, params):
        if endpoint not in ALLOWED:
            raise ValueError('Endpoint outside readonly allowlist')
        time.sleep(max(0, .25 - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()
        return self.auth.rest_client.get(endpoint, params=params)

    def ohlc(self, symbol, start, end, page=1, size=100, daily=False):
        if not re.fullmatch(r'[A-Z0-9 _-]{1,40}', symbol) or not page >= 1 or not 1 <= size <= 1000:
            raise ValueError('Invalid market query')
        first, last = date_range(start, end, daily)
        return self.get('/api/v3/data/ohlc', {'symbol': symbol, 'from': first, 'to': last,
                       'timeFrame': '1d', 'pageIndex': page, 'pageSize': size})

    def close(self):
        self.auth.close()
