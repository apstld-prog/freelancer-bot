# diagnostic_all.py — FULL SYSTEM DIAGNOSTICS (ENHANCED)

import os, platform, subprocess, json, sys, shutil
from datetime import datetime

print("=== FULL DIAGNOSTIC REPORT ===")

data = {}
data["timestamp"] = datetime.utcnow().isoformat()
data["cwd"] = os.getcwd()
data["os"] = platform.system()
data["python"] = sys.version

required = [
    "app.py","bot.py","server.py","config.py","db.py","db_events.py",
    "db_keywords.py","handlers_start.py","handlers_ui.py","handlers_jobs.py",
    "handlers_admin.py","platform_freelancer.py","platform_peopleperhour.py",
    "platform_skywalker.py","start.sh","safe_restart.sh","requirements.txt"
]
data["missing_files"] = [f for f in required if not os.path.exists(f)]

env_data = {}
for f in [".env", "freelancer-bot.env"]:
    env_data[f] = os.path.exists(f)
data["env_files"] = env_data

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        return str(e)

inside_render = os.path.exists("/opt/render")

if inside_render:
    data["render_ls"] = run("ls -la")
    data["render_ps"] = run("ps aux | grep python")
    data["workers"] = run("ps aux | grep worker_")
    data["uvicorn"] = run("ps aux | grep uvicorn")

    port_script = "tmp_port_check.py"
    with open(port_script, "w", encoding="utf-8") as f:
        f.write(
            "import psutil, json\n"
            "out=[]\n"
            "for p in psutil.process_iter(['pid','name']):\n"
            "  try:\n"
            "    for c in p.connections(kind='inet'):\n"
            "      if c.laddr and c.laddr.port==10000:\n"
            "        out.append({'pid':p.pid,'name':p.name()})\n"
            "  except: pass\n"
            "print(json.dumps(out))\n"
        )
    data["port_10000"] = run("python3 tmp_port_check.py")
    os.remove(port_script)

else:
    data["render"] = "Not in Render environment"

try:
    import psycopg2
    url = os.getenv("DATABASE_URL")
    if url:
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        data["db_tables"] = cur.fetchall()
        conn.close()
    else:
        data["db_tables"] = "DATABASE_URL missing"
except Exception as e:
    data["db_error"] = str(e)

print(json.dumps(data, indent=2))
print("=== END ===")
