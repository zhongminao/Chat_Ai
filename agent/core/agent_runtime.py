import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..model.buffer import TextBuffer
from ..model.catalog import ModelCatalog
from ..workflow.commands import RenameImage, SwitchModel
from ..workflow.input import UserInput, normalize_input
from ..model.messages import build_user_message, build_tool_message, model_image_ids
from ..storage.images import ImageStore
from ..workflow.model_switch import apply as apply_model_switch
from ..workflow.state import AgentState
from .cancellation import ExecutionContext, RunCancelled, CancellationToken
from .control import ControlState
from ..model.openai_compatible import stream
from ..model.providers import create as create_provider
from ..storage.event_log import EventLog
from ..tools.router import ToolRouter
from ..tools.result import ToolResult, normalize_result
from ..tools.spill import handle as spill_output
from ..tools.schema import SUBMIT_SCHEMA, ToolCallAssembler


class AgentRuntime:
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
        max_rounds: int,
        system_prompt: str,
        output: Callable[[str], None] | None = None,
        tools: ToolRouter | None = None,
        on_submit: Callable[[str, str], str] | None = None,
        control: ControlState | None = None,
        images: ImageStore | None = None,
        on_tool_result: Callable[[ToolResult], None] | None = None,
    ):
        self.client = client
        self.control = control or ControlState()
        self.model = model
        self.catalog = catalog
        self.session_id = session_id
        self.spill = spill
        self.max_rounds = max_rounds
        self.system_prompt = system_prompt
        self.tools = tools or ToolRouter(workspace)
        self.on_submit = on_submit
        self.submitted_report: str | None = None
        self.tools.submit = self._submit
        self.tools.schemas.append(SUBMIT_SCHEMA)
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
        self.images = images or ImageStore(log.path.parent)
        self.tools.images = self.images
        self.on_tool_result = on_tool_result
        self.output = output or (lambda text: print(text, end="", flush=True))
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt.replace("{workspace}", str(workspace.resolve()))},
        ]

    def _submit(self, content: str) -> str:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("report content must be non-empty text")
        if self.submitted_report is not None:
            raise ValueError("a report has already been submitted")
        self.submitted_report = content.strip()
        return "Report submitted."

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

    def dispatch(self, command: SwitchModel | RenameImage) -> dict:
        if isinstance(command, RenameImage):
            image = self.images.rename(command.image, command.name)
            self.log.append("image.renamed", image=image)
            return image
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
        prompt: str | UserInput,
        context: ExecutionContext | None = None,
    ) -> str:
        own_token = context is None
        context = context or ExecutionContext(CancellationToken())
        self.control.bind(context.cancellation)
        try:
            return self._run(prompt, context)
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
        prompt: str | UserInput,
        context: ExecutionContext,
    ) -> str:
        run_id = uuid.uuid4().hex
        self._current_run_id = run_id
        self._current_answer = ""
        self.submitted_report = None
        context.cancellation.raise_if_cancelled()
        value = self.prepare_input(prompt)
        assets = [self.images.get(image) for image in value.images]
        self.messages.append(build_user_message(value.text, value.images))
        self.log.append("turn.started", runId=run_id, prompt=value.text, images=assets)

        for round_no in range(self.max_rounds):
            vision, image_limit = self.catalog.vision_options(self.model) if self.catalog else (False, None)
            self.tools.vision = vision
            self.tools.image_limit = image_limit
            assembler = ToolCallAssembler()
            text_buffer = TextBuffer()
            answer: list[str] = []
            finish_reason = None
            usage = None

            self.log.append("model.started", runId=run_id, round=round_no)
            for chunk in stream(
                self.client,
                self.model["name"],
                self.messages,
                self.tools.schemas,
                provider=self.provider,
                context=context,
                images=self.images,
                read_images=vision,
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
                if self.submitted_report is None:
                    context.cancellation.raise_if_cancelled()
                self.log.append(
                    "tool.requested",
                    runId=run_id,
                    tool=call.name,
                    callId=call.id,
                    arguments=call.arguments,
                )
                try:
                    self.tools.model_images = model_image_ids(self.messages)
                    output = normalize_result(
                        "[tool skipped] Report already submitted."
                        if self.submitted_report is not None
                        else self.tools.call(call.name, call.arguments, context)
                    )
                    result = spill_output(
                        output.text,
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
                    images=output.images,
                    model_images=output.model_images,
                )
                if output.images and self.on_tool_result:
                    self.on_tool_result(output)
                self.messages.append(build_tool_message(call.id, result, [image["id"] for image in output.model_images]))
                completed_call_ids.add(call.id)
                if self.submitted_report is None:
                    context.cancellation.raise_if_cancelled()

            if self.submitted_report is not None:
                report = self.submitted_report
                if self.on_submit:
                    report = self.on_submit(report, run_id)
                    self.submitted_report = report
                else:
                    self.log.append("report.submitted", runId=run_id, content=report)
                self.output(report)
                self.log.append("turn.completed", runId=run_id, answer=report)
                return report

        self.log.append("turn.failed", runId=run_id, reason="max_rounds")
        raise RuntimeError("maximum model rounds reached")

    def prepare_input(self, prompt: str | UserInput) -> UserInput:
        value = normalize_input(prompt)
        identifiers = tuple(self.images.get(image)["id"] for image in value.images)
        return UserInput(value.text, identifiers)

