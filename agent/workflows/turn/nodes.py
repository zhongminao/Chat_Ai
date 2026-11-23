"""Side effects at the boundaries of a single Agent turn."""
from __future__ import annotations

import uuid
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command

from ...agentsessionstate import completion, context_compaction, message_updates, transitions
from ...agentsessionstate.input import UserInput
from ...core.cancellation import ExecutionContext, RunCancelled
from ...model.buffer import TextBuffer
from ...model.catalog import ModelTarget
from ...model.context_summary import summarize_context
from ...model.openai_compatible import stream
from ...model.stream_guard import ModelStreamGuard
from ...model.tokens import count_request_tokens
from ...tools.result import normalize_result
from ...tools.schema import ToolCall, ToolCallAssembler
from ...tools.spill import spill_tool_output

if TYPE_CHECKING:
    from ...core.agent_runtime import AgentRuntime


class TurnState(TypedDict):
    prompt: str | UserInput
    calls: NotRequired[list[ToolCall]]


@dataclass(frozen=True)
class TurnContext:
    agent: AgentRuntime
    execution: ExecutionContext


def prepare_turn(state: TurnState, runtime: Runtime[TurnContext]) -> None:
    agent, context = runtime.context.agent, runtime.context.execution
    run_id = transitions.execution(agent.state)["id"]
    context.cancellation.raise_if_cancelled()
    value = agent.prepare_input(state["prompt"])
    assets = [agent.images.get(image) for image in value.images]
    current_time = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    # Guidance accepted during a stopped turn precedes this new prompt.
    # Do not make a later one-character nudge outrank the earlier request.
    _deliver_inputs(agent, context)
    agent.apply(message_updates.receive_user(agent.state, value.text, value.images,
                                            current_time=current_time))
    agent.log.append("turn.started", runId=run_id, prompt=value.text, images=assets,
                    currentTime=current_time)


def model_round(_state: TurnState, runtime: Runtime[TurnContext]) -> Command[Literal["tool_batch", "finalize"]]:
    agent, context = runtime.context.agent, runtime.context.execution
    execution = transitions.execution(agent.state)
    run_id = execution["id"]
    # Only the first entry starts in the model phase; returns follow a completed model step.
    round_no = execution["round"]
    if execution["phase"] != "model":
        round_no += 1
    if round_no >= agent.max_rounds:
        raise RuntimeError("maximum model rounds reached")
    _deliver_inputs(agent, context)
    agent.apply(transitions.start_round(agent.state, round_no))
    model = agent.state["model"]
    client, provider = agent.catalog.get_binding(ModelTarget(**model))
    vision = agent.catalog.supports_vision(model)
    agent.tools.vision = vision
    _compact(agent, client, provider, vision, context)
    if _deliver_inputs(agent, context):
        _compact(agent, client, provider, vision, context)
    assembler = ToolCallAssembler()
    stream_guard = ModelStreamGuard()
    text_buffer = TextBuffer()
    finish_reason = None
    usage = None
    reasoning: list[str] = []
    keep_reasoning = model["provider"] == "deepseek" and model["thinking"] == "enabled"

    agent.log.append("model.started", runId=run_id, round=round_no)
    with closing(stream(
        client,
        model["name"],
        agent.state["messages"],
        agent.tools.schemas,
        provider=provider,
        context=context,
        images=agent.images,
        read_images=vision,
    )) as response:
        for chunk in response:
            context.cancellation.raise_if_cancelled()

            if chunk.content:
                agent.apply(transitions.append_answer(agent.state, chunk.content))
                agent.output(chunk.content)
                if piece := text_buffer.add(chunk.content):
                    agent.log.append(
                        "message.delta",
                        durable=False,
                        runId=run_id,
                        round=round_no,
                        text=piece,
                    )

            if keep_reasoning and chunk.reasoning:
                reasoning.append(chunk.reasoning)

            for delta in chunk.tool_deltas:
                stream_guard.check(delta)
                assembler.add(delta.as_dict())
                agent.log.append(
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
        agent.log.append(
            "message.delta",
            durable=False,
            runId=run_id,
            round=round_no,
            text=piece,
        )

    calls = assembler.finish()
    full_answer = transitions.execution(agent.state)["answer"]
    tool_reasoning = "".join(reasoning) if calls else ""
    agent.apply(message_updates.complete_model(agent.state, full_answer, calls, tool_reasoning))

    agent.log.append(
        "model.completed",
        runId=run_id,
        round=round_no,
        finishReason=finish_reason,
        usage=usage,
        **({"reasoning_content": tool_reasoning} if tool_reasoning else {}),
    )

    return Command(update={"calls": calls}, goto="tool_batch" if calls else "finalize")


def tool_batch(state: TurnState, runtime: Runtime[TurnContext]) -> Command[Literal["model_round", "finalize"]]:
    agent, context = runtime.context.agent, runtime.context.execution
    run_id = transitions.execution(agent.state)["id"]
    calls = state["calls"]
    completed_call_ids = set()
    for call in calls:
        if transitions.after_tools(agent.state) == "model":
            context.cancellation.raise_if_cancelled()
        agent.log.append(
            "tool.requested",
            runId=run_id,
            tool=call.name,
            callId=call.id,
            arguments=call.arguments,
        )
        tool_context = replace(context, on_process=lambda process, call=call: agent.log.append(
            "tool.process", runId=run_id, tool=call.name, callId=call.id, process=process,
        )) if call.name == "bash" else context
        try:
            output = normalize_result(
                "[tool skipped] Report already submitted."
                if transitions.after_tools(agent.state) == "submit"
                else agent.tools.call(call.name, call.arguments, tool_context, run_id=run_id, call_id=call.id)
            )
            result = spill_tool_output(
                output.text,
                preview=output.preview,
                sections=output.sections,
                detail_limit=output.detail_limit,
                max_inline_chars=int(agent.spill.get("max_inline_chars", 20000)),
                max_preview_chars=int(agent.spill.get("max_preview_chars", 24000)),
                # ask_user is already strictly bounded and its complete
                # answer must reach the next model step, not a spill preview.
                enabled=bool(agent.spill.get("enabled", True)) and call.name != "ask_user",
                max_inline_lines=int(agent.spill.get("max_inline_lines", 100)),
                head_lines=int(agent.spill.get("head_lines", 10)),
                tail_lines=int(agent.spill.get("tail_lines", 10)),
                max_line_chars=int(agent.spill.get("max_line_chars", 200)),
                workspace=agent.workspace,
                session_id=agent.session_id,
                directory=str(agent.spill.get("directory", ".spill")),
            )
        except RunCancelled:
            _cancel_pending_tools(
                agent, run_id,
                [item for item in calls if item.id not in completed_call_ids],
            )
            raise
        agent.log.append(
            "tool.completed",
            runId=run_id,
            tool=call.name,
            callId=call.id,
            result=result,
            model_images=output.model_images,
        )
        agent.apply(message_updates.receive_tool(agent.state, call.id, result, [image["id"] for image in output.model_images]))
        completed_call_ids.add(call.id)
        if transitions.after_tools(agent.state) == "model":
            context.cancellation.raise_if_cancelled()

    # The model's entire tool-call batch uses the schemas it was shown.
    # Discovered MCP tools are activated only for the next model request.
    for alias, url in agent.tools.commit_pending_tools():
        agent.log.append("mcp.enabled", runId=run_id, alias=alias, url=url)
    next_node = "model_round" if transitions.after_tools(agent.state) == "model" else "finalize"
    return Command(update={"calls": []}, goto=next_node)


def finalize(_state: TurnState, runtime: Runtime[TurnContext]) -> Command[Literal["model_round", "__end__"]]:
    agent, context = runtime.context.agent, runtime.context.execution
    execution = transitions.execution(agent.state)
    report = execution["report"]
    if report is not None:
        # The submit tool already sealed guidance and saved the report.
        agent.output(report)
        answer = report
    else:
        if agent.begin_submit(partial(_deliver_inputs, agent), context):
            return Command(goto="model_round")
        decision = completion.decide(agent.state, agent.max_rounds)
        if decision == "remind":
            agent.release_submit()
            context.cancellation.raise_if_cancelled()
            agent.apply(message_updates.remind_completion(agent.state, completion.REMINDER))
            agent.log.append("completion.reminded", runId=execution["id"], content=completion.REMINDER)
            return Command(goto="model_round")
        if decision == "fail":
            raise RuntimeError(completion.MISSING_SUBMIT)
        answer = execution["answer"]

    agent.apply(transitions.complete(agent.state, answer))
    agent.log.append("turn.completed", runId=execution["id"], answer=answer)
    if report is None:
        print()
    return Command(goto=END)


def _cancel_pending_tools(agent: AgentRuntime, run_id: str, calls: list[ToolCall]) -> None:
    for call in calls:
        result = "[tool cancelled] Turn was stopped before this tool completed."
        agent.log.append(
            "tool.completed",
            runId=run_id,
            tool=call.name,
            callId=call.id,
            result=result,
        )
        agent.apply(message_updates.receive_tool(agent.state, call.id, result))


def _deliver_inputs(agent: AgentRuntime, context: ExecutionContext, *, finish=False) -> bool:
    context.cancellation.raise_if_cancelled()
    values = agent.steering.take(transitions.execution(agent.state)['id'], finish=finish)
    if values:
        agent.apply({"messages": [*agent.state["messages"], *values]})
        # A submit generated before the new requirements is only a candidate.
        agent.apply(transitions.update_execution(agent.state, report=None, report_path=None, completion_reminders=0))
    return bool(values)


def _compact(agent: AgentRuntime, client, provider, vision: bool, context: ExecutionContext) -> None:
    config = context_compaction.for_model(agent.context_config, agent.state["model"])
    context.cancellation.raise_if_cancelled()
    if not config.get("enabled", False):
        return
    method = agent.catalog.token_counter(agent.state["model"])

    def measure(value):
        return count_request_tokens(client, value, agent.tools.schemas, context, method=method,
                            images=agent.images, read_images=vision)

    before = measure(agent.state["messages"])
    identifiers = {"runId": transitions.execution(agent.state)["id"], "compactionId": uuid.uuid4().hex}
    try:
        selected = context_compaction.plan(agent.state, before, config)
        if selected is not None:
            agent.log.append("context.compaction.started", **identifiers, beforeTokens=before, counter=method)
            summary = summarize_context(client, agent.state["model"]["name"], provider, selected, config, context)
            update = context_compaction.build_update(selected, summary)
            after = measure(update["messages"])
            context_compaction.validate_compacted_size(before, after, config)
            context.cancellation.raise_if_cancelled()
            # Commit the exact replacement before mutating memory. No await or
            # cancellation check may split durable commit from applying it.
            agent.log.append("context.compacted", **identifiers, messages=update["messages"],
                            beforeTokens=before, afterTokens=after, counter=method)
            agent.apply(update)
            before = after
    except (RunCancelled, KeyboardInterrupt):
        agent.log.append("context.compaction.cancelled", **identifiers)
        raise
    except Exception as exc:
        agent.log.append("context.compaction.failed", **identifiers, reason=str(exc))
        raise

    agent.log.append("context.measured", usedTokens=before, limitTokens=config["trigger_tokens"],
                    estimated=method != "llama_cpp")
