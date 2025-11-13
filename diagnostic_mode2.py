
import subprocess, json, os

print("=== MODE 2 — Render Remote Diagnostic ===")

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        return str(e)

data={}
data["render_ls"]=run("ls -la")
data["render_ps"]=run("ps aux")

# Port check
script = "import psutil, json\nout=[]\n" \
         "for p in psutil.process_iter(['pid','name']):\n" \
         " try:\n" \
         "  for c in p.connections(kind='inet'):\n" \
         "   if c.laddr and c.laddr.port==10000:\n" \
         "    out.append({'pid':p.pid,'name':p.name()})\n" \
         " except: pass\n" \
         "print(json.dumps(out))\n"

with open("tmp_render_port.py","w",encoding="utf-8") as f:
    f.write(script)

data["port_check"]=run("python3 tmp_render_port.py")

try: os.remove("tmp_render_port.py")
except: pass

print(json.dumps(data,indent=2,ensure_ascii=False))
