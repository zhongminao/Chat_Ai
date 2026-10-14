"""Save immutable Markdown reports with stable references to published images."""
import re
from pathlib import Path

from .images import ImageStore
from .session import Session


def save(session: Session, run_id: str, content: str, workspace: Path) -> tuple[Path, str]:
    images = ImageStore(session.directory)
    requests = {}
    published = {}
    for event in session.events.read():
        if event.get("runId") != run_id:
            continue
        if event["type"] == "tool.requested":
            requests[event["callId"]] = event.get("arguments", {})
        elif event["type"] == "tool.completed":
            for image in event.get("images", []):
                published[image["id"]] = image
                url = images.url(image)
                sources = {str(images.path(image["id"])), images.path(image["id"]).as_posix()}
                if source := requests.get(event["callId"], {}).get("path"):
                    sources.update({source, str((workspace / source).resolve())})
                for source in sources:
                    content = content.replace(f"]({source})", f"]({url})").replace(f"](<{source}>)", f"]({url})")
    for image in published.values():
        if not re.search(r"!\[[^\n]*?\]\(" + re.escape(images.url(image)) + r"\)", content):
            content += "\n\n" + images.markdown(image)
        content += f"\n\n<!-- image_file: {images.path(image['id']).resolve()} -->"
    path = session.directory / "reports" / f"{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)
    return path.resolve(), content.rstrip()
