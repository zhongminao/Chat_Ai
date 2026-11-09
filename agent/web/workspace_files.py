"""Read-only HTTP access to files under the configured workspace."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


def workspace_file_router(workspace: Path) -> APIRouter:
    root = workspace.resolve()
    router = APIRouter(prefix=root.as_posix().rstrip("/"))

    @router.api_route("/{file_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def content(file_path: str):
        try:
            path = (root / file_path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise HTTPException(404, "Workspace file not found")
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(404, "Workspace file not found") from exc
        media_type = ("text/plain" if path.suffix.lower() in {".md", ".markdown"}
                      else mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        inline = (media_type.startswith("text/") and media_type != "text/html") or media_type in {
            "application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp",
        }
        return FileResponse(path, media_type=media_type, filename=path.name,
                            content_disposition_type="inline" if inline else "attachment",
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    return router
