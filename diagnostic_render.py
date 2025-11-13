import os, subprocess, json, time

print("=== SUPER RENDER DIAGNOSTIC ===")

def run(cmd):
    try:
        return subprocess.check_output(
            cmd, shell=True,
            stderr=subprocess.STDOUT,
            text=True
        )
    except Exception as e:
        return str(e)

data = {}

# ---------------------------------------
# 1) Περιεχόμενα φακέλου
# ---------------------------------------
data["ls"] = run("ls -la")

# ---------------------------------------
# 2) Λίστα διεργασιών (python, uvicorn, workers)
# ---------------------------------------
data["ps_python"] = run("ps aux | grep python")
data["ps_uvicorn"] = run("ps aux | grep uvicorn")
data["ps_all"] = run("ps aux")

# ---------------------------------------
# 3) Port scan για 10000
# ---------------------------------------
port_script = """
import psutil, json
out=[]
for p in psutil.process_iter(['pid','name']):
    try:
        for c in p.connections(kind='inet'):
            if c.laddr and c.laddr.port==10000:
                out.append({
                    'pid': p.pid,
                    'name': p.name(),
                    'status': p.status(),
                    'exe': p.exe() if p.exe() else '',
                })
    except:
        pass
print(json.dumps(out))
"""
open("port_check_tmp.py","w").write(port_script)
data["port_scan"] = run("python3 port_check_tmp.py")
os.remove("port_check_tmp.py")

# ---------------------------------------
# 4) Έλεγχος εάν τρέχει το uvicorn από Render service
# ---------------------------------------
data["service_check"] = run("ps aux | grep '/opt/render/project/src/.venv/bin/python'")

# ---------------------------------------
# 5) Έλεγχος .venv / modules
# ---------------------------------------
data["pip_list"] = run("/opt/render/project/src/.venv/bin/pip list")

# ---------------------------------------
# 6) Webhook check
# ---------------------------------------
data["webhook"] = run("curl -s https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo")

# ---------------------------------------
# 7) Τελευταίες 40 γραμμές logs
# ---------------------------------------
data["logs_tail"] = run("tail -n 40 /var/log/render/*.log 2>/dev/null")

# ---------------------------------------
# ΤΕΛΙΚΗ ΕΚΤΥΠΩΣΗ JSON
# ---------------------------------------
print("\n=== JSON OUTPUT ===")
print(json.dumps(data, indent=2, ensure_ascii=False))
print("\n=== END OF DIAGNOSTIC ===")
