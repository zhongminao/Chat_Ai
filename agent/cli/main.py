import argparse

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from ..core.session_registry import SessionRegistry
from ..model.discovery import refresh_catalog
from ..workflow.config import load
from ..workflow.commands import SwitchModel
from .images import ImageCommands
from .output import render_context_event, render_tool_result
from .approval import handle_approval_command, render_approval_event, wait_for_execution


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", help="one-shot user prompt")
    parser.add_argument("--session", help="继续已有 session")
    parser.add_argument("--access", choices=["audit", "full_access"], help="本会话及子 Agent 的访问模式")
    parser.add_argument("--image", action="append", default=[], help="图片文件，可重复指定")
    args = parser.parse_args()

    config = load()
    registry = SessionRegistry(config)
    refresh_catalog(registry.catalog)
    session_store = registry.store
    try:
        runtime = registry.get(args.session) if args.session else registry.create()
    except FileNotFoundError:
        raise SystemExit(f"找不到 session：{args.session}") from None
    if runtime.parent_session_id:
        raise SystemExit("子 session 只供查看，请继续它的主 session。")
    session = runtime.session
    agent = runtime.agent
    agent.output = lambda text: print(text, end="", flush=True)
    agent.on_tool_result = render_tool_result

    def on_event(event):
        runtime.bus.publish(event)
        render_context_event(event)
        render_approval_event(event)
        if event['type'].startswith('guidance.'):
            label = {'guidance.queued': '引导已发送，等待交付', 'guidance.applied': '引导已加入上下文',
                     'guidance.undelivered': '引导未送达，请重新发送'}
            print('\n' + label[event['type']])

    session.events.on_append = on_event
    if args.access:
        runtime.approvals.set_mode(args.access)
    prompt_session = PromptSession()

    if args.session:
        print(f"继续会话：{session.directory}")
    else:
        print(f"新会话：{session.directory}")
    print(f"当前模型：{agent.state['model']}")
    print("访问模式：" + ("审计" if runtime.approvals.snapshot()["mode"] == "audit" else "完全访问"))
    image_commands = ImageCommands(agent)
    for source in args.image:
        image_commands.add(source)
    if args.prompt or args.image:
        runtime.enqueue(image_commands.take_input(args.prompt or ""))
        wait_for_execution(registry, runtime, prompt_session, include_children=True)
        print()
        return

    print("输入 /model provider model 切换模型；输入 /exit 或 /quit 退出。")
    print("输入 /rename 新名称 修改当前会话名称。")
    print('执行期间直接输入补充要求即可引导；Ctrl+C 或 /stop 停止当前执行。')
    print("图片：/image 文件路径；/images；/send；/clear-images。")
    print("审批：/access audit|full_access；/approvals；/approve <审批ID>；/reject <审批ID>；/stop <会话ID>。")
    while True:
        try:
            with patch_stdout():
                prompt = prompt_session.prompt("> ")
        except KeyboardInterrupt:
            if runtime.busy:
                runtime.stop()
                print('\n本轮已请求停止。')
                continue
            print()
            break
        except EOFError:
            print()
            break

        text = prompt.strip()
        if text in {"/exit", "/quit"}:
            break
        if not text:
            continue
        if text == '/stop':
            runtime.stop()
            continue

        try:
            if handle_approval_command(text, runtime.approvals, lambda identifier: registry.get(identifier).stop()):
                continue
        except ValueError as exc:
            print(f"审批操作失败：{exc}")
            continue

        parts = text.split(maxsplit=1)
        if parts[0] == "/rename":
            try:
                title = session_store.rename(session.id, parts[1] if len(parts) == 2 else "")
                print(f"会话名称：{title}")
            except (ValueError, OSError) as exc:
                print(f"改名失败：{exc}")
            continue

        try:
            if image_commands.handle(text):
                continue
        except (ValueError, FileNotFoundError) as exc:
            print(f"图片操作失败：{exc}")
            continue

        if text.startswith("/model"):
            parts = text.split()
            if len(parts) != 3:
                print("用法：/model <provider> <model>")
                continue
            try:
                with runtime.lock:
                    if runtime.busy:
                        raise ValueError("会话正在执行")
                    target = runtime.dispatch(SwitchModel(provider=parts[1], model=parts[2]))
                print(f"已切换模型：{target['provider']}/{target['name']}")
            except Exception as exc:
                print(f"模型切换失败：{exc}")
            continue

        try:
            runtime.send(image_commands.take_input(text))
        except KeyboardInterrupt:
            runtime.stop()
            print("\n本轮已请求停止。")
        except Exception as exc:
            print(f"\n错误：{exc}")


if __name__ == "__main__":
    main()
