import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..model.buffer import TextBuffer
from ..model.catalog import ModelCatalog, ModelTarget
from ..model.tokens import count_request_tokens
from ..model.context_summary import summarize_context
from ..workflow.commands import RenameImage
from ..workflow.input import UserInput, normalize_input
from ..model.request_messages import model_image_ids
from ..storage.images import ImageStore
from ..workflow.state import AgentState, StateUpdate
from ..workflow import context_compaction, completion, message_updates, transitions
from .cancellation import ExecutionContext, RunCancelled, CancellationToken
from .control import ExecutionControl
from ..model.openai_compatible import stream
from ..model.stream_guard import ModelStreamGuard
from ..storage.event_log import EventLog
from ..tools.router import ToolRouter
from ..tools.result import ToolResult, normalize_result
from ..tools.spill import spill_tool_output
from ..tools.schema import SUBMIT_SCHEMA, ToolCallAssembler


class AgentRuntime:
    """Execute model and tool steps against the supplied serializable state."""

    def __init__(
        self,
        state: AgentState,
        catalog: ModelCatalog,
        session_id: str,
        spill: dict[str, int | bool | str],
        workspace: Path,
        log: EventLog,
        max_rounds: int,
        images: ImageStore,
        output: Callable[[str], None] | None = None,
        tools: ToolRouter | None = None,
        on_submit: Callable[[str, str], str] | None = None,
        control: ExecutionControl | None = None,
        on_tool_result: Callable[[ToolResult], None] | None = None,
        context_config: dict | None = None,
        steering=None,
        begin_submit=None,
        release_submit=None,
    ):
        self.state = state
        self.control = control or ExecutionControl()
        self.catalog = catalog
        self.session_id = session_id
        self.spill = spill
        self.max_rounds = max_rounds
        self.context_config = context_config or {}
        self.steering = steering
        self.begin_submit = begin_submit
        self.release_submit = release_submit or (lambda: None)
        self.tools = tools or ToolRouter(workspace)
        self.on_submit = on_submit
        self.tools.submit = self._submit
        self.tools.schemas.append(SUBMIT_SCHEMA)

        self.workspace = workspace
        self.log = log
        self.images = images
        self.tools.images = self.images
        self.on_tool_result = on_tool_result
        self.output = output or (lambda text: print(text, end="", flush=True))

    def close(self) -> None:
        self.catalog.close()

    def apply(self, update: StateUpdate) -> None:
        self.state.update(update)

    def _submit(self, content: str) -> str:
        self.apply(transitions.submit(self.state, content))
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
            self.apply(message_updates.receive_tool(self.state, call.id, result))

    def dispatch(self, command: RenameImage) -> dict:
        image = self.images.rename(command.image, command.name)
        self.log.append("image.renamed", image=image)
        return image

    def run(
        self,
        prompt: str | UserInput,
        context: ExecutionContext | None = None,
    ) -> str:
        own_token = context is None
        context = context or ExecutionContext(CancellationToken())
        self.apply(transitions.start(self.state, uuid.uuid4().hex))
        self.control.bind(context.cancellation)
        try:
            return self._run(prompt, context)
        except (RunCancelled, KeyboardInterrupt):
            context.cancellation.cancel()
            self.apply(message_updates.cancel(self.state))
            if not own_token:
                raise
            execution = transitions.execution(self.state)
            answer = execution["answer"]
            self.log.append(
                "turn.cancelled",
                runId=execution["id"],
                answer=answer,
            )
            print()
            return answer
        except Exception as exc:
            self.apply(transitions.fail(self.state, str(exc)))
            raise
        finally:
            self.control.unbind(context.cancellation)

    def _run(
        self,
        prompt: str | UserInput,
        context: ExecutionContext,
    ) -> str:
        run_id = transitions.execution(self.state)["id"]
        context.cancellation.raise_if_cancelled()
        value = self.prepare_input(prompt)
        assets = [self.images.get(image) for image in value.images]
        self.apply(message_updates.receive_user(self.state, value.text, value.images))
        self.log.append("turn.started", runId=run_id, prompt=value.text, images=assets)

        for round_no in range(self.max_rounds):
            self._deliver_guidance(context)
            self.apply(transitions.start_round(self.state, round_no))
            model = self.state["model"]
            client, provider = self.catalog.get_binding(ModelTarget(**model))
            vision, image_limit = self.catalog.vision_options(model) if self.catalog else (False, None)
            self.tools.vision = vision
            self.tools.image_limit = image_limit
            self._compact(client, provider, vision, context)
            if self._deliver_guidance(context):
                self._compact(client, provider, vision, context)
            assembler = ToolCallAssembler()
            stream_guard = ModelStreamGuard()
            text_buffer = TextBuffer()
            finish_reason = None
            usage = None

            self.log.append("model.started", runId=run_id, round=round_no)
            for chunk in stream(
                client,
                model["name"],
                self.state["messages"],
                self.tools.schemas,
                provider=provider,
                context=context,
                images=self.images,
                read_images=vision,
            ):
                context.cancellation.raise_if_cancelled()

                if chunk.content:
                    self.apply(transitions.append_answer(self.state, chunk.content))
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
                    stream_guard.check(delta)
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
            full_answer = transitions.execution(self.state)["answer"]
            self.apply(message_updates.complete_model(self.state, full_answer, calls))

            self.log.append(
                "model.completed",
                runId=run_id,
                round=round_no,
                finishReason=finish_reason,
                usage=usage,
            )

            if transitions.after_model(self.state) == "end":
                if self._begin_submit(context):
                    continue
                decision = completion.decide(self.state, self.max_rounds)
                if decision == "remind":
                    if self.begin_submit:
                        self.release_submit()
                    elif self.steering:
                        self.steering.begin()
                    context.cancellation.raise_if_cancelled()
                    self.apply(message_updates.remind_completion(self.state, completion.REMINDER))
                    self.log.append("completion.reminded", runId=run_id, content=completion.REMINDER)
                    continue
                if decision == "fail":
                    raise RuntimeError(completion.MISSING_SUBMIT)
                self.apply(transitions.complete(self.state, full_answer))
                self.log.append(
                    "turn.completed",
                    runId=run_id,
                    answer=full_answer,
                )
                print()
                return full_answer

            completed_call_ids = set()
            for call in calls:
                if transitions.after_tools(self.state) == "model":
                    context.cancellation.raise_if_cancelled()
                self.log.append(
                    "tool.requested",
                    runId=run_id,
                    tool=call.name,
                    callId=call.id,
                    arguments=call.arguments,
                )
                try:
                    self.tools.model_images = model_image_ids(self.state["messages"])
                    output = normalize_result(
                        "[tool skipped] Report already submitted."
                        if transitions.after_tools(self.state) == "submit"
                        else self.tools.call(call.name, call.arguments, context, run_id=run_id, call_id=call.id)
                    )
                    result = spill_tool_output(
                        output.text,
                        enabled=bool(self.spill.get("enabled", True)),
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
                self.apply(message_updates.receive_tool(self.state, call.id, result, [image["id"] for image in output.model_images]))
                completed_call_ids.add(call.id)
                if transitions.after_tools(self.state) == "model":
                    context.cancellation.raise_if_cancelled()

            if transitions.after_tools(self.state) == "submit":
                if self._begin_submit(context):
                    continue
                report = transitions.execution(self.state)["report"]
                if self.on_submit:
                    report = self.on_submit(report, run_id)
                else:
                    self.log.append("report.submitted", runId=run_id, content=report)
                self.output(report)
                self.apply(transitions.complete(self.state, report))
                self.log.append("turn.completed", runId=run_id, answer=report)
                return report

        raise RuntimeError("maximum model rounds reached")

    def _begin_submit(self, context):
        if self.begin_submit:
            return self.begin_submit(self._deliver_guidance, context)
        return self._deliver_guidance(context, finish=True)

    def _deliver_guidance(self, context, *, finish=False):
        context.cancellation.raise_if_cancelled()
        if not self.steering:
            return False
        values = self.steering.take(transitions.execution(self.state)['id'], finish=finish)
        for value in values:
            self.apply(message_updates.receive_user(self.state, value.text, value.images))
        if values:
            # A submit generated before the new requirements is only a candidate.
            self.apply(transitions.update_execution(self.state, report=None, report_path=None, completion_reminders=0))
        return bool(values)

    def _compact(self, client, provider, vision: bool, context: ExecutionContext) -> None:
        config = self.context_config
        context.cancellation.raise_if_cancelled()
        if not config.get("enabled", False):
            return
        method = self.catalog.token_counter(self.state["model"])

        def measure(value):
            return count_request_tokens(client, value, self.tools.schemas, context, method=method,
                                images=self.images, read_images=vision)

        before = measure(self.state["messages"])
        identifiers = {"runId": transitions.execution(self.state)["id"], "compactionId": uuid.uuid4().hex}
        try:
            selected = context_compaction.plan(self.state, before, config)
            if selected is None:
                return
            self.log.append("context.compaction.started", **identifiers, beforeTokens=before, counter=method)
            summary = summarize_context(client, self.state["model"]["name"], provider, selected, config, context)
            update = context_compaction.build_update(selected, summary)
            after = measure(update["messages"])
            context_compaction.validate_compacted_size(before, after, config)
            context.cancellation.raise_if_cancelled()
            # Commit the exact replacement before mutating memory. No await or
            # cancellation check may split durable commit from applying it.
            self.log.append("context.compacted", **identifiers, messages=update["messages"],
                            beforeTokens=before, afterTokens=after, counter=method)
            self.apply(update)
        except (RunCancelled, KeyboardInterrupt):
            self.log.append("context.compaction.cancelled", **identifiers)
            raise
        except Exception as exc:
            self.log.append("context.compaction.failed", **identifiers, reason=str(exc))
            raise

    def prepare_input(self, prompt: str | UserInput) -> UserInput:
        value = normalize_input(prompt)
        identifiers = tuple(self.images.get(image)["id"] for image in value.images)
        return UserInput(value.text, identifiers)

