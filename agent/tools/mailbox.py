"""Agent-local mailbox tool handlers; sender identity is bound at construction."""


def send(registry, sender_id: str, *, to: str, content: str,
         cc: list[str] | None = None, kind: str | None = None) -> dict:
    role = registry.store.metadata(sender_id).get("parent_session_id")
    if to == "parent":
        if not role:
            raise ValueError("parent is available only to child agents")
        to = role
    return registry.notify_agent(sender_id, to, content, cc=() if cc is None else cc,
                                 kind=kind or ("feedback" if role else "notification"))


def inbox(registry, session_id: str, *, unread_only: bool = False) -> list[dict]:
    return registry.mailbox_list(session_id, unread_only=unread_only)


def read(registry, session_id: str, *, message_id: str) -> dict:
    return registry.mailbox_read(session_id, message_id)
