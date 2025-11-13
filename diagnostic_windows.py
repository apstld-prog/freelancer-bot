# diagnostic_windows.py
import os
import sys
import json
import platform

ROOT = os.path.abspath(os.getcwd())

print("=== DIAGNOSTIC — WINDOWS LOCAL CHECK ===")
print(f"CWD: {ROOT}")
print(f"OS : {platform.system()} {platform.release()}")
print("")

result = {
    "cwd": ROOT,
    "os": platform.system(),
    "missing_files": [],
    "encoding_issues": [],
    "syntax_errors": [],
    "notes": [],
}

# --------------------------------------------------
# 1. Έλεγχος βασικών αρχείων
# --------------------------------------------------
required_files = [
    "app.py",
    "bot.py",
    "server.py",
    "config.py",
    "db.py",
    "db_events.py",
    "db_keywords.py",
    "handlers_start.py",
    "handlers_ui.py",
    "handlers_jobs.py",
    "handlers_admin.py",
    "platform_freelancer.py",
    "platform_peopleperhour.py",
    "platform_skywalker.py",
    "start.sh",
    "safe_restart.sh",
    "requirements.txt",
]

print(">> Checking required files...")
for name in required_files:
    if not os.path.exists(os.path.join(ROOT, name)):
        print(f"   [MISSING] {name}")
        result["missing_files"].append(name)
    else:
        print(f"   [OK]      {name}")
print("")

# --------------------------------------------------
# 2. Έλεγχος .env αρχείων (αν υπάρχουν)
# --------------------------------------------------
env_files = [".env", "freelancer-bot.env"]
env_found = {}

print(">> Checking env files (.env, freelancer-bot.env)...")
for ef in env_files:
    path = os.path.join(ROOT, ef)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Δεν τυπώνουμε όλο το περιεχόμενο για λόγους ασφαλείας
            print(f"   [OK] {ef} (size {len(content)} bytes)")
            env_found[ef] = True
        except Exception as e:
            print(f"   [ERR] {ef}: {e}")
            env_found[ef] = False
    else:
        print(f"   [MISS] {ef} not found")
        env_found[ef] = False
print("")

result["env_files"] = env_found

# --------------------------------------------------
# 3. Έλεγχος BOM / Encoding και Syntax για .py αρχεία
# --------------------------------------------------
print(">> Checking encoding (BOM) & syntax on .py files...")
for entry in os.listdir(ROOT):
    if not entry.endswith(".py"):
        continue
    path = os.path.join(ROOT, entry)

    # 3a. BOM check
    try:
        with open(path, "rb") as f:
            data = f.read(3)
        if data == b"\xef\xbb\xbf":
            print(f"   [BOM] {entry} has UTF-8 BOM")
            result["encoding_issues"].append(f"{entry}: UTF-8 BOM")
        else:
            print(f"   [OK ] {entry} encoding header")
    except Exception as e:
        print(f"   [ERR] {entry} reading bytes: {e}")
        result["encoding_issues"].append(f"{entry}: read error {e}")
        continue

    # 3b. Syntax check
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        compile(src, entry, "exec")
    except SyntaxError as e:
        msg = f"{entry}: SyntaxError line {e.lineno} - {e.msg}"
        print(f"        -> {msg}")
        result["syntax_errors"].append(msg)
    except Exception as e:
        msg = f"{entry}: Error {e}"
        print(f"        -> {msg}")
        result["syntax_errors"].append(msg)

print("")

# --------------------------------------------------
# 4. Γρήγορες σημειώσεις
# --------------------------------------------------
if result["missing_files"]:
    result["notes"].append("Some core files are missing.")
if result["encoding_issues"]:
    result["notes"].append("Some .py files have UTF-8 BOM or encoding issues.")
if result["syntax_errors"]:
    result["notes"].append("There are Python syntax errors that must be fixed.")
if not (result["missing_files"] or result["encoding_issues"] or result["syntax_errors"]):
    result["notes"].append("All basic Windows-side checks look OK.")

print("=== SUMMARY (JSON) ===")
print(json.dumps(result, indent=2, ensure_ascii=False))
print("=== END WINDOWS DIAGNOSTIC ===")
