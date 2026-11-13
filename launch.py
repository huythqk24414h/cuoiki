"""Double-click entrypoint: start the local app, then open its browser page."""
import json
import threading
import webbrowser
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from run import Handler
from src.ssi_stream import LIVE, start_live_stream

URL = 'http://127.0.0.1:8792'


def existing_app():
    try:
        with urlopen(URL + '/api/status', timeout=2) as response:
            status = json.load(response)
        return (status.get('source') == 'none'
                and status.get('database') == 'disabled'
                and status.get('connection') == 'not_configured')
    except (OSError, ValueError, AttributeError):
        return False


def launch():
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8792), Handler)
    except OSError:
        if existing_app():
            webbrowser.open(URL)
            print('Liquidity Lab is already running. Opened its page.')
            return
        raise RuntimeError('Cannot start on port 8792. Close the application using this port and try again.')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    start_live_stream()
    print('Liquidity Lab is running: ' + URL, flush=True)
    print('Keep this window open. Close it or press Ctrl+C to stop.', flush=True)
    try:
        if not webbrowser.open(URL):
            print('Browser could not open automatically. Open ' + URL)
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        LIVE.stop()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    try:
        launch()
    except (OSError, RuntimeError) as error:
        print('ERROR: ' + str(error), flush=True)
        raise SystemExit(1)
