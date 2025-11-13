# FINAL ONE-FILE DIAGNOSTIC
import os, platform, subprocess, json

print("=== ONE-FILE DIAGNOSTIC (Windows + Render) ===")

data = {}
data["cwd"] = os.getcwd()
data["os"] = platform.system()

# -----------------------------------
# CHECK REQUIRED BOT FILES
# -----------------------------------
required = [
    "app.py","bot.py","server.py","config.py","db.py","db_events.py",
    "db_keywords.py","handlers_start.py","handlers_ui.py","handlers_jobs.py",
    "handlers_admin.py","platform_freelancer.py","platform_peopleperhour.py",
    "platform_skywalker.py","start.sh","safe_restart.sh","requirements.txt"
]

data["missing_files"] = [f for f in required if not os.path.exists(f)]

# -----------------------------------
# ENV CHECK
# -----------------------------------
env_data = {}
for f in [".env", "freelancer-bot.env"]:
    env_data[f] = os.path.exists(f)
data["env_files"] = env_data

# -----------------------------------
# DETECT RENDER
# -----------------------------------
inside_render = os.path.exists("/opt/render")

def run(cmd: str):
    """Run shell command safely"""
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.STDOUT
        )
    except Exception as e:
        return str(e)


# -----------------------------------
# RENDER DIAGNOSTICS
# -----------------------------------
if inside_render:

    data["render_ls"] = run("ls -la")
    data["render_ps"] = run("ps aux")

    # Create temporary script for port scan
    port_code = (
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

    with open("tmp_port.py", "w", encoding="utf-8") as f:
        f.write(port_code)

    data["render_port"] = run("python3 tmp_port.py")

    try:
        os.remove("tmp_port.py")
    except:
        pass

else:
    data["render_info"] = "Not inside Render environment."

# -----------------------------------
# PRINT FULL JSON OUTPUT
# -----------------------------------
print(json.dumps(data, indent=2, ensure_ascii=False))
print("=== END ===")
