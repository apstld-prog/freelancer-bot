
# diagnostic_fresh.py — full file
import os, sys, json, subprocess, importlib

print("=== FRESH DIAGNOSTIC ===")

data = {}

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        return str(e)

data["cwd"] = os.getcwd()
data["python"] = sys.version
data["env"] = {k: os.environ.get(k,"") for k in os.environ.keys()}

# Check workers
data["workers"] = run("ps aux | grep worker_")

# Check uvicorn
data["uvicorn"] = run("ps aux | grep uvicorn")

# Import platforms
platforms = [
    "platform_freelancer",
    "platform_peopleperhour",
    "platform_peopleperhour_proxy",
    "platform_skywalker",
    "platform_kariera"
]

imp = {}
for p in platforms:
    try:
        importlib.import_module(p)
        imp[p] = "OK"
    except Exception as e:
        imp[p] = str(e)
data["platform_imports"] = imp

# Test fetch functions
def safe_test(module, func):
    try:
        m = importlib.import_module(module)
        f = getattr(m, func)
        items = f([])
        return len(items)
    except Exception as e:
        return str(e)

data["pph_test"] = safe_test("platform_peopleperhour","get_items")
data["freelancer_test"] = safe_test("platform_freelancer","get_items")
data["skywalker_test"] = safe_test("platform_skywalker","get_items")

print(json.dumps(data, indent=2, ensure_ascii=False))
print("=== END FRESH ===")
