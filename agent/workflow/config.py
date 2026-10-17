import yaml
from dataclasses import dataclass, field
from pathlib import Path

from ..model.catalog import ModelCatalog
from ..tools.approval import MODES


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    model: dict[str, str]
    workspace: Path
    storage_dir: Path
    providers_file: Path
    spill: dict[str, int | bool | str]
    mcp: dict[str, str]
    max_rounds: int
    system_prompt: str
    child_system_prompt: str
    context: dict = field(default_factory=dict)
    approval_mode: str = "audit"


def _path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def load(path: Path | None = None) -> Config:
    config_path = (path or DEFAULT_CONFIG).expanduser().resolve()
    root = config_path.parent
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    max_rounds = data.get("max_rounds", 200)
    if type(max_rounds) is not int or max_rounds < 1:
        raise ValueError("config.yaml: max_rounds 必须是正整数")
    prompts = {}
    for name in ("system_prompt", "child_system_prompt"):
        key = f"{name}_file"
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config.yaml: {key} 必须是非空文件路径")
        prompt_path = _path(root, value.strip())
        try:
            content = prompt_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"config.yaml: {key} 无法读取 {prompt_path}: {exc}") from exc
        if not content:
            raise ValueError(f"config.yaml: {key} 文件内容不能为空：{prompt_path}")
        prompts[name] = content

    providers_file = _path(
        root,
        data.get("providers_file", "agent/model/providers/providers.yaml"),
    )
    catalog = ModelCatalog(providers_file)
    context = dict(data.get("context") or {})
    context.setdefault("enabled", False)
    if type(context["enabled"]) is not bool:
        raise ValueError("config.yaml: context.enabled 必须是布尔值")
    context.setdefault("trigger_tokens", 110592)
    if type(context["trigger_tokens"]) is not int or context["trigger_tokens"] < 1:
        raise ValueError("config.yaml: context.trigger_tokens 必须是正整数")
    context["prompt_file"] = _path(root, context.get("prompt_file", "prompts/context_compaction.md"))
    if context["enabled"] and not context["prompt_file"].is_file():
        raise ValueError("config.yaml: context.prompt_file 不存在")
    workspace = _path(root, data.get("workspace", "."))
    storage_dir = _path(root, data.get("storage_dir", "storage"))
    approval_mode = (data.get("approval") or {}).get("mode", "audit")
    if approval_mode not in MODES:
        raise ValueError("config.yaml: approval.mode 必须为 audit 或 full_access")

    return Config(
        model=catalog.default().as_dict(),
        workspace=workspace,
        storage_dir=storage_dir,
        providers_file=providers_file,
        spill=data.get("spill", {}),
        mcp=data.get("mcp", {}),
        max_rounds=max_rounds,
        context=context,
        approval_mode=approval_mode,
        **prompts,
    )
