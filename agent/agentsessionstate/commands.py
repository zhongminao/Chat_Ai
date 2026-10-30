from dataclasses import dataclass


@dataclass(frozen=True)
class SwitchModel:
    provider: str
    model: str
