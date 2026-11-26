"""Side effects at the boundaries of a single Agent turn."""
from __future__ import annotations

import uuid
from contextlib import closing, contextmanager
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


@contextmanager
def _step_context(agent, context, step):
    remove = context.cancellation.add_callback(step.token.cancel)
    try:
        yield replace(context, cancellation=step.token, turn_cancellation=context.cancellation)
    finally:
        agent.control.end_step(step)
        remove()


def model_round(_state: TurnState, runtime: Runtime[TurnContext]) -> Command[Literal["model_round", "tool_batch", "finalize"]]:
    agent, context = runtime.context.agent, runtime.context.execution
    execution = transitions.execution(agent.state)
    run_id = execution["id"]
    round_no = execution["round"] + (execution["phase"] != "model")
    context.cancellation.raise_if_cancelled()
    if round_no >= agent.max_rounds:
        raise RuntimeError("maximum model rounds reached")
    agent.apply(transitions.start_round(agent.state, round_no))
    with _step_context(agent, context, agent.control.start_step("model")) as step_context:
        try:
            return _run_model(agent, step_context, run_id, round_no)
        except RunCancelled:
            if _turn_stopped(agent, context) or not step_context.cancellation.is_cancelled():
                raise
            # Keep streamed text, but never turn partial tool arguments into calls.
            answer = transitions.execution(agent.state)["answer"]
            if answer:
                agent.apply(message_updates.complete_model(agent.state, answer, []))
            else:
                agent.apply(transitions.update_execution(agent.state, phase="done"))
            agent.log.append("model.interrupted", runId=run_id, round=round_no, answer=answer)
            return Command(goto="model_round")


def _run_model(agent, context, run_id, round_no):
    _deliver_inputs(agent, context)
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

    context.cancellation.raise_if_cancelled()
    agent.steering.acknowledge_corrections()
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

    agent.control.pending_tools(calls)
    return Command(update={"calls": calls}, goto="tool_batch" if calls else "finalize")


def tool_batch(state: TurnState, runtime: Runtime[TurnContext]) -> Command[Literal["model_round", "finalize"]]:
    agent, context = runtime.context.agent, runtime.context.execution
    run_id = transitions.execution(agent.state)["id"]
    calls = state["calls"]
    for index, call in enumerate(calls):
        # Share admission with stop and send; neither can race past this boundary.
        with agent.steering.lock:
            stopped = transitions.after_tools(agent.state) != "submit" and _turn_stopped(agent, context)
            corrected = not stopped and agent.state["role"] == "child" and agent.steering.has_correction()
            step = None if stopped or corrected else agent.control.start_step("tool")
        if stopped:
            _cancel_tools(agent, run_id, calls[index:])
            raise RunCancelled()
        if step is None:
            for pending in calls[index:]:
                _tool_result(agent, run_id, pending, "[tool skipped] Parent sent a correction.", status="skipped")
            break
        try:
            with _step_context(agent, context, step) as tool_context:
                _run_tool(agent, tool_context, run_id, call)
        except RunCancelled:
            if _turn_stopped(agent, context) or not step.token.is_cancelled():
                _cancel_tools(agent, run_id, calls[index:])
                raise
            _tool_result(agent, run_id, call, "[tool interrupted] Parent sent a correction.", status="interrupted")
            for pending in calls[index + 1:]:
                _tool_result(agent, run_id, pending, "[tool skipped] Parent sent a correction.", status="skipped")
            break
    agent.control.pending_tools([])
    if transitions.after_tools(agent.state) != "submit" and _turn_stopped(agent, context):
        raise RunCancelled()

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


def _run_tool(agent, context, run_id, call):
    agent.log.append("tool.requested", runId=run_id, tool=call.name, callId=call.id, arguments=call.arguments)
    if call.name == "bash":
        context = replace(context, on_process=lambda process: agent.log.append(
            "tool.process", runId=run_id, tool=call.name, callId=call.id, process=process,
        ))
    output = normalize_result(
        "[tool skipped] Report already submitted."
        if transitions.after_tools(agent.state) == "submit"
        else agent.tools.call(call.name, call.arguments, context, run_id=run_id, call_id=call.id)
    )
    result = spill_tool_output(
        output.text, preview=output.preview, sections=output.sections, detail_limit=output.detail_limit,
        max_inline_chars=int(agent.spill.get("max_inline_chars", 20000)),
        max_preview_chars=int(agent.spill.get("max_preview_chars", 24000)),
        # Keep complete answers and do not spill private collaboration data into the workspace.
        enabled=bool(agent.spill.get("enabled", True)) and call.name not in {
            "ask_user", "inspect_agent", "read_agent_message",
        },
        max_inline_lines=int(agent.spill.get("max_inline_lines", 100)),
        head_lines=int(agent.spill.get("head_lines", 10)),
        tail_lines=int(agent.spill.get("tail_lines", 10)),
        max_line_chars=int(agent.spill.get("max_line_chars", 200)),
        workspace=agent.workspace, session_id=agent.session_id,
        directory=str(agent.spill.get("directory", ".spill")),
    )
    _tool_result(agent, run_id, call, result, output.model_images)


def _turn_stopped(agent, context):
    return agent.control.stopped or context.cancellation.is_cancelled()


def _cancel_tools(agent, run_id, calls):
    for call in calls:
        _tool_result(agent, run_id, call, "[tool cancelled] Turn was stopped before this tool completed.")


def _tool_result(agent, run_id, call, result, images=(), *, status=None):
    fields = {"status": status} if status else {}
    agent.log.append("tool.completed", runId=run_id, tool=call.name, callId=call.id,
                     result=result, model_images=list(images), **fields)
    agent.apply(message_updates.receive_tool(agent.state, call.id, result, [image["id"] for image in images]))


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
            context.cancellation.raise_if_cancelled()
            if after < before:
                # Persist the replacement before using it, even if still above the trigger.
                agent.log.append("context.compacted", **identifiers, messages=update["messages"],
                                 beforeTokens=before, afterTokens=after, counter=method)
                agent.apply(update)
                before = after
            else:
                agent.log.append("context.compaction.failed", **identifiers,
                                 reason="整理未缩小上下文，保留原上下文并继续请求模型。")
    except (RunCancelled, KeyboardInterrupt):
        agent.log.append("context.compaction.cancelled", **identifiers)
        raise
    except Exception as exc:
        agent.log.append("context.compaction.failed", **identifiers, reason=str(exc))
        raise

    agent.log.append("context.measured", usedTokens=before, limitTokens=config["trigger_tokens"],
                    estimated=method != "llama_cpp")
