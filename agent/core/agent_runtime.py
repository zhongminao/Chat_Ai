import uuid
from collections.abc import Callable
from pathlib import Path

from ..agentsessionstate import message_updates, transitions
from ..agentsessionstate.input import UserInput, normalize_input
from ..agentsessionstate.state import AgentState, StateUpdate
from ..model.catalog import ModelCatalog
from ..storage.event_log import EventLog
from ..storage.images import ImageStore
from ..tools.router import ToolRouter
from ..tools.schema import SUBMIT_SCHEMA
from ..workflows.turn.graph import run_turn
from .cancellation import CancellationToken, ExecutionContext, RunCancelled
from .control import ExecutionControl


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
        *,
        output: Callable[[str], None],
        tools: ToolRouter,
        on_submit: Callable[[str, str], str],
        control: ExecutionControl,
        context_config: dict,
        steering,
        begin_submit,
        release_submit,
    ):
        self.state = state
        self.control = control
        self.catalog = catalog
        self.session_id = session_id
        self.spill = spill
        self.max_rounds = max_rounds
        self.context_config = context_config
        self.steering = steering
        self.begin_submit = begin_submit
        self.release_submit = release_submit
        self.tools = tools
        self.on_submit = on_submit
        self.tools.submit = self._submit
        self.tools.schemas.append(SUBMIT_SCHEMA)

        self.workspace = workspace
        self.log = log
        self.images = images
        self.tools.images = self.images
        self.output = output

    def close(self) -> None:
        self.catalog.close()

    def apply(self, update: StateUpdate) -> None:
        self.state.update(update)

    def _submit(self, content: str, *, context=None) -> str:
        update = transitions.submit(self.state, content)
        if context:
            context.cancellation.raise_if_cancelled()
        if self.begin_submit(lambda *_args, **_kwargs: self.steering.has_pending(), context):
            return "Report not submitted: new runtime input is pending. Process it and call submit again."
        self.apply(update)
        run_id = transitions.execution(self.state)['id']
        try:
            self.on_submit(transitions.execution(self.state)['report'], run_id)
        except Exception:
            self.apply(transitions.update_execution(self.state, report=None, report_path=None))
            self.release_submit()
            raise
        return "Report submitted."

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
            return run_turn(self, prompt, context)
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
            # A cancelled or failed tool batch must not activate a previous discovery
            # on an unrelated later user turn.
            self.tools.pending_tools.clear()
            self.control.pending_tools([])
            self.control.unbind(context.cancellation)

    def prepare_input(self, prompt: str | UserInput) -> UserInput:
        value = normalize_input(prompt)
        identifiers = tuple(self.images.get(image)["id"] for image in value.images)
        return UserInput(value.text, identifiers)
