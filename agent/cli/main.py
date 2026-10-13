import argparse
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from ..workflow.config import load
from ..workflow.commands import SwitchModel
from ..workflow.history import HistoryNode
from ..core.control import ControlState
from ..core.controller import Controller
from ..model.catalog import ModelCatalog
from ..storage.event_log import EventLog
from ..storage.session import Session, create as create_session
from ..tools.mcp.client import McpRuntime
from ..tools.router import ToolRouter


def open_session(config, session_id: str | None) -> Session:
    if not session_id:
        return create_session(config.event_log.parent)
    root = (config.event_log.parent / "sessions").resolve()
    directory = (root / session_id).resolve()
    if directory.parent != root or not (directory / "session.json").is_file():
        raise SystemExit(f"找不到 session：{session_id}")
    return Session(session_id, directory, EventLog(directory / "events.jsonl"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", help="one-shot user prompt")
    parser.add_argument("--session", help="继续已有 session")
    args = parser.parse_args()

    config = load()
    catalog = ModelCatalog(config.providers_file)
    session = open_session(config, args.session)
    target = catalog.default()
    records = session.events.read()
    for event in records:
        if event["type"] == "model.changed":
            target = catalog.resolve(event["new"]["provider"], event["new"]["name"])
    client, provider = catalog.runtime(target)
    tools = ToolRouter(config.workspace, McpRuntime(config.mcp) if config.mcp else None)
    control = ControlState()
    controller = Controller(
        client=client,
        model=target.as_dict(),
        provider=provider,
        catalog=catalog,
        thinking=target.thinking,
        session_id=session.id,
        spill=config.spill,
        workspace=config.workspace,
        log=session.events,
        tools=tools,
        control=control,
    )
    controller.state = HistoryNode(records).run(controller.state)
    controller.messages.extend(controller.state["messages"])
    controller.state["messages"] = controller.messages

    if args.session:
        print(f"继续会话：{session.directory}")
    else:
        print(f"新会话：{session.directory}")
    print(f"当前模型：{controller.model}")
    if args.prompt:
        controller.run(args.prompt)
        return

    print("输入 /model provider model 切换模型；输入 /exit 或 /quit 退出。")
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

        if text.startswith("/model"):
            parts = text.split()
            if len(parts) != 3:
                print("用法：/model <provider> <model>")
                continue
            try:
                target = controller.dispatch(SwitchModel(provider=parts[1], model=parts[2]))
                print(f"已切换模型：{target['provider']}/{target['name']}")
            except Exception as exc:
                print(f"模型切换失败：{exc}")
            continue

        try:
            control.clear_stop()
            controller.run(text)
        except KeyboardInterrupt:
            control.request_stop()
            print("\n本轮已请求停止。")
        except Exception as exc:
            print(f"\n错误：{exc}")


if __name__ == "__main__":
    main()
