"""Skill task client: pass JSON on stdin, never write session state to disk."""
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description='Desktop task session API client')
    parser.add_argument('action', choices=['start_task', 'observe', 'plan', 'verify', 'action', 'finish', 'cancel', 'health'])
    parser.add_argument('--task-id', help='required for every action except start_task and health')
    args = parser.parse_args()
    if args.action not in ('start_task','health') and not args.task_id:
        parser.error('--task-id required')
    if args.action in ('start_task','health') and args.task_id:
        parser.error('--task-id is not valid for this action')
    port = int(os.environ.get('DESKTOP_TASK_PORT', '18766'))
    if not 1 <= port <= 65535: parser.error('invalid port')
    body = None if args.action == 'health' else sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if body is not None and len(body) > 2 * 1024 * 1024: parser.error('body too large')
    path = '/health' if args.action == 'health' else '/start_task' if args.action == 'start_task' else f'/task/{args.task_id}/{args.action}'
    req = Request(f'http://127.0.0.1:{port}{path}',body,
                  {'Content-Type':'application/json'} if body is not None else {},
                  method='GET' if body is None else 'POST')
    try:
        with urlopen(req, timeout=180) as response: sys.stdout.buffer.write(response.read() + b'\n')
    except HTTPError as exc:
        sys.stderr.buffer.write(exc.read() + b'\n'); raise SystemExit(1) from None
    except URLError as exc: raise SystemExit(f'task service unavailable: {exc.reason}') from None


if __name__ == '__main__': main()
