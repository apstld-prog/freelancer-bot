import os, sys, json, subprocess, platform, shutil

print("=== SUPER DIAGNOSTIC PRO — FULL MODE ===")

data = {}

# ---------------------------------------
# WINDOWS LOCAL CHECKS
# ---------------------------------------
root = os.getcwd()
data["cwd"] = root
data["os"] = platform.system()

targets = [
    "app.py", "bot.py", "server.py", "start.sh",
    "requirements.txt", "config.py", "db.py", "db_events.py"
]

missing = [t for t in targets if not os.path.exists(t)]
data["missing_local_files"] = missing

# Read .env files
env_files = [".env", "freelancer-bot.env"]
env_data = {}

for ef in env_files:
    if os.path.exists(ef):
        try:
            with open(ef, "r", encoding="utf-8") as f:
                env_data[ef] = f.read()
        except:
            env_data[ef] = "ERROR READING"
    else:
        env_data[ef] = "NOT FOUND"

data["env_files"] = env_data


# ---------------------------------------
# RENDER SHELL CHECKS
# (Executed only if running on Render)
# ---------------------------------------
def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        return str(e)

render_info = {}

# Check if running on Render
if "RENDER" in root or "/opt/render" in root:
    render_info["mode"] = "RUNNING ON RENDER"

    render_info["ps_aux"] = run_cmd("ps aux")

    # Check port 10000
    port_script = (
        "import psutil\n"
        "for p in psutil.process_iter(['pid','name']):\n"
        "    try:\n"
        "        for c in p.net_connections(kind='inet'):\n"
        "            if c.laddr and c.laddr.port == 10000:\n"
        "                print('PROC', p.pid, p.name(), 'USES 10000')\n"
        "    except: pass\n"
    )

    cmd = f"python3 -c \"{port_script.replace('\"', '\\\"')}\""
    render_info["port_10000"] = run_cmd(cmd)

else:
    render_info["mode"] = "WINDOWS LOCAL (not on Render)"

data["render_checks"] = render_info


# ---------------------------------------
# OUTPUT
# ---------------------------------------
print(json.dumps(data, indent=2, ensure_ascii=False))
