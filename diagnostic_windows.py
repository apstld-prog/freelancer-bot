import os, json, platform

print("=== WINDOWS BOT DIAGNOSTIC ===")

data = {}
root = os.getcwd()
data["cwd"] = root
data["os"] = platform.system()

required = [
    "app.py","bot.py","server.py","config.py",
    "db.py","db_events.py","db_keywords.py",
    "handlers_start.py","handlers_ui.py","handlers_jobs.py","handlers_admin.py",
    "platform_freelancer.py","platform_peopleperhour.py","platform_skywalker.py",
    "start.sh","safe_restart.sh","requirements.txt"
]

missing = []
for f in required:
    if not os.path.exists(os.path.join(root,f)):
        missing.append(f)

data["missing_files"] = missing

print(json.dumps(data, indent=2, ensure_ascii=False))
input("\nPress ENTER to exit...")
