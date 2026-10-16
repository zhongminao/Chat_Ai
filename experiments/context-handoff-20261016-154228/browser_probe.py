"""Browser observations for the generated game; never changes game files."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(args.game.resolve())))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    result = {"page_errors": [], "console_errors": [], "checks": {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1100, "height": 1000})
            page.on("pageerror", lambda exc: result["page_errors"].append(str(exc)))
            page.on("console", lambda msg: result["console_errors"].append(msg.text) if msg.type == "error" else None)
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle", timeout=20000)
            result["title"] = page.title()
            result["body_text"] = page.locator("body").inner_text()[:5000]
            result["checks"]["canvas_576x384"] = page.locator("canvas").evaluate_all(
                "items => items.some(c => c.width === 576 && c.height === 384)"
            )
            result["checks"]["corrected_default_seed_visible"] = page.locator("input").evaluate_all(
                "items => items.some(i => i.value === 'ORBIT-2049')"
            )
            result["checks"]["browser_game_initialized"] = page.evaluate(
                "() => { try { return typeof game !== 'undefined' && !!game && game.status === 'playing'; } catch { return false; } }"
            )
            page.screenshot(path=str(args.out / "game.png"), full_page=True)
            if result["checks"]["browser_game_initialized"]:
                turn_before = page.evaluate("game.turn")
                page.keyboard.press("z")
                result["checks"]["keyboard_wait_advances_turn"] = page.evaluate("game.turn") == turn_before + 1
                result["checks"]["game_has_dash"] = page.evaluate("typeof game.dash === 'function'")
                page.evaluate("""() => {
                    game.grid = Array.from({length: game.height}, () => Array(game.width).fill(0));
                    game.player = {x: 3, y: 3, hp: 5, energy: 12};
                    game.enemies = []; game.chips = []; game.collected = 0;
                    game.status = 'playing'; game.turn = 0;
                }""")
                page.keyboard.press("Shift+ArrowRight")
                result["checks"]["shift_arrow_uses_dash"] = page.evaluate(
                    "game.player.x === 5 && game.player.energy === 10 && game.turn === 1"
                )
                # Restart before save/replay checks so the replay has a valid seeded origin.
                if page.locator("#resetBtn").count():
                    page.locator("#resetBtn").click()
                    page.keyboard.press("z")
                if page.locator("#saveSlot1").count() and page.locator("#loadSlot1").count():
                    saved = page.evaluate("game.serialize()")
                    page.locator("#saveSlot1").click()
                    result["checks"]["save_format_version_1"] = page.evaluate(
                        "() => { const d = JSON.parse(localStorage.getItem('game_save_1')); return (d.version ?? d.schemaVersion ?? d.v) === 1; }"
                    )
                    page.keyboard.press("z")
                    page.locator("#loadSlot1").click()
                    result["checks"]["slot1_restores_exact_state"] = page.evaluate("game.serialize()") == saved
                if page.locator("#saveSlot2").count() and page.locator("#loadSlot2").count():
                    saved = page.evaluate("game.serialize()")
                    page.locator("#saveSlot2").click()
                    page.keyboard.press("z")
                    page.locator("#loadSlot2").click()
                    result["checks"]["slot2_restores_exact_state"] = page.evaluate("game.serialize()") == saved
                else:
                    result["checks"]["slot2_restores_exact_state"] = False
                if page.locator("#exportReplay").count():
                    before_replay = page.evaluate("game.serialize()")
                    downloaded = None
                    try:
                        with page.expect_download(timeout=3000) as download_info:
                            page.locator("#exportReplay").click()
                        downloaded = args.out / "replay.json"
                        download_info.value.save_as(str(downloaded))
                        value = downloaded.read_text(encoding="utf-8")
                    except PlaywrightTimeoutError:
                        value = page.locator("#replayText").input_value() if page.locator("#replayText").count() else ""
                    try:
                        replay = json.loads(value)
                        result["checks"]["replay_has_seed_and_actions"] = isinstance(replay.get("actions"), list) and bool(replay.get("seed"))
                        if result["checks"]["replay_has_seed_and_actions"] and page.locator("#importReplay").count():
                            page.keyboard.press("z")
                            if downloaded:
                                with page.expect_file_chooser(timeout=3000) as chooser:
                                    page.locator("#importReplay").click()
                                chooser.value.set_files(str(downloaded))
                                expected_turn = json.loads(before_replay)["turn"]
                                try:
                                    page.wait_for_function("expected => game.turn === expected", arg=expected_turn, timeout=3000)
                                except PlaywrightTimeoutError:
                                    result["replay_error"] = "Imported actions did not restore the expected turn"
                            else:
                                page.locator("#importReplay").click()
                            result["checks"]["replay_import_restores_exact_state"] = page.evaluate("game.serialize()") == before_replay
                    except (ValueError, AttributeError):
                        result["checks"]["replay_has_seed_and_actions"] = False
            browser.close()
    except Exception as exc:
        result["probe_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        server.shutdown()
        server.server_close()
    (args.out / "browser.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
