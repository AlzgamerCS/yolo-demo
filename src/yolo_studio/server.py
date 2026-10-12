"""Start the local YOLO Studio web server."""
import argparse
import threading
import webbrowser
import uvicorn
from .app import app

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1', help='Listening address; use 0.0.0.0 for trusted LAN access')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    if args.open_browser:
        browser_host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
        threading.Timer(2, lambda: webbrowser.open(f'http://{browser_host}:{args.port}')).start()
    uvicorn.run(app, host=args.host, port=args.port, access_log=False,
                proxy_headers=True, forwarded_allow_ips='127.0.0.1,::1',
                ws_max_size=2_000_004, ws_max_queue=1, ws_per_message_deflate=False)


if __name__ == "__main__":
    main()
