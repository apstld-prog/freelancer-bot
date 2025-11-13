
import os,platform,json

print("=== MODE 1 — Windows Local Diagnostic ===")

data={}
data["cwd"]=os.getcwd()
data["os"]=platform.system()

targets=[
"app.py","bot.py","server.py","config.py","db.py","db_events.py",
"db_keywords.py","start.sh","safe_restart.sh","requirements.txt"
]
missing=[t for t in targets if not os.path.exists(t)]
data["missing"]=missing

env_files=[".env","freelancer-bot.env"]
env={}
for e in env_files:
    if os.path.exists(e):
        try:
            env[e]=open(e,encoding="utf-8").read()
        except:
            env[e]="ERR"
data["env"]=env

print(json.dumps(data,indent=2,ensure_ascii=False))
