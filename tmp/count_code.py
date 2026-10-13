from pathlib import Path
import argparse

SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "dist", "build"}
EXTENSIONS = {".py", ".yaml", ".yml"}


def count_file(path: Path):
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    total = len(lines)
    nonempty = sum(bool(line.strip()) for line in lines)
    effective = sum(bool(line.strip()) and not line.lstrip().startswith("#") for line in lines)
    return total, nonempty, effective


def count_project(root: Path):
    result = {ext: [0, 0, 0, 0] for ext in sorted(EXTENSIONS)}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if any(part in SKIP for part in path.parts):
            continue
        total, nonempty, effective = count_file(path)
        item = result[path.suffix.lower()]
        item[0] += 1
        item[1] += total
        item[2] += nonempty
        item[3] += effective
    return result


def show(root: Path):
    print(f"\n{root}")
    print("类型    文件数  总行数  非空行  去注释")
    print("------  ------  ------  ------  ------")
    result = count_project(root)
    for ext, values in result.items():
        print(f"{ext:<6}  {values[0]:>6}  {values[1]:>6}  {values[2]:>6}  {values[3]:>6}")
    total = [sum(values[i] for values in result.values()) for i in range(4)]
    print(f"合计    {total[0]:>6}  {total[1]:>6}  {total[2]:>6}  {total[3]:>6}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    roots = args.paths or [Path("/home/zhong/mydisk/tools/chat_ai"), Path("/home/zhong/mydisk/tools/chat")]
    for root in roots:
        show(root)
