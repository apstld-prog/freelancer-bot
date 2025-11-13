
import os, sys, platform, subprocess, json

print("=== SUPER DIAGNOSTIC PRO — FULL MODE ===")

data = {}
data["cwd"] = os.getcwd()
data["os"] = platform.system()

# Check key local files
targets = [
    "app.py","bot.py","server.py","start.sh","safe_restart.sh",
    "requirements.txt","config.py","db.py","db_events.py","db_keywords.py",
    "handlers_start.py","handlers_ui.py","handlers_jobs.py","handlers_admin.py",
    "platform_freelancer.py","platform_peopleperhour.py","platform_skywalker.py"
]
missing = [t for t in targets if not os.path.exists(t)]
data["missing_local_files"] = missing

# Collect env files content
env_files = [".env","freelancer-bot.env"]
env_data = {}
for ef in env_files:
    if os.path.exists(ef):
        try:
            with open(ef,"r",encoding="utf-8") as f:
                env_data[ef] = f.read()
        except:
            env_data[ef] = "ERROR READING"
data["env_files"] = env_data

# Render-side commands (safe)
def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        return str(e)

data["render_ls"] = run("ls -la")
data["render_ps"] = run("ps aux")

# Port scan without shell quoting issues
port_script = (
    "import psutil\n"
    "import json\n"
    "out=[]\n"
    "for p in psutil.process_iter(['pid','name']):\n"
    "    try:\n"
    "        for c in p.connections(kind='inet'):\n"
    "            if c.laddr and c.laddr.port==10000:\n"
    "                out.append({'pid':p.pid,'name':p.name()})\n"
    "    except: pass\n"
    "print(json.dumps(out))\n"
)

with open("tmp_port_check.py","w",encoding="utf-8") as f:
    f.write(port_script)

data["render_port"] = run("python3 tmp_port_check.py")

try:
    os.remove("tmp_port_check.py")
except:
    pass

print(json.dumps(data, indent=2, ensure_ascii=False))
