"""HTTP transport for the shared image store."""
import asyncio

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..storage.images import ImageStore, MAX_IMAGE_BYTES

def image_router(sessions) -> APIRouter:
    router = APIRouter(prefix="/api/sessions/{session_id}/images")

    def store(session_id: str) -> ImageStore:
        try:
            return sessions.open(session_id).images
        except FileNotFoundError as exc:
            raise HTTPException(404, "Session not found") from exc

    @router.get("")
    def listing(session_id: str):
        return {"images": store(session_id).list()}

    @router.post("")
    async def upload(session_id: str, file: UploadFile):
        images = store(session_id)
        try:
            data = await file.read(MAX_IMAGE_BYTES + 1)
            image = await asyncio.to_thread(images.add, data, file.filename or "image")
            return {"image": image}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            await file.close()

    @router.get("/{image_id}/content")
    def content(session_id: str, image_id: str, preview: bool = False):
        images = store(session_id)
        try:
            image = images.get(image_id)
            return FileResponse(images.path(image_id, preview), media_type="image/png" if preview else image["mime"],
                                filename=image["filename"], content_disposition_type="inline")
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc


    return router
