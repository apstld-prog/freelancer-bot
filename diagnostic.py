
#!/usr/bin/env python3
# SUPER DIAGNOSTIC (UTF-8 SAFE)
import os, sys, subprocess, json, importlib, re
from pathlib import Path

BASE = Path(os.getcwd())
REPORT = []

def add(status, msg):
    REPORT.append({"status": status, "message": msg})

def safe_read(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return ""

def check_encoding():
    for path in BASE.rglob("*.py"):
        try:
            data = path.read_bytes()
            if data.startswith(b'\xef\xbb\xbf'):
                add("FAIL", f"[Encoding] {path} has UTF-8 BOM")
            else:
                add("PASS", f"[Encoding] {path} OK")
        except Exception as e:
            add("FAIL", f"[Encoding] {path}: {e}")

def check_syntax():
    for path in BASE.rglob("*.py"):
        proc = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                              capture_output=True)
        if proc.returncode != 0:
            add("FAIL", f"[Syntax] {path}: {proc.stderr.decode(errors='ignore')}")
        else:
            add("PASS", f"[Syntax] {path} OK")

def check_imports():
    for path in BASE.glob("*.py"):
        mod = path.stem
        try:
            importlib.invalidate_caches()
            importlib.import_module(mod)
            add("PASS", f"[Import] {mod} OK")
        except Exception as e:
            add("FAIL", f"[Import] {mod}: {e}")

REQUIRED = [
    "bot.py","server.py","start.sh","requirements.txt","db.py","db_events.py"
]

def check_required_files():
    for fname in REQUIRED:
        if not (BASE / fname).exists():
            add("FAIL", f"[File missing] {fname}")
        else:
            add("PASS", f"[File exists] {fname}")

    workers = list((BASE / "workers").glob("worker_*.py"))
    if not workers:
        add("FAIL", "No workers in workers/")
    else:
        add("PASS", f"{len(workers)} workers detected")

def check_start_sh():
    if (BASE/"start.sh").exists():
        add("PASS","start.sh OK")
    else:
        add("FAIL","start.sh missing")

def check_requirements():
    req = BASE/"requirements.txt"
    if not req.exists():
        add("FAIL","requirements.txt missing")
        return
    missing=[]
    for line in req.read_text().splitlines():
        pkg=line.strip().split("==")[0]
        if not pkg: continue
        try:
            importlib.import_module(pkg)
        except Exception:
            missing.append(pkg)
    if missing:
        add("FAIL", f"Missing modules (except psycopg2): {missing}")
    else:
        add("PASS","All modules installed (except DB drivers)")

def check_critical_functions():
    def scan(fname, keywords):
        content = safe_read(BASE/fname)
        for kw in keywords:
            if kw in content:
                add("PASS", f"{kw} found in {fname}")
            else:
                add("FAIL", f"{kw} MISSING in {fname}")

    scan("bot.py",["build_application","ApplicationBuilder","CommandHandler","CallbackQueryHandler"])
    scan("server.py",["FastAPI","build_application"])
    scan("db.py",["create_engine","get_session"])
    scan("db_events.py",["ensure_feed_events_schema"])

def check_webhook_prefix():
    cfg = BASE/"config.py"
    if not cfg.exists():
        add("FAIL","config.py missing")
        return
    s = safe_read(cfg)
    m = re.search(r"WEBHOOK_SECRET\s*=\s*['\"](.+?)['\"]", s)
    if m:
        add("PASS", f"Webhook secret: {m.group(1)}")
    else:
        add("FAIL", "WEBHOOK_SECRET missing")

def check_fastapi_route():
    sp = BASE/"server.py"
    if not sp.exists():
        add("FAIL","server.py missing")
        return
    t = safe_read(sp)
    if "async def root" in t and '"status": "ok"' in t:
        add("PASS","FastAPI root '/' OK")
    else:
        add("FAIL","Root route missing or wrong")

def main():
    add("INFO","=== SUPER DIAGNOSTIC (UTF-8 SAFE) START ===")
    check_required_files()
    check_encoding()
    check_syntax()
    check_imports()
    check_start_sh()
    check_requirements()
    check_critical_functions()
    check_webhook_prefix()
    check_fastapi_route()
    add("INFO","=== SUPER DIAGNOSTIC END ===")
    print(json.dumps(REPORT, indent=2))
    input("\nPress Enter to close...")

if __name__=="__main__":
    main()
