# ULTIMATE DIAGNOSTIC V2 (Enhanced)
import os, platform, subprocess, json, re, importlib, socket, time, psutil

print("=== ULTIMATE DIAGNOSTIC REPORT V2 ===")

data = {}
data["cwd"] = os.getcwd()
data["os"] = platform.system()
data["python"] = platform.python_version()
data["hostname"] = socket.gethostname()

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        return str(e)

# ENV variables
env_keys = ["TELEGRAM_BOT_TOKEN","WEBHOOK_SECRET","RENDER_EXTERNAL_HOSTNAME","DATABASE_URL","PORT"]
data["env"] = {k: os.environ.get(k,"") for k in env_keys}

# Basic env checks
data["token_valid_format"] = bool(re.match(r"^\d+:[A-Za-z0-9_-]+$", data["env"].get("TELEGRAM_BOT_TOKEN","")))
data["secret_not_empty"] = data["env"].get("WEBHOOK_SECRET","") != ""
data["public_url_ok"] = bool(data["env"].get("RENDER_EXTERNAL_HOSTNAME","").strip())

# Port status
port = data["env"].get("PORT","10000")
data["port_binding"] = run(f"lsof -i:{port}")[:300]

# File encoding test
suspicious = []
for root,_,files in os.walk("."):
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(root,f)
            try:
                with open(p,"rb") as fh:
                    b = fh.read()
                    if b.startswith(b"\xef\xbb\xbf"):
                        suspicious.append(p)
            except:
                pass
data["utf8_bom_files"] = suspicious

# Import tests
modules = ["server","bot","handlers_start","handlers_settings","handlers_help","handlers_jobs","db","platform_peopleperhour","worker_pph"]
import_status = {}
for m in modules:
    try:
        importlib.import_module(m)
        import_status[m] = "OK"
    except Exception as e:
        import_status[m] = str(e)
data["import_status"] = import_status

# Worker processes
data["workers"] = run("ps aux | grep worker_")
data["uvicorn"] = run("ps aux | grep uvicorn")

# DNS test
def test_dns(host):
    try:
        socket.gethostbyname(host)
        return True
    except:
        return False

data["dns"] = {
    "peopleperhour.com": test_dns("www.peopleperhour.com"),
    "freelancer.com": test_dns("www.freelancer.com"),
    "skywalker.gr": test_dns("www.skywalker.gr")
}

# Network test simple fetch
def curl_test(url):
    try:
        out = run(f"curl -I --max-time 5 {url}")
        return out[:200]
    except:
        return "ERR"

data["network_tests"] = {
    "PPH": curl_test("https://www.peopleperhour.com/freelance-jobs?rss=1"),
    "Freelancer": curl_test("https://www.freelancer.com/rss.xml"),
    "Skywalker": curl_test("https://www.skywalker.gr/jobs/feed")
}

# Memory & CPU
try:
    data["memory"] = dict(psutil.virtual_memory()._asdict())
    data["cpu_load"] = psutil.getloadavg()
except:
    data["memory"] = "psutil missing"
    data["cpu_load"] = "psutil missing"

# Database
db_url = data["env"].get("DATABASE_URL","")
if db_url:
    data["db_tables"] = run(f'psql "{db_url}" -c "\dt"')

# Webhook info
token = data["env"].get("TELEGRAM_BOT_TOKEN","")
if token:
    data["webhook_info"] = run(f"curl -s https://api.telegram.org/bot{token}/getWebhookInfo")

print(json.dumps(data, indent=2, ensure_ascii=False))
print("=== END ===")
