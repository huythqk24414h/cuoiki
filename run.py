"""Local-only Python HTTP application; zero third-party dependencies or database imports."""
import argparse
import json
import os
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from src.finance import calculate, ContractError
from src.sources import get_source
from src.eod_analytics import demo_payload
from src.market import market_payload
from src.ssi_stream import LIVE, start_live_stream
from src.security import redact_public

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'web'
DEMO = ROOT / 'data' / 'demo'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log user payloads or credentials.
        pass

    def respond(self, data, status=200):
        raw = json.dumps(redact_public(data), ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.headers_common('application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
        elapsed=round((time.monotonic()-getattr(self,'_request_started',time.monotonic()))*1000,1)
        if elapsed>=1000 or status>=400:
            try:
                folder=ROOT/'data/runtime_logs';folder.mkdir(exist_ok=True)
                with (folder/'http.jsonl').open('a',encoding='utf-8') as log:
                    log.write(json.dumps({'route':urlsplit(self.path).path,'status':status,'elapsed_ms':elapsed})+'\n')
            except OSError:pass

    def headers_common(self, content_type):
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")

    def do_GET(self):
        self._request_started=time.monotonic()
        parsed = urlsplit(self.path)
        route = parsed.path
        if route=='/api/market/board-stream':
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':
                return self.respond({'error':'Nguồn SSE không được phép.'},403)
            from src.quote_board import board_payload
            first,code=board_payload(parsed.query)
            if code!=200:return self.respond(first,code)
            self.send_response(200);self.headers_common('text/event-stream; charset=utf-8')
            self.send_header('Connection','close');self.end_headers()
            try:
                for i in range(25):
                    payload=first if i==0 else board_payload(parsed.query)[0]
                    block='event: board\ndata: '+json.dumps(redact_public(payload),ensure_ascii=False,allow_nan=False)+'\n\n'
                    self.wfile.write(block.encode());self.wfile.flush()
                    time.sleep(1)
                self.wfile.write(b'event: cycle\ndata: {}\n\n');self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError,OSError):pass
            self.close_connection=True
            return
        if route == '/api/health' or route.startswith('/api/market/'):
            payload, status = market_payload(route, parsed.query)
            return self.respond(payload, status)
        if route == '/api/status':
            return self.respond(get_source().health())
        if route == '/api/protocol':
            return self.respond({'version': 'draft-0.1', 'locked': False, 'study_started': False,
                                 'evaluation': 'not_available', 'thresholds': None})
        if route.startswith('/api/demo/'):
            payload, status = demo_payload(route, parsed.query, DEMO)
            return self.respond(payload, status)
        files = {'/intraday-ui.js':('intraday-ui.js','text/javascript; charset=utf-8'), '/welcome-fx.js':('welcome-fx.js','text/javascript; charset=utf-8'),
                 '/assets/landing.png':('assets/landing.png','image/png'),
                 '/demo-login.js':('demo-login.js','text/javascript; charset=utf-8'),
                 '/quote-board.js': ('quote-board.js','text/javascript; charset=utf-8'),
                 '/formula.js':('formula.js','text/javascript; charset=utf-8'),
                 '/vendor/katex/katex.js':('vendor/katex/katex.js','text/javascript; charset=utf-8'),
                 '/vendor/lightweight-charts.js': ('vendor/lightweight-charts.js','text/javascript; charset=utf-8'),
                 '/vendor/echarts.js': ('vendor/echarts.js','text/javascript; charset=utf-8'),
                 '/chart-kit.js': ('chart-kit.js','text/javascript; charset=utf-8'),
                 '/': ('index.html', 'text/html; charset=utf-8'),
                 '/market-state.js': ('market-state.js', 'text/javascript; charset=utf-8'),
                 '/market-ui.js': ('market-ui.js', 'text/javascript; charset=utf-8'),
                 '/depth-chart.js': ('depth-chart.js', 'text/javascript; charset=utf-8'),
                 '/themes.js': ('themes.js', 'text/javascript; charset=utf-8'),
                 '/calculator-core.js': ('calculator-core.js', 'text/javascript; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/symbol-analysis.js': ('symbol-analysis.js', 'text/javascript; charset=utf-8'),
                 '/vn30-brief.js': ('vn30-brief.js', 'text/javascript; charset=utf-8'),
                 '/eod-ui.js': ('eod-ui.js', 'text/javascript; charset=utf-8'),
                 '/theme-tokens.css': ('theme-tokens.css', 'text/css; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8'),
                 '/book.svg': ('book.svg', 'image/svg+xml')}
        if route not in files:
            return self.respond({'error': 'Không tìm thấy.'}, 404)
        filename, mime = files[route]
        raw = (STATIC / filename).read_bytes()
        self.send_response(200)
        self.headers_common(mime)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        # Block cross-origin requests, including HTML form submissions from other sites.
        origin = self.headers.get('Origin')
        expected = f'http://127.0.0.1:{self.server.server_port}'
        if origin and origin != expected:
            return self.respond({'error': 'Nguồn yêu cầu không được phép.'}, 403)
        if urlsplit(self.path).path != '/api/calculate':
            return self.respond({'error': 'Chức năng chưa được mở.'}, 404)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond({'error': 'Cần Content-Type application/json.'}, 415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16000:
                return self.respond({'error': 'Giới hạn đầu vào 16 KB.'}, 413)
            payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            result = calculate(payload)
            from decimal import Decimal, localcontext
            with localcontext() as context:
                context.prec = 64
                result['total_depth_vnd'] = str(Decimal(result['bid_depth_vnd']) + Decimal(result['ask_depth_vnd']))
        except (ContractError, ValueError, TypeError, UnicodeDecodeError):
            import sys
            error = sys.exception()
            return self.respond({'error': str(error) if isinstance(error, ContractError) else 'JSON không hợp lệ.'}, 422)
        return self.respond(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8792)
    args = parser.parse_args()
    get_source(os.environ.get('DATA_SOURCE', 'none'))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    start_live_stream()
    print(f'Liquidity Lab: http://127.0.0.1:{args.port} | database disabled', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LIVE.stop()
        server.server_close()


if __name__ == '__main__':
    main()
