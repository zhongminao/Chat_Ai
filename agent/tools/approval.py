"""Per-conversation tool approval, shared by its main and child agents."""
from copy import deepcopy
from threading import Condition
from uuid import uuid4

from ..core.cancellation import RunCancelled


MODES = {"audit", "full_access"}


def requires_approval(name: str, is_mcp: bool) -> bool:
    return is_mcp or name in {"write_file", "edit_file", "run_bash"}


class ApprovalGate:
    def __init__(self, mode: str, emit):
        if mode not in MODES:
            raise ValueError("访问模式必须为 audit 或 full_access")
        self._mode = mode
        self._instance_id = uuid4().hex
        self._emit = emit
        self._pending: dict[str, dict] = {}
        self._revision = 0
        self._condition = Condition()

    def snapshot(self) -> dict:
        with self._condition:
            return {"mode": self._mode, "instanceId": self._instance_id, "revision": self._revision,
                    "pending": deepcopy(list(self._pending.values()))}

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError("访问模式必须为 audit 或 full_access")
        with self._condition:
            if self._pending:
                raise ValueError("请先处理或停止待审批操作，再切换访问模式")
            if mode != self._mode:
                self._emit("approval.mode.changed", mode=mode)
                self._mode = mode
                self._revision += 1

    def resolve(self, identifier: str, approved: bool) -> None:
        with self._condition:
            item = self._pending.get(identifier)
            if item is None:
                raise ValueError("此审批已处理或已失效")
            self._finish(item, "approved" if approved else "rejected")

    def _finish(self, item: dict, decision: str) -> None:
        self._emit("approval.resolved", approvalId=item["id"], sessionId=item["sessionId"],
                   runId=item["runId"], callId=item["callId"], decision=decision)
        item["decision"] = decision
        self._pending.pop(item["id"])
        self._revision += 1
        self._condition.notify_all()

    def request(self, name, arguments, context, *, session_id, run_id, call_id, is_mcp, workspace=None) -> bool:
        if context:
            context.cancellation.raise_if_cancelled()
        if not requires_approval(name, is_mcp):
            return True
        with self._condition:
            if self._mode == "full_access":
                self._emit("approval.bypassed", sessionId=session_id, runId=run_id,
                           callId=call_id, tool=name, mode=self._mode)
                return True
            item = {"id": uuid4().hex, "sessionId": session_id, "runId": run_id,
                    "callId": call_id, "tool": name, "arguments": deepcopy(arguments),
                    "workspace": None if is_mcp else workspace}
            self._pending[item["id"]] = item
            try:
                self._emit("approval.requested", **deepcopy(item))
            except BaseException:
                self._pending.pop(item["id"])
                raise
            self._revision += 1

            def wake():
                with self._condition:
                    self._condition.notify_all()

            remove = context.cancellation.add_callback(wake) if context else lambda: None
            try:
                while "decision" not in item:
                    if context:
                        context.cancellation.raise_if_cancelled()
                    self._condition.wait()
                if context:
                    context.cancellation.raise_if_cancelled()
                return item["decision"] == "approved"
            except (RunCancelled, KeyboardInterrupt):
                if item["id"] in self._pending:
                    self._finish(item, "cancelled")
                raise
            finally:
                remove()
