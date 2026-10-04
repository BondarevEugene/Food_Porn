import os

# Папки и файлы, которые нам не нужны в контексте
IGNORE_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.idea', 'data', 'storage', 'node_modules', 'alembic'}
IGNORE_EXTS = {'.pyc', '.png', '.jpg', '.jpeg', '.mp4', '.sqlite3', '.pdf', '.zip', '.exe', '.lock'}

output_file = 'food_porn_codebase.txt'

with open(output_file, 'w', encoding='utf-8') as outfile:
    for root, dirs, files in os.walk('.'):
        # Исключаем ненужные директории
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in IGNORE_EXTS or file == output_file or file == 'pack_repo.py':
                continue

            filepath = os.path.join(root, file)
            try:
                with open(filepath, encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(f"\n\n{'='*80}\n")
                    outfile.write(f"FILE: {filepath}\n")
                    outfile.write(f"{'='*80}\n\n")
                    outfile.write(content)
            except Exception as e:
                print(f"Пропущен файл {filepath} (ошибка чтения: {e})")

print(f"✅ Готово! Весь код собран в файл: {output_file}")