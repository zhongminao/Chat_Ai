# Windows desktop workflow (skill-only)

**Only use with the user's live Windows interactive session and explicit approval.** Neither the Linux agent nor its core framework requires modifications. The Linux skill service runs on demand and is closed by `scripts/workflow.py` after each locate. Linux cannot capture/control the Windows desktop directly.

## 1. Screenshot with cursor (Windows PowerShell)

Copy the skill's `scripts/windows_bridge.ps1` to the Windows host (this environment supports SSH alias `my_server_` in the Windows-to-Linux direction). On Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\desktop-locator-windows-bridge.ps1" -Action capture -Output "$env:TEMP\desktop-locator-cursor.png" -Metadata "$env:TEMP\desktop-locator-cursor.json"
scp "$env:TEMP\desktop-locator-cursor.png" my_server_:/home/zhong/mydisk/tools/chat_ai_test/workspace/desktop-locator-cursor.png
scp "$env:TEMP\desktop-locator-cursor.json" my_server_:/home/zhong/mydisk/tools/chat_ai_test/workspace/desktop-locator-cursor.json
```

`capture` composites the visible pointer via Win32 `GetCursorInfo` + `DrawIconEx` and returns window identity, pointer screen position, virtual desktop origin, screenshot SHA-256, and `stable` status. It must not silently succeed if the pointer was hidden. The screenshot includes the pointer, which might obscure a target: do **not** deliberately move the mouse to obtain an unobscured screenshot without asking; capture again when appropriate. Save screenshot only in an approved private location: it can contain sensitive desktop information.

## 2. One-shot locate on Linux

Use the Python with Pillow from the chat_ai_test environment. Run only after the screenshot is on Linux:

```bash
/home/zhong/miniconda3/envs/chat-ai-py313/bin/python /home/zhong/mydisk/tools/chat_ai_test/skills/desktop_locator/scripts/workflow.py \
  --image /home/zhong/mydisk/tools/chat_ai_test/workspace/desktop-locator-cursor.png \
  --target 'unique description of target' \
  --annotated /home/zhong/mydisk/tools/chat_ai_test/workspace/desktop-locator-annotated.png
```

For client-collected AX nodes instead, supply `--ax-json FILE` containing `{"selector":{"name":"Save","role":"button"},"nodes":[{"name":"Save","role":"button","bbox":{"x":10,"y":20,"width":100,"height":40}}]}`; all bboxes must refer to the **virtual desktop screenshot's** pixels and selector must be unique. Windows UI Automation collection is **not yet implemented**; do not fabricate AX nodes from a screenshot. The workflow starts a localhost HTTP server on a random available port, requests `/locate` once, writes a preview image and shuts the server down even on failures. It does not click. For a real window-relative AX tree use the window's exact screenshot instead; screenshot/capture coordinate systems must agree.

The result's `screenshot_token` is SHA-256 of the image bytes. It is only an image identity check, not proof that the desktop is unchanged. For a full desktop screenshot convert local pixel x/y to absolute screen by adding `virtualScreen.x/y`. Never assume `(0,0)` with multiple monitors.

## 3. Guarded pointer movement and click (explicit execution only)

The Windows bridge supports `-Action preview` (no mouse input), `-Action move -ConfirmExecution` (move pointer only), and `-Action execute -ConfirmExecution` (move pointer and send one left-button down/up pair). For `move`/`execute`, pass `-ActionPermit` containing the `task/<id>/action` JSON result from the running in-memory session; this handoff cannot survive a skill service restart. Both require `-CaptureMetadata <capture.json> -Metadata <locator-result.json> -X <absolute-screen-x> -Y <absolute-screen-y> -TargetLeft/-TargetTop/-TargetRight/-TargetBottom <absolute-screen-bounds>`. For vision output also pass `-RegionSpecified`, **only if the user explicitly reviewed the `reviewed_region` of the session action permit**; target bounds must match this region exactly after virtual-screen offset; unique AX must be genuine Windows UI Automation output. The locator's `x/y` are screenshot pixels; absolute screen coordinates add `virtualScreen.x/y`.

The bridge checks screenshot hash/token, maximum five-second age, unchanged foreground identity and bounds, virtual desktop, current pointer position, and target region. With `execute`, it rechecks pointer/window before moving and before a one-time click. It reports input submitted, **not semantic task success**; do not retry after uncertainty. No full Windows UI Automation collector is included yet. A Linux↔Windows roundtrip may take longer than five seconds, causing deliberate refusal; obtaining a fresh capture and locating again is necessary.

**Safety boundary:** The image alone cannot prove an active/dynamic target is still present, and pointer sampling cannot perfectly exclude a human click or movement in the check-to-input gap. Before actual actions, present the proposed target/region to the user and obtain consent; never assume an allowed_actions entry is permission. For a real hands-off workflow add native UI Automation target identity, occlusion verification, emergency stop and on-host fresh visual confirmation. Development tests executed no actual pointer movements or clicks.

## Firefox tab UI Automation (preferred over physical mouse for tab navigation)

`scripts/windows_select_tab.ps1 -Name '<exact tab title>' -ExpectedWindowTitle '<exact current Firefox window title>'` performs a dry-run lookup of a uniquely named, visible and enabled tab. Add `-Execute` to call UI Automation `SelectionItemPattern.Select()` and confirm its selected state; this **does not move the pointer**. Afterwards call `capture` and `observe` again to verify page content; selected state alone does not prove the page loaded. This action is limited to Firefox's existing tab, not arbitrary URL navigation.

Real Firefox tab-switch smoke test: a unique UI Automation `TabItem` titled `武魂融合，隐身带球完成惊天翻盘！_哔哩哔哩_bilibili` was selected without moving the pointer; Firefox window title and a fresh screenshot of the video page confirmed navigation. The post-navigation full-screen PNG was 1.9 MiB and exceeded the locator's 1 MiB screenshot limit, so a 296 KiB JPEG derivative was fed to `observe` solely for description. **Do not use the derivative JPEG hash for `windows_bridge.ps1` action validation**: it differs from the original capture's SHA-256. This test did not move or click the physical mouse.
