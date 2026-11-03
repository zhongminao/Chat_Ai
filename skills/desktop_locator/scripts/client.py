"""Fixed stdin-to-loopback CLI; no file access or desktop control."""
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("health", "locate"):
        raise SystemExit("usage: client.py health|locate")
    port = int(os.environ.get("DESKTOP_LOCATOR_PORT", "18765"))
    if not 1 <= port <= 65535:
        raise SystemExit("invalid port")
    method = sys.argv[1]
    body = sys.stdin.buffer.read(2 * 1024 * 1024 + 1) if method == "locate" else None
    if body is not None and len(body) > 2 * 1024 * 1024:
        raise SystemExit("request exceeds 2 MiB")
    req = Request(f"http://127.0.0.1:{port}/{method}", body,
                  {"Content-Type": "application/json"} if body is not None else {},
                  method="POST" if body is not None else "GET")
    try:
        with urlopen(req, timeout=90) as response:
            sys.stdout.buffer.write(response.read() + b"\n")
    except HTTPError as exc:
        sys.stderr.buffer.write(exc.read() + b"\n")
        raise SystemExit(1) from None
    except URLError as exc:
        raise SystemExit(f"locator unavailable: {exc.reason}") from None


if __name__ == "__main__":
    main()
