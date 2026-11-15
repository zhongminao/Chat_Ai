"""Durable per-session user questions; only the session worker waits here.

The gate never takes the session lock. Cancellation callback removal happens
outside the condition, including when a callback is already waking a waiter.
"""
from copy import deepcopy
from threading import Condition
from uuid import uuid4

from ..core.cancellation import RunCancelled


class QuestionNotFound(ValueError):
    pass


class QuestionConflict(ValueError):
    pass


def _text(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be nonblank text of at most {maximum} characters")
    return value.strip()


_MISSING = object()


def validate_question(question, options=_MISSING):
    question = _text(question, "question", 2000)
    if options is _MISSING:
        options = []
    if not isinstance(options, list) or (options and not 2 <= len(options) <= 5):
        raise ValueError("options must be absent, empty, or contain 2–5 options")
    normalized = []
    for option in options:
        if not isinstance(option, dict) or set(option) != {"title", "description"}:
            raise ValueError("each option requires only title and description (no option IDs)")
        normalized.append({"title": _text(option["title"], "title", 200),
                           "description": _text(option["description"], "description", 1000)})
    return question, normalized


class QuestionGate:
    def __init__(self, emit, records=()):
        self._emit = emit
        self._condition = Condition()
        self._items = {}
        self._contexts = {}
        for event in records:
            kind = event["type"]
            identifier = event.get("questionId")
            if kind == "question.requested":
                self._items[identifier] = {key: deepcopy(event[key]) for key in
                                          ("questionId", "callId", "question", "options", "runId")}
            elif kind in {"question.answered", "question.cancelled"} and identifier in self._items:
                item = self._items[identifier]
                if kind == "question.answered":
                    item["answer"] = deepcopy(event["answer"])
                else:
                    item["cancelled"] = True
        # A recreated process cannot resume the old tool stack. Persist a terminal
        # event before exposing the runtime so replay and snapshots agree.
        with self._condition:
            for item in self._items.values():
                if "answer" not in item and not item.get("cancelled"):
                    self._cancel(item, "process_restarted")

    def snapshot(self):
        with self._condition:
            return {"pending": deepcopy([item for item in self._items.values()
                                         if "answer" not in item and not item.get("cancelled")])}

    def _cancel(self, item, reason):
        self._emit("question.cancelled", questionId=item["questionId"],
                   runId=item["runId"], callId=item["callId"], reason=reason)
        item["cancelled"] = True
        self._condition.notify_all()

    def answer(self, identifier, *, option_index=None, text=None):
        with self._condition:
            item = self._items.get(identifier)
            if item is None:
                raise QuestionNotFound("Question not found")
            if item.get("cancelled"):
                raise QuestionConflict("This question was cancelled")
            context = self._contexts.get(identifier)
            if context and context.cancellation.is_cancelled() and "answer" not in item:
                self._cancel(item, "run_cancelled")
                raise QuestionConflict("This question was cancelled")
            if text is not None and (not isinstance(text, str) or len(text) > 4000):
                raise ValueError("text must be a string of at most 4000 characters")
            if option_index is not None:
                if type(option_index) is not int or not 0 <= option_index < len(item["options"]):
                    raise ValueError("option_index must be a zero-based index into this question's options")
                option = item["options"][option_index]
                answer = {"option_index": option_index, "text": option["title"] + "\n" + option["description"]}
            else:
                answer = {"option_index": None, "text": _text(text, "text", 4000)}
            if "answer" in item:
                if item["answer"] != answer:
                    raise QuestionConflict("This question already has a different answer")
            else:
                self._emit("question.answered", questionId=identifier, answer=deepcopy(answer),
                           runId=item["runId"], callId=item["callId"])
                item["answer"] = answer
                self._condition.notify_all()
            return {"accepted": True, "answer": deepcopy(answer)}

    def request(self, question, options=_MISSING, context=None, *, run_id=None, call_id=None):
        question, options = validate_question(question, options)
        if context is None:
            raise ValueError("ask_user requires an active session execution context")
        context.cancellation.raise_if_cancelled()
        item = {"questionId": uuid4().hex, "callId": call_id,
                "question": question, "options": options, "runId": run_id}
        identifier = item["questionId"]

        def wake():
            with self._condition:
                self._condition.notify_all()

        remove = context.cancellation.add_callback(wake)
        try:
            with self._condition:
                context.cancellation.raise_if_cancelled()
                self._items[identifier] = item
                self._contexts[identifier] = context
                try:
                    # State precedes publication: synchronous subscribers can answer
                    # immediately and the predicate below cannot lose that wakeup.
                    self._emit("question.requested", **deepcopy(item))
                    while "answer" not in item:
                        context.cancellation.raise_if_cancelled()
                        if item.get("cancelled"):
                            raise RunCancelled()
                        self._condition.wait()
                    context.cancellation.raise_if_cancelled()
                    result = {"questionId": identifier, **deepcopy(item["answer"])}
                    if result["option_index"] is not None:
                        result.update(deepcopy(options[result["option_index"]]))
                    return result
                except (RunCancelled, KeyboardInterrupt):
                    if "answer" not in item and not item.get("cancelled"):
                        self._cancel(item, "run_cancelled")
                    raise
                except Exception:
                    # If publication/subscriber handling fails, the router returns
                    # its usual tool error; no unanswered card may remain active.
                    if "answer" not in item and not item.get("cancelled"):
                        self._cancel(item, "tool_failed")
                    raise
                finally:
                    self._contexts.pop(identifier, None)
        finally:
            remove()
