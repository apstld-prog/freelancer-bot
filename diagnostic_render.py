# diagnostic_render.py
import os
import json
import subprocess
import platform

print("=== RENDER DIAGNOSTIC ===")
print(f"OS: {platform.system()} {platform.release()}")
print(f"CWD: {os.getcwd()}")
print("")

def run(cmd: str) -> str:
    try:
        out = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT, text=True
        )
        return out
    except subprocess.CalledProcessError as e:
        return f"[EXIT {e.returncode}] {e.output.strip()}"
    except Exception as e:
        return f"[ERROR] {e}"

data = {}

print(">> ps aux | grep 'uvicorn\\|worker_'")
data["ps_uvicorn_workers"] = run("ps aux | egrep 'uvicorn|worker_' || echo 'NONE'")
print(data["ps_uvicorn_workers"])
print("")

print(">> ls -la")
data["ls_la"] = run("ls -la")
print(data["ls_la"])
print("")

print(">> Checking port 10000 via psutil (if installed)...")

port_info = "psutil not available"
try:
    import psutil  # type: ignore

    procs = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            for c in p.connections(kind="inet"):
                if c.laddr and c.laddr.port == 10000:
                    procs.append({"pid": p.pid, "name": p.name()})
        except Exception:
            pass
    port_info = json.dumps(procs)
except Exception as e:
    port_info = f"psutil import failed: {e}"

data["port_10000"] = port_info
print(port_info)
print("")

# Environment variables of interest (masked)
print(">> Environment variables (masked)")
ENV_KEYS = [
    "BOT_TOKEN",
    "DATABASE_URL",
    "WEBHOOK_SECRET",
    "RENDER_EXTERNAL_URL",
    "WORKER_INTERVAL",
    "KEYWORD_FILTER_MODE",
]

env_report = {}
for key in ENV_KEYS:
    val = os.environ.get(key)
    if val is None:
        env_report[key] = "MISSING"
        print(f"   {key}: MISSING")
    else:
        if len(val) <= 6:
            masked = "***"
        else:
            masked = val[:3] + "..." + val[-3:]
        env_report[key] = f"SET ({masked})"
        print(f"   {key}: SET ({masked})")
print("")

data["env"] = env_report

print("=== JSON SUMMARY ===")
print(json.dumps(data, indent=2, ensure_ascii=False))
print("=== END RENDER DIAGNOSTIC ===")
