"""Loopback-only, stateless localization HTTP API. No desktop control or file inputs."""
from __future__ import annotations

import base64
import binascii
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import math
import os
import hashlib
from urllib.request import Request, urlopen

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BODY = 2 * 1024 * 1024
MAX_IMAGE = 1024 * 1024
MAX_PIXELS = 8_000_000
MAX_SIDE = 4096
MAX_NODES = 1000
VISION_SIDE = 1024
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class LocatorError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-standard JSON number")


def object_json(raw: bytes):
    try:
        obj = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (UnicodeError, ValueError) as exc:
        raise LocatorError("invalid JSON") from exc
    if type(obj) is not dict:
        raise LocatorError("JSON object required")
    return obj


def dimension(value):
    if type(value) is not int or not 1 <= value <= MAX_SIDE:
        raise LocatorError("invalid window dimension")
    return value


def window_size(value):
    if type(value) is not dict or set(value) != {"width", "height"}:
        raise LocatorError("invalid window_size")
    w, h = dimension(value["width"]), dimension(value["height"])
    if w * h > MAX_PIXELS:
        raise LocatorError("window too large")
    return w, h


def image_from_base64(data):
    if type(data) is not str or not data or len(data) > (MAX_IMAGE + 2) // 3 * 4 + 4:
        raise LocatorError("screenshot_base64 exceeds limit or is invalid")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LocatorError("invalid screenshot base64") from exc
    if len(raw) > MAX_IMAGE:
        raise LocatorError("image exceeds 1 MiB")
    try:
        with Image.open(BytesIO(raw)) as im:
            if im.format not in {"PNG", "JPEG", "WEBP"}:
                raise LocatorError("screenshot must be PNG, JPEG, or WebP")
            w, h = im.size
            if not 1 <= w <= MAX_SIDE or not 1 <= h <= MAX_SIDE or w * h > MAX_PIXELS:
                raise LocatorError("image dimensions exceed limit")
            im.load()
            # Browser/window screenshot orientation is the decoded raster orientation.
            image = ImageOps.exif_transpose(im).convert("RGB")
            if image.size != (w, h):
                raise LocatorError("rotated EXIF images are unsupported")
            return image, hashlib.sha256(raw).hexdigest()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise LocatorError("invalid screenshot image") from exc


def match_ax(nodes, selector, width, height):
    if type(selector) is not dict or set(selector) != {"name", "role"} or any(
        type(selector[k]) is not str or not selector[k].strip() or len(selector[k]) > 256
        for k in ("name", "role")
    ):
        raise LocatorError("selector must contain exact name and role")
    if type(nodes) is not list or not 1 <= len(nodes) <= MAX_NODES:
        raise LocatorError("nodes must contain 1 to 1000 entries")
    hits = []
    for node in nodes:
        if type(node) is not dict:
            raise LocatorError("invalid AX node")
        if node.get("name") == selector["name"] and node.get("role") == selector["role"]:
            hits.append(node)
    if len(hits) != 1:
        raise LocatorError("AX selector ambiguous" if hits else "AX selector not found", 422)
    box = hits[0].get("bbox")
    if type(box) is not dict or set(box) != {"x", "y", "width", "height"}:
        raise LocatorError("invalid AX bbox")
    vals = [box[k] for k in ("x", "y", "width", "height")]
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in vals):
        raise LocatorError("invalid AX bbox")
    x, y, w, h = vals
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise LocatorError("AX bbox out of bounds", 422)
    return min(width - 1, math.floor(x + w / 2)), min(height - 1, math.floor(y + h / 2))


def validate_model_result(value, scaled_width, scaled_height, width, height):
    if type(value) is not dict or set(value) != {"x", "y", "confidence", "uncertain"}:
        raise LocatorError("vision response must be strict coordinate JSON", 422)
    x, y, confidence = value["x"], value["y"], value["confidence"]
    if (type(x) is not int or type(y) is not int or
            type(confidence) not in (int, float) or not math.isfinite(confidence) or
            type(value["uncertain"]) is not bool):
        raise LocatorError("invalid vision coordinate fields", 422)
    if value["uncertain"] or not 0.8 <= confidence <= 1:
        raise LocatorError("vision result uncertain", 422)
    if not 0 <= x < scaled_width or not 0 <= y < scaled_height:
        raise LocatorError("vision coordinates out of bounds", 422)
    px, py = math.floor((x + 0.5) * width / scaled_width), math.floor((y + 0.5) * height / scaled_height)
    if not 0 <= px < width or not 0 <= py < height:
        raise LocatorError("mapped vision coordinates out of bounds", 422)
    return px, py, float(confidence)


def validate_model_bbox(value, target, width, height):
    """Qwen's bbox_2d is 0..1000 normalized, NOT image pixel coordinates."""
    if type(value) is not dict or set(value) != {"bbox_2d", "label"}:
        raise LocatorError("vision response must contain bbox_2d and label", 422)
    box, label = value["bbox_2d"], value["label"]
    if type(label) is not str or label.strip().casefold() != target.strip().casefold():
        raise LocatorError("vision label does not match target", 422)
    if type(box) is not list or len(box) != 4 or any(type(v) is not int or not 0 <= v <= 1000 for v in box):
        raise LocatorError("missing or invalid vision bbox", 422)
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        raise LocatorError("empty vision bbox", 422)
    x, y = int((left + right) * width / 2000), int((top + bottom) * height / 2000)
    if not 0 <= x < width or not 0 <= y < height:
        raise LocatorError("mapped vision bbox out of bounds", 422)
    # No calibrated confidence available from this model. Never invent one.
    return x, y, None


def call_vision(target: str, image: Image.Image, *, base_url: str, model: str, api_key: str):
    width, height = image.size
    scaled = image.copy()
    scaled.thumbnail((VISION_SIDE, VISION_SIDE), Image.Resampling.LANCZOS)
    sw, sh = scaled.size
    buffer = BytesIO()
    scaled.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    payload = {"model": model, "temperature": 0, "max_tokens": 512,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": (
                       "Locate ONLY this target in the attached image: " + target +
                       f". Image pixel size is {sw}x{sh}. Return ONLY a JSON object with exactly "
                       'two fields: bbox_2d=[left,top,right,bottom] in normalized 0..1000 '
                       'coordinates, and label exactly matching the given target text. '
                       'If target is missing, ambiguous, partly hidden or uncertain, '
                       'set bbox_2d to null. Never guess or return multiple locations.')},
                   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
               ]}]}
    req = Request(base_url.rstrip("/") + "/chat/completions",
                  data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
                  method="POST")
    try:
        with urlopen(req, timeout=60) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise LocatorError("vision response too large", 502)
        response = object_json(raw)
        choice = response["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ValueError("unfinished or refused vision response")
        content = choice["message"]["content"]
        if type(content) is not str:
            raise ValueError("non-text vision content")
        parsed = object_json(content.encode())
    except LocatorError as exc:
        if exc.status == 400:
            raise LocatorError("invalid vision JSON", 502) from exc
        raise
    except (OSError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LocatorError("vision API unavailable or invalid response", 502) from exc
    return validate_model_bbox(parsed, target, width, height)


def locate(request, vision=call_vision, *, base_url=None, model=None, api_key=None):
    if type(request) is not dict:
        raise LocatorError("JSON object required")
    if set(request) - {"method", "selector", "nodes", "window_size", "screenshot_base64", "target"}:
        raise LocatorError("unexpected request fields")
    method = request.get("method", "ax" if "nodes" in request else "vision")
    if method not in ("ax", "vision"):
        raise LocatorError("method must be ax or vision")
    screenshot = request.get("screenshot_base64")
    image, token = image_from_base64(screenshot) if screenshot is not None else (None, None)
    size = window_size(request["window_size"]) if "window_size" in request else None
    if image is not None:
        if size is not None and size != image.size:
            raise LocatorError("window_size differs from screenshot dimensions")
        size = image.size
    if method == "ax":
        if size is None:
            raise LocatorError("AX-only requests require window_size")
        if "target" in request:
            raise LocatorError("target is only valid for vision")
        x, y = match_ax(request.get("nodes"), request.get("selector"), *size)
        confidence, source = 1.0, "ax_exact_unique"
    else:
        if image is None or "nodes" in request or "selector" in request:
            raise LocatorError("vision requires screenshot, not AX inputs")
        target = request.get("target")
        if type(target) is not str or not target.strip() or len(target) > 500:
            raise LocatorError("vision target must be 1 to 500 characters")
        x, y, confidence = vision(target, image,
                                  base_url=base_url or os.environ.get("DESKTOP_LOCATOR_VISION_BASE_URL", "http://192.168.250.1:18082/v1"),
                                  model=model or os.environ.get("DESKTOP_LOCATOR_VISION_MODEL", "Qwen3.6-35B-A3B"),
                                  api_key=api_key or os.environ.get("DESKTOP_LOCATOR_VISION_API_KEY", "EMPTY"))
        source = "vision_openai_compatible"
    return {"x": x, "y": y, "confidence": confidence, "source": source,
            "screenshot_token": token, "window_size": {"width": size[0], "height": size[1]}}


class LocatorHandler(BaseHTTPRequestHandler):
    # Replace for isolated tests; production always uses the real call_vision.
    vision = staticmethod(call_vision)

    def _reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"status": "ok"})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/locate":
            return self._reply(404, {"error": "not found"})
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self._reply(415, {"error": "Content-Type must be application/json"})
        lengths = self.headers.get_all("Content-Length", [])
        try:
            if self.headers.get("Transfer-Encoding"):
                raise LocatorError("chunked requests are unsupported")
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise LocatorError("Content-Length required")
            length = int(lengths[0])
            if length > MAX_BODY:
                raise LocatorError("request body exceeds 2 MiB", 413)
            body = self.rfile.read(length)
            if len(body) != length:
                raise LocatorError("truncated request")
            result = locate(object_json(body), vision=self.vision)
            self._reply(200, result)
        except LocatorError as exc:
            self._reply(exc.status, {"error": str(exc)})

    def log_message(self, format, *args):
        pass  # Do not log potentially sensitive user-supplied paths or targets.


def main():
    port = int(os.environ.get("DESKTOP_LOCATOR_PORT", "18765"))
    if not 1 <= port <= 65535:
        raise SystemExit("invalid port")
    with ThreadingHTTPServer(("127.0.0.1", port), LocatorHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
