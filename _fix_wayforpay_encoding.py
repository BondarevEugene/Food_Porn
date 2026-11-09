from pathlib import Path
import ast
import io
import tokenize

path = Path("app/bot/handlers/wayforpay.py")
source = path.read_text(encoding="utf-8")
backup = path.with_suffix(".py.bak_encoding")

backup.write_text(source, encoding="utf-8")

tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
replacements = []

for token in tokens:
    if token.type != tokenize.STRING:
        continue

    try:
        original = ast.literal_eval(token.string)
    except (ValueError, SyntaxError):
        continue

    if not isinstance(original, str):
        continue

    try:
        restored = original.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        continue

    if restored == original:
        continue

    if not any("\u0400" <= char <= "\u04ff" for char in restored):
        continue

    replacements.append((token.start, token.end, token.string, restored))

print(f"Найдено потенциально повреждённых строк: {len(replacements)}")

for start, end, old, new in replacements:
    print(f"Строка {start[0]}: {new}")

print(f"Резервная копия: {backup}")