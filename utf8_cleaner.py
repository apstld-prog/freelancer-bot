import os
import sys
import codecs
from datetime import datetime

# ----------------------------------------------------------
# UTF-8 NO-BOM CLEANER
# ----------------------------------------------------------

EXCLUDE_DIRS = {
    ".git",
    "backups",
    "__pycache__"
}

EXCLUDE_EXT = {
    ".zip", ".png", ".jpg", ".jpeg", ".gif",
    ".pdf", ".exe", ".dll", ".so"
}

VALID_EXT = {
    ".py", ".txt", ".md", ".json", ".yml", ".yaml",
    ".env", ".cfg", ".ini", ".toml", ".sh", ".sql"
}

REPORT_FILE = "utf8_report.txt"


def has_bom(raw_bytes: bytes) -> bool:
    return raw_bytes.startswith(codecs.BOM_UTF8)


def clean_file(path: str) -> tuple[bool, int]:
    """Returns (changed, size_diff)"""
    try:
        with open(path, "rb") as f:
            raw = f.read()

        if not has_bom(raw):
            return False, 0

        # Remove UTF-8 BOM
        new_raw = raw[3:]

        with open(path, "wb") as f:
            f.write(new_raw)

        return True, len(raw) - len(new_raw)

    except Exception as e:
        print(f"[ERROR] Cannot process {path}: {e}")
        return False, 0


def scan_and_clean(root: str):
    changed_files = []
    total_bytes = 0

    for subdir, dirs, files in os.walk(root):
        # skip excluded dirs
        if any(x in subdir.replace("\\", "/").split("/") for x in EXCLUDE_DIRS):
            continue

        for file in files:
            ext = os.path.splitext(file)[1].lower()

            if ext in EXCLUDE_EXT:
                continue

            if ext not in VALID_EXT:
                continue

            full_path = os.path.join(subdir, file)

            try:
                with open(full_path, "rb") as f:
                    raw = f.read()

                if has_bom(raw):
                    changed, diff = clean_file(full_path)
                    if changed:
                        changed_files.append((full_path, diff))
                        total_bytes += diff
                        print(f"[FIXED] {full_path}  (-{diff} bytes)")

            except Exception as e:
                print(f"[ERROR] {full_path}: {e}")

    return changed_files, total_bytes


def write_report(changed_files, total_bytes):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("UTF-8 CLEAN REPORT\n")
        f.write("---------------------------------------\n")
        f.write(f"Timestamp: {datetime.now()}\n\n")

        if not changed_files:
            f.write("No BOM issues found.\n")
            return

        for path, diff in changed_files:
            f.write(f"FIXED: {path}  (-{diff} bytes)\n")

        f.write("\n---------------------------------------\n")
        f.write(f"TOTAL FIXED FILES: {len(changed_files)}\n")
        f.write(f"TOTAL BYTES REMOVED: {total_bytes}\n")
        f.write("---------------------------------------\n")


if __name__ == "__main__":
    print("=======================================")
    print(" UTF-8 CLEANER - Remove BOM from files ")
    print("=======================================")

    root = os.getcwd()
    print(f"Scanning: {root}")
    print("---------------------------------------")

    changed, bytes_removed = scan_and_clean(root)

    print("\n---------------------------------------")
    print(" Operation finished.")
    print(f" Fixed files: {len(changed)}")
    print(f" Bytes removed: {bytes_removed}")
    print(" Report saved to utf8_report.txt")
    print("---------------------------------------")

    input("\nPress ENTER to exit...")
