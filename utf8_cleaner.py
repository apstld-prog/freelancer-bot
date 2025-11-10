import os

TARGET_EXT = {'.py', '.txt', '.md', '.sql', '.json', '.sh'}
REPORT = "utf8_report.txt"


def remove_bom(path):
    with open(path, 'rb') as f:
        data = f.read()

    if data.startswith(b'\xEF\xBB\xBF'):
        data = data[3:]
        with open(path, 'wb') as f:
            f.write(data)
        return True

    return False


def main():
    with open(REPORT, 'w', encoding='utf-8') as rep:
        rep.write("UTF-8 Cleaner (Python version)\n")
        rep.write("====================================\n")

        for root, dirs, files in os.walk("."):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in TARGET_EXT:
                    full = os.path.join(root, name)
                    changed = remove_bom(full)
                    rep.write(f"{'CLEANED' if changed else 'OK     '} : {full}\n")

        rep.write("\nDone.\n")


if __name__ == "__main__":
    main()

