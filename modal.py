"""
modelOS (MDL) Standalone Miner — modeloslab pool
Mode: Miner only (no HF_TOKEN required)
GPU: 2x H100 (80GB)
Image: modeloslab/vllm-miner:latest
"""

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MDL_ADDRESS = "mdl1p6cy5sl8348asqrt63qnngm2688g526fqhnaerewuxqdr6w7jl2aqlmwxcq"
WORKER      = "container-h100"
POOL_HOST   = "stratum.modeloslab.xyz"
POOL_PORT   = "5566"
PORT        = int(os.environ.get("PORT", "11134"))

miner_status = {"running": False, "pid": None}


def run_miner():
    print("[server] --- nvidia-smi check ---", flush=True)
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=15)
        print(out.stdout or out.stderr, flush=True)
    except Exception as e:
        print(f"[server] nvidia-smi failed: {e}", flush=True)
    print("[server] --- end nvidia-smi check ---", flush=True)

    print(f"[server] modelOS MDL Miner — 2x H100", flush=True)
    print(f"[server] Pool      : {POOL_HOST}:{POOL_PORT}", flush=True)
    print(f"[server] MDL wallet: {MDL_ADDRESS}", flush=True)
    print(f"[server] Worker    : {WORKER}", flush=True)

    env = os.environ.copy()
    env.update({
        "POOL_HOST":                    POOL_HOST,
        "POOL_PORT":                    POOL_PORT,
        "POOL_TLS":                     "false",
        "MDL_ADDRESS":                  MDL_ADDRESS,
        "POOL_WORKER":                  WORKER,
        "MODELOS_MINER_ONLY":           "1",
        "MODELOS_GPU_MEMORY_UTILIZATION": "0.90",
        "MODELOS_COORDINATOR_URL":      "https://pool.modeloslab.xyz",
        "MODELOS_DIRECT_MINER_V2":      "1",
        "MINER_NO_GATEWAY":             "true",
        "MINER_NO_VLLM_PLUGIN":        "true",
    })

    # The entrypoint of modeloslab/vllm-miner handles mining automatically via env vars
    # We exec the default entrypoint script
    candidates = [
        "/entrypoint.sh",
        "/start.sh",
        "/app/start.sh",
        "/app/entrypoint.sh",
    ]
    entrypoint = None
    for c in candidates:
        if os.path.exists(c):
            entrypoint = c
            break

    if entrypoint:
        print(f"[server] Using entrypoint: {entrypoint}", flush=True)
        cmd = ["bash", entrypoint]
    else:
        # fallback: list root to help diagnose
        print("[server] No entrypoint found, listing /:", flush=True)
        os.system("ls -la /")
        os.system("ls -la /app 2>/dev/null || true")
        sys.exit(1)

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
    )
    miner_status["running"] = True
    miner_status["pid"] = proc.pid
    print(f"[server] Miner PID: {proc.pid}", flush=True)

    for line in iter(proc.stdout.readline, b""):
        print(line.decode(errors="replace").strip(), flush=True)

    miner_status["running"] = False
    code = proc.wait()
    print(f"[server] Miner exited with code {code}", flush=True)


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = (
                '{"status":"ok","miner_running":%s,"pid":%s}'
                % (
                    str(miner_status["running"]).lower(),
                    miner_status["pid"] if miner_status["pid"] else "null",
                )
            )
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    miner_thread = threading.Thread(target=run_miner, daemon=True)
    miner_thread.start()

    print(f"[server] Health server listening on 0.0.0.0:{PORT}", flush=True)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[server] Shutting down", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
