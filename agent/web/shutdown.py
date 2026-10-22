"""Close long-lived responses before the ASGI server waits for them.

Lifespan shutdown runs after uvicorn drains HTTP requests, too late for SSE.
Chain the server's signal handlers, retaining its second-Ctrl+C behaviour.
"""
from contextlib import contextmanager
import signal
import threading


@contextmanager
def shutdown_signals(stopping: threading.Event):
    handlers = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            if not callable(previous):
                continue

            def forward(sig, frame, previous=previous):
                stopping.set()
                previous(sig, frame)

            signal.signal(signum, forward)
            handlers[signum] = (previous, forward)
    try:
        yield
    finally:
        stopping.set()
        for signum, (previous, installed) in handlers.items():
            # Do not overwrite a handler installed by another component later.
            if signal.getsignal(signum) is installed:
                signal.signal(signum, previous)
