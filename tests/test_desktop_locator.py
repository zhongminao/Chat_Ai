"""Isolated locator tests: no actual desktop, model, network outside loopback or clicks."""
import base64
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection
from io import BytesIO
import importlib.util
import json
import hashlib
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from PIL import Image

SERVICE = Path(__file__).resolve().parents[1] / "skills" / "desktop_locator" / "service.py"
spec = importlib.util.spec_from_file_location("desktop_locator_service", SERVICE)
locator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locator)


def screenshot(w=2000, h=1000, fmt="PNG"):
    stream = BytesIO()
    Image.new("RGB", (w, h), "white").save(stream, format=fmt)
    return base64.b64encode(stream.getvalue()).decode()


class LocatorTest(unittest.TestCase):
    def setUp(self):
        self.ax = {"method": "ax", "window_size": {"width": 200, "height": 100},
                   "selector": {"name": "Save", "role": "button"},
                   "nodes": [{"name": "Save", "role": "button",
                              "bbox": {"x": 40, "y": 20, "width": 40, "height": 20}}]}

    def test_ax_exact_unique(self):
        result = locator.locate(self.ax)
        self.assertEqual((result["x"], result["y"]), (60, 30))
        self.assertEqual(result["source"], "ax_exact_unique")
        self.assertIsNone(result["screenshot_token"])
        self.ax["nodes"].append({"name": "save", "role": "button", "bbox": {}})
        self.assertEqual(locator.locate(self.ax)["x"], 60)
        self.ax["nodes"].append(dict(self.ax["nodes"][0]))
        with self.assertRaisesRegex(locator.LocatorError, "ambiguous"):
            locator.locate(self.ax)

    def test_ax_invalid_bbox_and_window(self):
        for bbox in ({"x": 190, "y": 0, "width": 40, "height": 10},
                     {"x": True, "y": 0, "width": 40, "height": 10},
                     {"x": 0, "y": 0, "width": 0, "height": 10}):
            self.ax["nodes"][0]["bbox"] = bbox
            with self.assertRaises(locator.LocatorError):
                locator.locate(self.ax)
        self.ax["window_size"]["width"] = 5000
        with self.assertRaises(locator.LocatorError):
            locator.locate(self.ax)

    def test_image_token_and_validation(self):
        self.ax["screenshot_base64"] = screenshot(200, 100)
        first = locator.locate(self.ax)
        second = locator.locate(self.ax)
        self.assertTrue(first["screenshot_token"])
        self.assertEqual(first["screenshot_token"], second["screenshot_token"])
        self.assertEqual(first["screenshot_token"], hashlib.sha256(base64.b64decode(self.ax["screenshot_base64"])).hexdigest())
        self.ax["window_size"]["width"] = 199
        with self.assertRaises(locator.LocatorError):
            locator.locate(self.ax)
        self.ax["screenshot_base64"] = base64.b64encode(b"invalid").decode()
        with self.assertRaises(locator.LocatorError):
            locator.locate(self.ax)
        self.ax["screenshot_base64"] = "A" * 1_500_000
        with self.assertRaises(locator.LocatorError):
            locator.locate(self.ax)

    def test_mock_vision_and_scaling(self):
        seen = []
        def fake(target, image, **settings):
            seen.append((target, image.size, settings["model"]))
            sw, sh = 1024, 512
            return locator.validate_model_result({"x": 512, "y": 256,
                                                   "confidence": 0.93, "uncertain": False},
                                                  sw, sh, *image.size)
        result = locator.locate({"method": "vision", "target": "Save button",
                                 "screenshot_base64": screenshot()}, vision=fake, model="mock")
        self.assertEqual((result["x"], result["y"]), (1000, 500))
        self.assertEqual(result["source"], "vision_openai_compatible")
        self.assertTrue(result["screenshot_token"])
        self.assertEqual(seen[0], ("Save button", (2000, 1000), "mock"))

    def test_vision_fail_closed(self):
        valid = {"x": 10, "y": 20, "confidence": 0.9, "uncertain": False}
        for patch in ({"x": 1024}, {"x": -1}, {"x": 5.2}, {"x": True},
                      {"confidence": 0.79}, {"confidence": float("nan")},
                      {"uncertain": True}, {"uncertain": "false"}, {"alternatives": []}):
            with self.subTest(patch=patch), self.assertRaises(locator.LocatorError):
                locator.validate_model_result(valid | patch, 1024, 512, 2000, 1000)
        for raw in (b'{"x": 1, "x": 2}', b'{"x": NaN}', b'```json\n{}\n```'):
            with self.assertRaises(locator.LocatorError):
                locator.object_json(raw)
        with self.assertRaises(locator.LocatorError):
            locator.locate({"method": "vision", "target": "Save", "screenshot_base64": ""})

    def test_vision_bbox_normalized_and_fail_closed(self):
        good = {"bbox_2d": [815, 823, 953, 900], "label": "Save button"}
        self.assertEqual(locator.validate_model_bbox(good, "Save button", 960, 540), (848, 465, None))
        for bad in ({"bbox_2d": None, "label": "Save button"},
                    {"bbox_2d": [815, 823, 953, 900], "label": "another button"},
                    {"bbox_2d": [815, 823, 1001, 900], "label": "Save button"},
                    {"bbox_2d": [900, 823, 815, 900], "label": "Save button"},
                    {"bbox_2d": [815, 823, 953, 900], "label": "Save button", "confidence": .99}):
            with self.subTest(bad=bad), self.assertRaises(locator.LocatorError):
                locator.validate_model_bbox(bad, "Save button", 960, 540)

    def test_vision_protocol_mock_transport_and_scaled_image(self):
        class FakeResponse:
            def __init__(self, content, finish="stop"):
                self.body = json.dumps({"choices": [{"finish_reason": finish,
                    "message": {"content": content}}]}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                return self.body

        requests = []
        def mock_urlopen(req, timeout):
            requests.append(json.loads(req.data))
            return FakeResponse('{"bbox_2d":[450,450,550,550],"label":"Save"}')
        with patch.object(locator, "urlopen", mock_urlopen):
            coords = locator.call_vision("Save", Image.new("RGB", (2000, 1000)),
                                         base_url="http://mock/v1", model="mock", api_key="fake")
        self.assertEqual(coords, (1000, 500, None))
        image_url = requests[0]["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        with Image.open(BytesIO(base64.b64decode(image_url.split(",", 1)[1]))) as image:
            self.assertEqual(image.size, (1024, 512))
        for content, finish in (("```json\n{}\n```", "stop"),
                                ('{"bbox_2d":[450,450,550,550],"label":"Save"}', "length"),
                                ('{"bbox_2d":[450,450,1050,550],"label":"Save"}', "stop")):
            with self.subTest(content=content, finish=finish), patch.object(locator, "urlopen",
                    return_value=FakeResponse(content, finish)), self.assertRaises(locator.LocatorError):
                locator.call_vision("Save", Image.new("RGB", (2000, 1000)),
                                    base_url="http://mock/v1", model="mock", api_key="fake")

    def test_http_loopback_health_body_limit_ax_and_mock_vision(self):
        class Handler(locator.LocatorHandler):
            vision = staticmethod(lambda target, image, **kw: (3, 4, 0.95))
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                self.assertEqual(json.load(urlopen(base + "/health"))["status"], "ok")
                body = json.dumps(self.ax).encode()
                req = Request(base + "/locate", body, {"Content-Type": "application/json"})
                self.assertEqual(json.load(urlopen(req))["x"], 60)
                req = Request(base + "/locate", json.dumps({"method": "vision", "target": "Save",
                               "screenshot_base64": screenshot(30, 20, "WEBP")}).encode(),
                               {"Content-Type": "application/json"})
                self.assertEqual(json.load(urlopen(req))["y"], 4)
                # Send headers only: the server rejects oversized requests before reading a body.
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                try:
                    connection.putrequest("POST", "/locate")
                    connection.putheader("Content-Type", "application/json")
                    connection.putheader("Content-Length", str(locator.MAX_BODY + 1))
                    connection.endheaders()
                    self.assertEqual(connection.getresponse().status, 413)
                finally:
                    connection.close()
            finally:
                server.shutdown()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
