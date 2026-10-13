import yaml
from dataclasses import dataclass
from pathlib import Path

from ..model.catalog import ModelCatalog


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    model: dict[str, str]
    workspace: Path
    event_log: Path
    providers_file: Path
    spill: dict[str, int | bool | str]
    mcp: dict[str, str]


def _path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def load(path: Path | None = None) -> Config:
    config_path = (path or DEFAULT_CONFIG).expanduser().resolve()
    root = config_path.parent
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    providers_file = _path(
        root,
        data.get("providers_file", "agent/model/providers/providers.yaml"),
    )
    catalog = ModelCatalog(providers_file)
    workspace = _path(root, data.get("workspace", "."))
    event_log = _path(root, data.get("event_log", "storage/events.jsonl"))

    return Config(
        model=catalog.default().as_dict(),
        workspace=workspace,
        event_log=event_log,
        providers_file=providers_file,
        spill=data.get("spill", {}),
        mcp=data.get("mcp", {}),
    )
