#!/usr/bin/env python3
"""Run the original AKTools application with per-Skill lifecycle management."""
import argparse
import asyncio
from contextlib import asynccontextmanager, suppress
import json
import os
from pathlib import Path
import socket
import time

import akshare as ak
from aktools.main import app
import uvicorn


def create_app(instance, state_dir, idle_seconds):
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            application.state.last_request = time.monotonic()

            async def reap_idle():
                while True:
                    await asyncio.sleep(min(15, idle_seconds))
                    if not application.state.active and time.monotonic() - application.state.last_request >= idle_seconds:
                        application.state.uvicorn.should_exit = True
                        return

            task = asyncio.create_task(reap_idle())
            try:
                stamp = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()[19]
                record = {"pid": os.getpid(), "stamp": stamp, "port": application.state.port}
                temporary = state_dir / "service.tmp"
                temporary.write_text(json.dumps(record))
                temporary.replace(state_dir / "service.json")
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
    app.state.active = 0

    @app.middleware("http")
    async def activity(request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        app.state.active += 1
        app.state.last_request = time.monotonic()
        try:
            return await call_next(request)
        finally:
            app.state.active -= 1
            app.state.last_request = time.monotonic()

    @app.get("/healthz", include_in_schema=False)
    def health():
        return {"instance": instance, "pid": os.getpid(), "idle_seconds": idle_seconds}

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--idle-seconds", type=int, required=True)
    args = parser.parse_args()
    ak.set_timeout((10, 20))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    application = create_app(args.instance, args.state_dir, args.idle_seconds)
    application.state.port = listener.getsockname()[1]
    application.state.uvicorn = uvicorn.Server(uvicorn.Config(application, fd=listener.fileno(),
                                                            log_level="warning", access_log=False))
    try:
        application.state.uvicorn.run()
    finally:
        listener.close()


if __name__ == "__main__":
    main()
