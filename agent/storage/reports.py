"""Save immutable Markdown reports with stable image references."""
import re
from pathlib import Path

from .session import Session


def save(session: Session, run_id: str, content: str, workspace: Path) -> tuple[Path, str]:
    images = session.images
    requests = {}
    for event in session.events.read():
        if event.get("runId") != run_id:
            continue
        if event["type"] == "tool.requested":
            requests[event["callId"]] = event.get("arguments", {})
        elif event["type"] == "tool.completed":
            for image in event.get("model_images", []):
                url = images.url(image)
                sources = {str(images.path(image["id"])), images.path(image["id"]).as_posix()}
                if source := requests.get(event["callId"], {}).get("path"):
                    sources.update({source, str((workspace / source).resolve())})
                for source in sources:
                    content = content.replace(f"]({source})", f"]({url})").replace(f"](<{source}>)", f"]({url})")
    # Saved MCP images remain referenceable even for non-visual models.
    for image in images.list():
        referenced = re.search(r"!\[[^\n]*?\]\(" + re.escape(images.url(image)) + r"\)", content)
        if not referenced:
            continue  # Only explicit Markdown references opt an image into the report.
        content += f"\n\n<!-- image_file: {images.path(image['id']).resolve()} -->"
    path = session.directory / "reports" / f"{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)
    return path.resolve(), content.rstrip()
