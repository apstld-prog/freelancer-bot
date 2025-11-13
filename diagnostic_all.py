# ULTIMATE DIAGNOSTIC SCRIPT (Full Mode – Option B)
# Compatible with Render + Windows
import os, platform, subprocess, json, datetime, sys

print("=== ULTIMATE DIAGNOSTIC REPORT ===")

data = {}
data["timestamp"] = datetime.datetime.utcnow().isoformat()
data["cwd"] = os.getcwd()
data["os"] = platform.system()
data["python"] = sys.version

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        return str(e)

# ----------------------------------
# FILESYSTEM CHECKS
# ----------------------------------
required = [
    "app.py","bot.py","server.py","config.py","db.py",
    "db_events.py","db_keywords.py","start.sh","safe_restart.sh",
    "utils.py","handlers_start.py","handlers_ui.py"
]
data["missing_files"] = [f for f in required if not os.path.exists(f)]
data["render_ls"] = run("ls -la")

# ----------------------------------
# ENVIRONMENT CHECKS
# ----------------------------------
env_names = [
    "TELEGRAM_BOT_TOKEN","WEBHOOK_SECRET","RENDER_EXTERNAL_HOSTNAME",
    "DATABASE_URL","WORKER_INTERVAL","KEYWORD_FILTER_MODE","PORT"
]
data["env"] = {e: os.getenv(e) for e in env_names}

# ----------------------------------
# PROCESS CHECKS
# ----------------------------------
data["processes"] = run("ps aux")
data["workers"] = run("ps aux | grep worker_")
data["uvicorn"] = run("ps aux | grep uvicorn")
data["bot_process"] = run("ps aux | grep bot.py")

# ----------------------------------
# TELEGRAM WEBHOOK STATUS
# ----------------------------------
token = os.getenv("TELEGRAM_BOT_TOKEN")
if token:
    data["webhook_info"] = run(f"curl -s https://api.telegram.org/bot{token}/getWebhookInfo")
else:
    data["webhook_info"] = "NO TELEGRAM TOKEN FOUND"

# ----------------------------------
# SERVER ENDPOINT CHECK
# ----------------------------------
data["server_root_test"] = run("curl -s http://127.0.0.1:10000/")
secret = os.getenv("WEBHOOK_SECRET")
if secret:
    data["server_webhook_test"] = run(
        f"curl -s -X POST http://127.0.0.1:10000/{secret} "
        "-d '{{}}' -H 'Content-Type: application/json'"
    )
else:
    data["server_webhook_test"] = "NO WEBHOOK_SECRET SET"

# ----------------------------------
# DB TABLES + SCHEMA CHECK
# ----------------------------------
dburl = os.getenv("DATABASE_URL")
if dburl:
    data["db_tables"] = run("psql \"$DATABASE_URL\" -c \"\\\\dt\"")
    data["db_user_preview"] = run("psql \"$DATABASE_URL\" -c \"SELECT * FROM app_user LIMIT 5;\"")
    data["db_keyword_preview"] = run("psql \"$DATABASE_URL\" -c \"SELECT * FROM keyword LIMIT 5;\"")
    data["db_event_preview"] = run("psql \"$DATABASE_URL\" -c \"SELECT * FROM feed_event ORDER BY id DESC LIMIT 5;\"")
else:
    data["db_tables"] = "NO DATABASE_URL FOUND"

# ----------------------------------
# LOGS CHECK (LAST 20 LINES FOR EACH)
# ----------------------------------
def tail(path):
    if not os.path.exists(path):
        return "NOT FOUND"
    return run(f"tail -n 20 {path}")

data["logs"] = {
    "server": tail("logs/server.log"),
    "freelancer": tail("logs/worker_freelancer.log"),
    "pph": tail("logs/worker_pph.log"),
    "skywalker": tail("logs/worker_skywalker.log"),
}

# ----------------------------------
# OUTPUT
# ----------------------------------
print(json.dumps(data, indent=2))
print("=== END OF ULTIMATE DIAGNOSTIC ===")
