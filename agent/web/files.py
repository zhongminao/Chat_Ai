"""Upload transport for session-owned opaque attachments."""
import asyncio

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..storage.files import FileStore, FileTooLarge


def file_router(sessions) -> APIRouter:
    router = APIRouter(prefix="/api/sessions/{session_id}/files")

    @router.post("")
    async def upload(session_id: str, file: UploadFile):
        try:
            store = FileStore(sessions.path(session_id))
            try:
                record = await asyncio.to_thread(store.add, file.file, file.filename or "file")
                return {"file": record}
            except FileTooLarge as exc:
                raise HTTPException(413, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "Session not found") from exc
        finally:
            await file.close()

    @router.post("/folder")
    async def upload_folder(session_id: str, name: str = Form(...),
                            files: list[UploadFile] = File(...),
                            paths: list[str] = Form(...)):
        try:
            store = FileStore(sessions.path(session_id))
            try:
                record = await asyncio.to_thread(store.add_folder, [file.file for file in files], paths, name)
                return {"file": record}
            except FileTooLarge as exc:
                raise HTTPException(413, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "Session not found") from exc
        finally:
            for file in files:
                await file.close()

    return router
