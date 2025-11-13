# ULTIMATE DIAGNOSTIC (Auto-generated)
import os, platform, subprocess, json, re, importlib

print("=== ULTIMATE DIAGNOSTIC REPORT ===")

data = {}
data["cwd"] = os.getcwd()
data["os"] = platform.system()
data["python"] = platform.python_version()

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        return str(e)

# Load env
env_keys = ["TELEGRAM_BOT_TOKEN","WEBHOOK_SECRET","RENDER_EXTERNAL_HOSTNAME","DATABASE_URL","PORT"]
env = {k: os.environ.get(k,"") for k in env_keys}
data["env"] = env

# Check handlers functions
handler_requirements = {
    "handlers_start":"register_start_handlers",
    "handlers_settings":"register_settings_handlers",
    "handlers_help":"register_help_handlers",
    "handlers_jobs":"register_jobs_handlers",
    "handlers_admin":"register_admin_handlers",
    "handlers_ui":"register_ui_handlers"
}

handler_status = {}
for module, func in handler_requirements.items():
    try:
        m = importlib.import_module(module)
        handler_status[module] = hasattr(m, func)
    except Exception as e:
        handler_status[module] = str(e)
data["handler_functions"] = handler_status

# Token format check
token = env.get("TELEGRAM_BOT_TOKEN","")
data["token_valid_format"] = bool(re.match(r"^\d+:[A-Za-z0-9_-]+$", token))

# Secret check
data["secret_not_empty"] = env.get("WEBHOOK_SECRET","") != ""

# Public URL check
pub = env.get("RENDER_EXTERNAL_HOSTNAME","")
data["public_url_ok"] = bool(pub.strip())

# Server listening
port = env.get("PORT","10000")
data["server_port_check"] = run(f"lsof -i:{port}")[:200]

# Test imports
imports = ["server","bot","handlers_start","handlers_settings","handlers_help"]
import_status = {}
for i in imports:
    try:
        importlib.import_module(i)
        import_status[i] = True
    except Exception as e:
        import_status[i] = str(e)
data["import_status"] = import_status

# Worker processes
data["workers"] = run("ps aux | grep worker_")

# Uvicorn process
data["uvicorn"] = run("ps aux | grep uvicorn")

# Webhook info
if token:
    data["webhook_info"] = run(f"curl -s https://api.telegram.org/bot{token}/getWebhookInfo")

# DB tables
db_url = env.get("DATABASE_URL","")
if db_url:
    data["db_tables"] = run(f'psql "{db_url}" -c "\dt"')

# Output
print(json.dumps(data, indent=2, ensure_ascii=False))
print("=== END ===")
