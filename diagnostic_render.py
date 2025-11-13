import subprocess, json

print("=== RENDER BOT DIAGNOSTIC ===")

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        return str(e)

data = {
    "ls": run("ls -la"),
    "ps": run("ps aux"),
    "port_scan": run("python3 - << 'EOF'\nimport psutil, json\nx=[]\nfor p in psutil.process_iter(['pid','name']):\n try:\n  for c in p.connections(kind='inet'):\n   if c.laddr and c.laddr.port==10000:\n    x.append({'pid':p.pid,'name':p.name()})\n except: pass\nprint(json.dumps(x))\nEOF")
}

print(json.dumps(data, indent=2, ensure_ascii=False))
