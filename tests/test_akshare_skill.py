"""Opt-in live lifecycle checks for the independently installed local Skill."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import sys
import unittest
import urllib.error
import urllib.request

from agent.tools.mcp.client import McpClient


@unittest.skipUnless(os.environ.get("AKSHARE_SKILL_INTEGRATION"),
                     "set AKSHARE_SKILL_INTEGRATION=1 after preparing Skill dependencies")
class AkshareSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill relocation with spaces ")
        self.addCleanup(self.temp.cleanup)
        original = Path(__file__).resolve().parents[1] / "skills/akshare"
        self.skill = Path(self.temp.name) / "another project/skills/akshare"
        shutil.copytree(original, self.skill, ignore=shutil.ignore_patterns("__pycache__"))
        self.script = self.skill / "scripts/service.py"
        self.addCleanup(lambda: self.manage("stop"))

    def manage(self, action, *arguments):
        result = subprocess.run(
            [sys.executable, str(self.script), action, *arguments], cwd="/tmp",
            capture_output=True, text=True, timeout=330)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_relocated_parallel_start_and_original_capabilities(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.manage, "start") for _ in range(2)]
            first, second = [future.result() for future in futures]
        self.assertEqual(first["pid"], second["pid"])
        self.assertEqual(first["url"], second["url"])
        self.assertEqual({first["reused"], second["reused"]}, {True, False})
        self.assertEqual(first["skill_dir"], str(self.skill))
        self.assertEqual(first["python"], sys.executable)
        argv = Path(f"/proc/{first['pid']}/cmdline").read_bytes().split(b"\0")
        self.assertEqual(argv[0].decode(), sys.executable)
        client = McpClient({"fixture": first["url"]})
        self.assertEqual(len(client.tools), 3)
        for name in ["stock_fund_flow_industry", "set_token", "get_proxies"]:
            with self.subTest(name=name):
                self.assertFalse(client.call("mcp_fixture_describe_interface",
                                             {"name": name}).is_error)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for route in ["/api/interfaces/set_token", "/docs"]:
            with opener.open(first["url"].removesuffix("/mcp") + route, timeout=5) as response:
                self.assertEqual(response.status, 200)
        self.manage("stop")
        self.assertFalse(self.manage("status")["running"])

    def test_missing_dependencies_fail_quickly_without_installing(self):
        source = self.script.read_text()
        self.script.write_text(source.replace(
            "def prepare(environment):", 'def prepare(environment):\n    raise RuntimeError("fixture missing dependencies")'))
        before = time.monotonic()
        result = subprocess.run([sys.executable, str(self.script), "start"], cwd="/tmp",
                                capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["state"], "failed")
        self.assertIn("fixture missing dependencies", data["error"])
        self.assertLess(time.monotonic() - before, 2)
        self.assertFalse(self.manage("status")["running"])

    def test_idle_exit(self):
        first = self.manage("start", "--idle-seconds", "2")
        self.assertTrue(first["running"])
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if not self.manage("status")["running"]:
                break
            time.sleep(0.3)
        self.assertFalse(self.manage("status")["running"])

    def test_stale_record_cannot_kill_unrelated_process(self):
        spec = importlib.util.spec_from_file_location("skill_manager_fixture", self.script)
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
        _, state = manager.locations()
        state.mkdir(parents=True, exist_ok=True)
        unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"])
        try:
            (state / "service.json").write_text(json.dumps({
                "pid": unrelated.pid, "stamp": manager.process_stamp(unrelated.pid), "port": 1}))
            self.manage("stop")
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
