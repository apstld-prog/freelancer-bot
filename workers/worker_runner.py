#!/usr/bin/env python3
import subprocess
import time
import sys
import os

WORKERS = [
    "worker_freelancer.py",
    "worker_pph.py",
    "worker_skywalker.py"
]

def run_worker(path):
    return subprocess.Popen([sys.executable, path])

if __name__ == "__main__":
    print("=== WORKER RUNNER STARTED ===")

    processes = []
    base = os.path.dirname(os.path.abspath(__file__))

    for w in WORKERS:
        p = run_worker(os.path.join(base, w))
        processes.append(p)
        print(f"[RUNNER] Started {w} (pid {p.pid})")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopping workers...")
        for p in processes:
            p.terminate()
        sys.exit(0)


