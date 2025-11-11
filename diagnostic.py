#!/usr/bin/env python3
import os, subprocess, sys, importlib, json

REPORT = []
BASE = os.getcwd()

def add(status, msg):
    REPORT.append({"status": status, "message": msg})

def check_utf8():
    for root, _, files in os.walk(BASE):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "rb") as fh:
                    data = fh.read()
                    if data.startswith(b'\xef\xbb\xbf'):
                        add("FAIL", f"{path} has UTF-8 BOM")
                    else:
                        add("PASS", f"{path} encoding OK")

def check_syntax():
    for root, _, files in os.walk(BASE):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                proc = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True)
                if proc.returncode != 0:
                    add("FAIL", f"Syntax error in {path}: {proc.stderr.decode()}")
                else:
                    add("PASS", f"Syntax OK: {path}")

def check_imports():
    for root, _, files in os.walk(BASE):
        for f in files:
            if f.endswith(".py"):
                module = f[:-3]
                try:
                    importlib.invalidate_caches()
                    importlib.import_module(module)
                    add("PASS", f"Import OK: {module}")
                except Exception as e:
                    add("FAIL", f"Import FAIL: {module} — {e}")

def main():
    add("INFO", "Running diagnostics...")
    check_utf8()
    check_syntax()
    check_imports()
    print(json.dumps(REPORT, indent=2))

if __name__ == "__main__":
    main()
