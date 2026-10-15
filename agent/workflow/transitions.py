"""Small state nodes and routing decisions. No I/O or runtime dependencies."""
from typing import Any, Literal

from .state import AgentState, ExecutionState, StateUpdate


def execution(state: AgentState) -> ExecutionState:
    value = state['execution']
    if value is None:
        raise ValueError('no execution has started')
    return value


def update_execution(state: AgentState, **changes: Any) -> StateUpdate:
    return {'execution': {**execution(state), **changes}}


def switch_model(state: AgentState, model: dict[str, str]) -> StateUpdate:
    if state['execution'] and state['execution']['status'] == 'running':
        raise ValueError('cannot switch models during an execution')
    return {'model': dict(model)}


def start(state: AgentState, run_id: str) -> StateUpdate:
    return {'execution': {
        'id': run_id, 'status': 'running', 'phase': 'model', 'round': 0,
        'answer': '', 'report': None, 'report_path': None, 'error': None,
    }}


def start_round(state: AgentState, round_no: int) -> StateUpdate:
    return update_execution(state, round=round_no, phase='model', answer='')


def append_answer(state: AgentState, text: str) -> StateUpdate:
    return update_execution(state, answer=execution(state)['answer'] + text)


def submit(state: AgentState, content: str) -> StateUpdate:
    if not isinstance(content, str) or not content.strip():
        raise ValueError('report content must be non-empty text')
    current = execution(state)
    if current['status'] != 'running':
        raise ValueError('no execution is running')
    if current['report'] is not None:
        raise ValueError('a report has already been submitted')
    return update_execution(state, report=content.strip())


def report_saved(state: AgentState, content: str, path: str) -> StateUpdate:
    return update_execution(state, report=content, report_path=path)


def complete(state: AgentState, answer: str) -> StateUpdate:
    report = {'report': answer} if execution(state)['report'] is not None else {}
    return update_execution(state, status='completed', phase='done', answer=answer, **report)


def fail(state: AgentState, reason: str) -> StateUpdate:
    return update_execution(state, status='failed', phase='done', error=reason)


def after_model(state: AgentState) -> Literal['tools', 'end']:
    return 'tools' if execution(state)['phase'] == 'tools' else 'end'


def after_tools(state: AgentState) -> Literal['model', 'submit']:
    return 'submit' if execution(state)['report'] is not None else 'model'
