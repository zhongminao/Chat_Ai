"""Single invocation memory-only task session; service lifetime owned by skill."""
import argparse
import base64
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_service


def main():
    parser=argparse.ArgumentParser(description='Start skill service, observe once, report, finish, stop')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--goal', required=True)
    parser.add_argument('--window', required=True)
    parser.add_argument('--target', help='optional coordinate grounding target')
    args=parser.parse_args()
    raw=args.image.read_bytes()
    if len(raw)>task_service.locator.MAX_IMAGE:parser.error('screenshot exceeds 1 MiB')
    with ThreadingHTTPServer(('127.0.0.1',0),task_service.TaskHandler) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def post(path,data):
            with urlopen(Request(base+path,json.dumps(data).encode(),{'Content-Type':'application/json'}),timeout=180) as r:
                return json.load(r)
        task_id=None
        try:
            task_id=post('/start_task',{'goal':args.goal,'window':args.window,'allowed_actions':['observe']})['task_id']
            observation=post(f'/task/{task_id}/observe',{'window':args.window,'target':args.target,
                'screenshot_base64':base64.b64encode(raw).decode()})
            print(json.dumps({'observation':observation,'plan':post(f'/task/{task_id}/plan',{})},ensure_ascii=False))
        finally:
            try:
                if task_id:post(f'/task/{task_id}/finish',{})
            finally:
                server.shutdown();thread.join(timeout=3)

if __name__=='__main__':main()
