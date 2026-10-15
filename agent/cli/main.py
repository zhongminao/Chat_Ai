import argparse

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from ..core.session_registry import SessionRegistry
from ..workflow.config import load
from ..workflow.commands import SwitchModel
from .images import ImageCommands
from .output import render_tool_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", help="one-shot user prompt")
    parser.add_argument("--session", help="继续已有 session")
    parser.add_argument("--image", action="append", default=[], help="图片文件，可重复指定")
    parser.add_argument("--image-name", action="append", default=[], help="图片名称；提供时与 --image 一一对应")
    args = parser.parse_args()
    if args.image_name and len(args.image_name) != len(args.image):
        parser.error("--image-name 需要与 --image 一一对应")

    config = load()
    registry = SessionRegistry(config)
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

    if args.session:
        print(f"继续会话：{session.directory}")
    else:
        print(f"新会话：{session.directory}")
    print(f"当前模型：{agent.state['model']}")
    image_commands = ImageCommands(agent)
    for index, source in enumerate(args.image):
        name = args.image_name[index] if args.image_name else None
        image_commands.add(source, name)
    if args.prompt or args.image:
        runtime.enqueue(image_commands.take_input(args.prompt or ""))
        registry.wait()
        print()
        return

    print("输入 /model provider model 切换模型；输入 /exit 或 /quit 退出。")
    print("输入 /rename 新名称 修改当前会话名称。")
    print("图片：/image 文件路径；/image-name 会话图片路径 新名称；/images；/send；/clear-images。")
    prompt_session = PromptSession()
    while True:
        try:
            with patch_stdout():
                prompt = prompt_session.prompt("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        text = prompt.strip()
        if text in {"/exit", "/quit"}:
            break
        if not text:
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
            runtime.enqueue(image_commands.take_input(text))
            runtime.queue.join()
        except KeyboardInterrupt:
            runtime.stop()
            print("\n本轮已请求停止。")
        except Exception as exc:
            print(f"\n错误：{exc}")


if __name__ == "__main__":
    main()
