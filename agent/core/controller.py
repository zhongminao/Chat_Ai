import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..model.buffer import TextBuffer
from ..model.catalog import ModelCatalog
from ..workflow.commands import SwitchModel
from ..workflow.model_switch import apply as apply_model_switch
from ..workflow.state import AgentState
from .cancellation import ExecutionContext, RunCancelled, CancellationToken
from .control import ControlState
from ..model.openai_compatible import stream
from ..model.providers import create as create_provider
from ..storage.event_log import EventLog
from ..tools.router import ToolRouter
from ..tools.spill import handle as spill_output
from ..tools.schema import DELEGATE_SCHEMA, TOOL_SCHEMAS, ToolCallAssembler


SYSTEM_PROMPT = (
    "You are a small coding assistant. Use the provided tools when needed. "
    "Keep answers concise."
)


class Controller:
    def __init__(
        self,
        client: Any,
        model: dict[str, str],
        provider: Any,
        catalog: ModelCatalog,
        thinking: str,
        session_id: str,
        spill: dict[str, int | bool | str],
        workspace: Path,
        log: EventLog,
        output: Callable[[str], None] | None = None,
        tools: ToolRouter | None = None,
        enable_delegate: bool = True,
        control: ControlState | None = None,
    ):
        self.client = client
        self.control = control or ControlState()
        self.model = model
        self.catalog = catalog
        self.session_id = session_id
        self.spill = spill
        self.tools = tools or ToolRouter(workspace)
        if enable_delegate and self.tools.delegate is None:
            self.tools.delegate = self._delegate
            self.tools.schemas.append(DELEGATE_SCHEMA)
        self.state: AgentState = {
            "model": dict(model),
            "messages": [],
            "tools": self.tools.schemas,
            "mcp_servers": self.tools.mcp_servers,
            "spill_enabled": bool(spill.get("enabled", True)),
            "status": "idle",
        }
        self.provider = provider or create_provider(model["provider"], model["thinking"])

        self.workspace = workspace
        self.log = log
        self.output = output or (lambda text: print(text, end="", flush=True))
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

    def _delegate(
        self, agent: str, task: str, context: ExecutionContext | None = None
    ) -> str:
        if not agent.strip() or not task.strip():
            raise ValueError("agent and task are required")
        if agent == "main":
            raise ValueError("an agent cannot delegate to main")
        self.log.append("agent.started", agent=agent, task=task)
        child_tools = ToolRouter(self.workspace, self.tools.mcp)
        child = Controller(
            client=self.client,
            model=dict(self.model),
            provider=self.provider,
            catalog=self.catalog,
            thinking=self.model.get("thinking", "disabled"),
            session_id=f"{self.session_id}:{agent}",
            spill=self.spill,
            workspace=self.workspace,
            log=_SilentLog(),
            output=lambda text: None,
            tools=child_tools,
            enable_delegate=False,
            control=self.control,
        )
        result = child.run(task, max_rounds=4, context=context)
        self.log.append("agent.completed", agent=agent, result=result)
        return result

    def _cancel_pending_tools(self, run_id: str, calls: list[Any]) -> None:
        for call in calls:
            result = "[tool cancelled] Turn was stopped before this tool completed."
            self.log.append(
                "tool.completed",
                runId=run_id,
                tool=call.name,
                callId=call.id,
                result=result,
            )
            self.messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    def dispatch(self, command: SwitchModel) -> dict[str, str]:
        target = self.catalog.resolve(command.provider, command.model)
        client, provider = self.catalog.runtime(target)
        old = self.model
        self.client = client
        self.provider = provider
        self.model = target.as_dict()
        self.state = apply_model_switch(self.state, command, self.model)
        self.log.append("model.changed", old=old, new=self.model)
        return self.model

    def run(
        self,
        prompt: str,
        max_rounds: int = 200,
        context: ExecutionContext | None = None,
    ) -> str:
        own_token = context is None
        context = context or ExecutionContext(CancellationToken())
        self.control.bind(context.cancellation)
        try:
            return self._run(prompt, max_rounds, context)
        except (RunCancelled, KeyboardInterrupt):
            context.cancellation.cancel()
            if not own_token:
                raise
            answer = getattr(self, "_current_answer", "")
            if answer:
                self.messages.append({"role": "assistant", "content": answer})
            self.log.append(
                "turn.cancelled",
                runId=getattr(self, "_current_run_id", None),
                answer=answer,
            )
            print()
            return answer
        finally:
            if own_token:
                context.cancellation.cancel() if context.cancellation.is_cancelled() else None
            self.control.unbind(context.cancellation)

    def _run(
        self,
        prompt: str,
        max_rounds: int,
        context: ExecutionContext,
    ) -> str:
        run_id = uuid.uuid4().hex
        self._current_run_id = run_id
        self._current_answer = ""
        context.cancellation.raise_if_cancelled()
        self.messages.append({"role": "user", "content": prompt})
        self.log.append("turn.started", runId=run_id, prompt=prompt)

        for round_no in range(max_rounds):
            assembler = ToolCallAssembler()
            text_buffer = TextBuffer()
            answer: list[str] = []
            finish_reason = None
            usage = None

            self.log.append("model.started", runId=run_id, round=round_no)
            cancelled = False
            for chunk in stream(
                self.client,
                self.model["name"],
                self.messages,
                self.tools.schemas,
                provider=self.provider,
                context=context,
            ):
                context.cancellation.raise_if_cancelled()

                if chunk.content:
                    answer.append(chunk.content)
                    self._current_answer = "".join(answer)
                    self.output(chunk.content)
                    if piece := text_buffer.add(chunk.content):
                        self.log.append(
                            "message.delta",
                            durable=False,
                            runId=run_id,
                            round=round_no,
                            text=piece,
                        )

                if chunk.reasoning:
                    self.log.append(
                        "reasoning.delta",
                        durable=False,
                        runId=run_id,
                        round=round_no,
                        text=chunk.reasoning,
                    )

                for delta in chunk.tool_deltas:
                    assembler.add(delta.as_dict())
                    self.log.append(
                        "tool_call.delta",
                        durable=False,
                        runId=run_id,
                        round=round_no,
                        delta=delta.as_dict(),
                    )

                finish_reason = chunk.finish_reason or finish_reason
                usage = chunk.usage or usage

            context.cancellation.raise_if_cancelled()

            if piece := text_buffer.flush():
                self.log.append(
                    "message.delta",
                    durable=False,
                    runId=run_id,
                    round=round_no,
                    text=piece,
                )

            calls = assembler.finish()
            full_answer = "".join(answer)
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": full_answer,
            }
            if calls:
                assistant["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.arguments, ensure_ascii=False
                            ),
                        },
                    }
                    for call in calls
                ]
            self.messages.append(assistant)

            self.log.append(
                "model.completed",
                runId=run_id,
                round=round_no,
                finishReason=finish_reason,
                usage=usage,
            )

            if not calls:
                self.log.append(
                    "turn.completed",
                    runId=run_id,
                    answer=full_answer,
                )
                print()
                return full_answer

            completed_call_ids = set()
            for call in calls:
                context.cancellation.raise_if_cancelled()
                self.log.append(
                    "tool.requested",
                    runId=run_id,
                    tool=call.name,
                    callId=call.id,
                    arguments=call.arguments,
                )
                try:
                    result = self.tools.call(call.name, call.arguments, context)
                    result = spill_output(
                        result,
                        enabled=self.state.get("spill_enabled", True),
                        max_inline_chars=int(self.spill.get("max_inline_chars", 12000)),
                        preview_chars=int(self.spill.get("preview_chars", 4000)),
                        workspace=self.workspace,
                        session_id=self.session_id,
                        directory=str(self.spill.get("directory", ".spill")),
                    )
                except RunCancelled:
                    self._cancel_pending_tools(
                        run_id,
                        [item for item in calls if item.id not in completed_call_ids],
                    )
                    raise
                self.log.append(
                    "tool.completed",
                    runId=run_id,
                    tool=call.name,
                    callId=call.id,
                    result=result,
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
                completed_call_ids.add(call.id)
                context.cancellation.raise_if_cancelled()

        self.log.append("turn.failed", runId=run_id, reason="max_rounds")
        raise RuntimeError("maximum model rounds reached")


class _SilentLog:
    def append(self, *args, **kwargs):
        return None
