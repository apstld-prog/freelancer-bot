# apply_worker_hotfix.py
# Usage: python apply_worker_hotfix.py
# Run from the project root (same folder where worker.py lives).
import re, sys, pathlib

path = pathlib.Path(__file__).parent / "worker.py"
txt = path.read_text(encoding="utf-8", errors="ignore")

# 1) Fix missing newline between counter and append for kariera
txt_new = txt.replace("_b=len(out) out += ph.fetch_kariera()", "_b=len(out)\n        out += ph.fetch_kariera()")

# 2) Generic safeguard: if a pattern like `_b=len(out) out +=` exists anywhere, insert newline
txt_new = re.sub(r"(_b\s*=\s*len\(out\))\s+(out\s*\+=)", r"\1\n        \2", txt_new)

# 3) Optional: ensure there is a newline after imports before first def if logging injection caused issues
if "log = logging.getLogger("worker")" in txt_new and "\n\nlog = logging.getLogger("worker")\ndef " in txt_new:
    pass  # already fine

# Write back only if changed
if txt_new != txt:
    path.write_text(txt_new, encoding="utf-8")
    print("Hotfix applied to worker.py")
else:
    print("Nothing to change. worker.py already OK.")
