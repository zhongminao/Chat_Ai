import shlex
from pathlib import Path

from ..workflow.input import UserInput


class ImageCommands:
    """Terminal transport for the same store/input/commands used by Web."""
    def __init__(self, agent):
        self.agent = agent
        self.pending: list[str] = []

    def add(self, source: str) -> dict:
        path = Path(source).expanduser()
        store = self.agent.images
        image = store.add_file(path)
        if image["id"] not in self.pending:
            self.pending.append(image["id"])
        return image

    def handle(self, text: str) -> bool:
        command = text.split(maxsplit=1)[0]
        if command not in {"/image", "/images", "/clear-images"}:
            return False
        parts = shlex.split(text)
        if command == "/image":
            if len(parts) != 2:
                raise ValueError("用法：/image <文件路径，已有图片使用会话保存路径>")
            image = self.add(parts[1])
            print(f"已添加图片：\n{self.agent.images.describe(image)}")
        elif command == "/images":
            for image in self.agent.images.list():
                marker = " [待发送]" if image["id"] in self.pending else ""
                print(f"{image['name']}{marker}\n{self.agent.images.path(image['id']).resolve()}")
        else:
            self.pending.clear()
            print("已移除待发送的图片")
        return True

    def take_input(self, text: str) -> UserInput:
        value = self.agent.prepare_input(UserInput("" if text == "/send" else text, tuple(self.pending)))
        self.pending.clear()
        return value
