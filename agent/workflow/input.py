from dataclasses import dataclass


MAX_IMAGES = 8


@dataclass(frozen=True)
class UserInput:
    text: str = ""
    images: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "images", tuple(self.images))
        if not isinstance(self.text, str) or any(not isinstance(image, str) or not image for image in self.images):
            raise ValueError("无效的消息或图片引用")
        if not self.text.strip() and not self.images:
            raise ValueError("消息需要包含文字或图片")
        if len(self.images) > MAX_IMAGES or len(set(self.images)) != len(self.images):
            raise ValueError("每条消息最多包含 8 张图片，不能重复")


def normalize_input(value: str | UserInput) -> UserInput:
    return value if isinstance(value, UserInput) else UserInput(text=value)
