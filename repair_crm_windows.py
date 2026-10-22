"""Repair the Mini CRM Windows test and run the installation with all tests enabled."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

OLD_HASH = 'e7c4a8d54a84eb32967d75b8518e6f0ae76e5f7f093de99aafe685a86cf7eab5'
NEW_HASH = 'a4efeb825b8265dd563b3dbfeec09106d18724ff9242c61d64405593dddaae20'
RELATIVE = "tests/test_bootstrap_runtime.py"


def main():
    root = Path(__file__).resolve().parent
    bundle = root / "_crm_update_1_0"
    installer = bundle / "apply_update.py"
    manifest_path = bundle / "manifest.json"
    test_path = bundle / "payload" / RELATIVE
    if not (root / "launcher.py").is_file() or not all(
        file.is_file() for file in (installer, manifest_path, test_path)
    ):
        raise RuntimeError("Place repair_crm_windows.py beside launcher.py; keep the _crm_update_1_0 folder there.")
    current = test_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    fingerprint = hashlib.sha256(current.encode()).hexdigest()
    if fingerprint not in (OLD_HASH, NEW_HASH):
        raise RuntimeError("Unexpected test version. No files changed; send payload/tests/test_bootstrap_runtime.py for adaptation.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = [row for row in manifest["files"] if row["path"] == RELATIVE]
    if len(entries) != 1 or entries[0]["new_hash"] not in (OLD_HASH, NEW_HASH):
        raise RuntimeError("Unexpected manifest. No files changed.")
    fixed = current
    if fingerprint == OLD_HASH:
        fixed = current.replace("import os\n", "", 1).replace(
            "        os.kill(os.getpid(), signal.SIGTERM)",
            "        # os.kill(..., SIGTERM) uses TerminateProcess on Windows and bypasses\n"
            "        # Python's shutdown handler. raise_signal exercises it on both platforms.\n"
            "        signal.raise_signal(signal.SIGTERM)",
            1,
        )
    if hashlib.sha256(fixed.encode()).hexdigest() != NEW_HASH:
        raise RuntimeError("Repair checksum failed. No files changed.")
    if fingerprint != NEW_HASH or entries[0]["new_hash"] != NEW_HASH:
        backup = bundle / "_windows_fix_backup"
        backup.mkdir(exist_ok=True)
        for source in (test_path, manifest_path):
            destination = backup / source.name
            if not destination.exists():
                shutil.copy2(source, destination)
        test_path.write_text(fixed, encoding="utf-8")
        entries[0]["new_hash"] = NEW_HASH
        manifest["version"] = "1.0.1"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Windows test repaired. Installing Mini CRM with all tests enabled.", flush=True)
    result = subprocess.run([sys.executable, str(installer), "--apply"], cwd=root, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print("ERROR:", str(exc))
        raise SystemExit(1) from None
