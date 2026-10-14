from dataclasses import dataclass


@dataclass(frozen=True)
class SwitchModel:
    provider: str
    model: str


@dataclass(frozen=True)
class RenameImage:
    image: str
    name: str
