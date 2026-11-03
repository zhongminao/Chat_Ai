"""One-shot desktop locator workflow: own service lifetime, no mouse actions."""
from __future__ import annotations
import argparse
import base64
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
import importlib.util
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE = 1024 * 1024
spec = importlib.util.spec_from_file_location("desktop_locator_service", ROOT / "service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def run(image_path: Path, target: str | None, *, selector: dict | None = None,
        nodes: list | None = None, output: Path | None = None) -> dict:
    raw = image_path.read_bytes()
    if len(raw) > MAX_IMAGE:
        raise ValueError("screenshot exceeds locator limit (1 MiB)")
    method = "ax" if selector is not None else "vision"
    payload = {"method": method, "screenshot_base64": base64.b64encode(raw).decode("ascii")}
    if method == "ax":
        payload.update({"selector": selector, "nodes": nodes})
    else:
        payload["target"] = target
    body = json.dumps(payload).encode("utf-8")
    if len(body) > service.MAX_BODY:
        raise ValueError("request exceeds 2 MiB")
    # Bind localhost on an ephemeral port; shut down in finally even on model errors.
    with ThreadingHTTPServer(("127.0.0.1", 0), service.LocatorHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/locate"
            req = Request(url, body, {"Content-Type": "application/json"}, method="POST")
            try:
                with urlopen(req, timeout=90) as response:
                    result = json.load(response)
            except HTTPError as exc:
                raise RuntimeError(f"locator rejected: {exc.code} {exc.read().decode('utf-8', 'replace')}") from exc
        finally:
            server.shutdown()
            thread.join(timeout=3)
    if output:
        with Image.open(image_path) as source:
            marked = source.convert("RGB")
        x, y = result["x"], result["y"]
        draw = ImageDraw.Draw(marked)
        draw.ellipse((x - 11, y - 11, x + 11, y + 11), outline="red", width=4)
        draw.line((x - 17, y, x + 17, y), fill="red", width=2)
        draw.line((x, y - 17, x, y + 17), fill="red", width=2)
        marked.save(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Locate only: start local service, locate, then stop")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--target", help="vision target description (not a desktop action)")
    parser.add_argument("--ax-json", type=Path, help="JSON file containing selector and nodes")
    parser.add_argument("--annotated", type=Path, help="save annotated result image")
    parser.add_argument("--vision-retries", type=int, choices=range(0,4), default=1, help="retry inference-only 502 failure, never click")
    args = parser.parse_args()
    if bool(args.target) == bool(args.ax_json):
        parser.error("provide exactly one of --target and --ax-json")
    ax = json.loads(args.ax_json.read_text(encoding="utf-8")) if args.ax_json else None
    for attempt in range(args.vision_retries + 1):
        try:
            result = run(args.image, args.target,
                         selector=ax["selector"] if ax else None,
                         nodes=ax["nodes"] if ax else None, output=args.annotated)
            break
        except RuntimeError as exc:
            if ax or attempt == args.vision_retries or "locator rejected: 502" not in str(exc):
                raise
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
