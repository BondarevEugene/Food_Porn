
from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "app" / "config.py"

tree = ast.parse(CONFIG.read_text(encoding="utf-8"))

fields = []
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "Settings":
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)

files = [
    path for folder in ("app", "src", "tests")
    if (ROOT / folder).exists()
    for path in (ROOT / folder).rglob("*.py")
    if "__pycache__" not in path.parts
]

print(f"\nНайдено параметров Settings: {len(fields)}")
print(f"Проверено Python-файлов: {len(files)}")

for field in fields:
    pattern = re.compile(rf"\b{re.escape(field)}\b")
    matches = []

    for path in files:
        if path == CONFIG:
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeError, OSError):
            continue

        for number, line in enumerate(lines, 1):
            if pattern.search(line) and not line.lstrip().startswith("#"):
                matches.append((path.relative_to(ROOT), number, line.strip()))

    print(f"\n{'=' * 65}")
    print(f"{field}: {len(matches)} упоминаний")

    for path, number, line in matches[:12]:
        print(f"  {path}:{number} | {line[:160]}")

    if len(matches) > 12:
        print(f"  ... ещё {len(matches) - 12}")
