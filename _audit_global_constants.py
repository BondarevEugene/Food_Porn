
from pathlib import Path

TERMS = [
    "usd_exchange_rate",
    "price_electronic_uah",
    "price_print_uah",
    "price_electronic_usd",
    "price_print_usd",
    "portmone_gateway_url",
    "print_shop_email",
    "print_poster_width_mm",
    "print_poster_height_mm",
    "print_dpi",
]

EXCLUDED = {
    ".venv", "venv", "__pycache__", ".git",
    "node_modules", ".pytest_cache", ".mypy_cache",
    "_backups", "dist", "build",
}

root = Path(__file__).resolve().parent

files = [
    p for p in root.rglob("*.py")
    if p.is_file()
    and p.name != "_audit_global_constants.py"
    and p.name != "config.py"
    and not any(
        part in EXCLUDED or part.startswith("_crm_backup")
        or part.startswith("_crm_update")
        for part in p.relative_to(root).parts
    )
]

print(f"Проверено активных Python-файлов: {len(files)}")

for term in TERMS:
    print(f"\n{'=' * 70}")
    print(f"{term}")

    count = 0

    for path in files:
        try:
            lines = path.read_text(
                encoding="utf-8-sig",
                errors="replace",
            ).splitlines()
        except OSError:
            continue

        for number, line in enumerate(lines, 1):
            if term in line:
                count += 1
                print(
                    f"{path.relative_to(root)}:{number} | "
                    f"{line.strip()}"
                )

    print(f"Реальных упоминаний вне config.py: {count}")

print("\nACTIVE PYTHON AUDIT COMPLETED")
