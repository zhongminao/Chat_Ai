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
                sources = {str(images.root / f"{image['id']}.{image['extension']}")}
                if source := requests.get(event["callId"], {}).get("path"):
                    sources.update({source, str((workspace / source).resolve())})
                for source in sources:
                    content = content.replace(f"]({source})", f"]({url})").replace(f"](<{source}>)", f"]({url})")
    # Only explicit Markdown references opt an image into the report.
    references = set(re.findall(r"!\[[^\n]*?\]\(([^)]+)\)", content))
    for image in images.list():
        if images.url(image) in references:
            path = (images.root / f"{image['id']}.{image['extension']}").resolve()
            content += f"\n\n<!-- image_file: {path} -->"
    path = session.directory / "reports" / f"{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)
    return path.resolve(), content.rstrip()
