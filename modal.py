"""
modelOS (MDL) Standalone Miner — modeloslab pool
Mode: Miner only — bypass vLLM entrypoint, run miner binary directly
GPU: 2x H100 (80GB)
Image: modeloslab/vllm-miner:latest
"""

import os
import subprocess
import sys
import threading
import glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MDL_ADDRESS = "mdl1p6cy5sl8348asqrt63qnngm2688g526fqhnaerewuxqdr6w7jl2aqlmwxcq"
WORKER      = "container-h100"
POOL_HOST   = "stratum.modeloslab.xyz"
POOL_PORT   = "5566"
PORT        = int(os.environ.get("PORT", "11134"))

miner_status = {"running": False, "pid": None}


def find_miner_binary():
    """Search common locations for the miner binary inside the image."""
    candidates = [
        "/app/miner",
        "/app/modelos-miner",
        "/app/mdl-miner",
        "/usr/local/bin/miner",
        "/usr/bin/miner",
    ]
    # Also search by glob
    globs = [
        "/app/*miner*",
        "/usr/local/bin/*miner*",
        "/opt/*miner*",
        "/root/*miner*",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    for pattern in globs:
        matches = [m for m in glob.glob(pattern)
                   if os.path.isfile(m) and os.access(m, os.X_OK)]
        if matches:
            return matches[0]
    return None


def diagnose():
    print("[server] === IMAGE DIAGNOSTICS ===", flush=True)
    for d in ["/", "/app", "/opt", "/usr/local/bin", "/root"]:
        try:
            files = os.listdir(d)
            print(f"[server] {d}: {files}", flush=True)
        except Exception as e:
            print(f"[server] {d}: {e}", flush=True)
    print("[server] === END DIAGNOSTICS ===", flush=True)


def run_miner():
    print("[server] --- nvidia-smi check ---", flush=True)
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=15)
        print(out.stdout or out.stderr, flush=True)
    except Exception as e:
        print(f"[server] nvidia-smi failed: {e}", flush=True)
    print("[server] --- end nvidia-smi check ---", flush=True)

    print(f"[server] MDL wallet: {MDL_ADDRESS}", flush=True)
    print(f"[server] Pool      : {POOL_HOST}:{POOL_PORT}", flush=True)
    print(f"[server] Worker    : {WORKER}", flush=True)

    binary = find_miner_binary()

    if binary:
        print(f"[server] Found miner binary: {binary}", flush=True)
        env = os.environ.copy()
        env.update({
            "POOL_HOST":               POOL_HOST,
            "POOL_PORT":               POOL_PORT,
            "POOL_TLS":                "false",
            "MDL_ADDRESS":             MDL_ADDRESS,
            "POOL_WORKER":             WORKER,
            "MODELOS_MINER_ONLY":      "1",
            "MODELOS_DIRECT_MINER_V2": "1",
            "MINER_NO_GATEWAY":        "true",
            "MINER_NO_VLLM_PLUGIN":    "true",
            "SKIP_VLLM":               "1",
            "NO_VLLM":                 "1",
        })
        cmd = [binary,
               "--pool", f"{POOL_HOST}:{POOL_PORT}",
               "--address", MDL_ADDRESS,
               "--worker", WORKER]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
        )
    else:
        print("[server] Miner binary not found — running diagnostics", flush=True)
        diagnose()
        # Try entrypoint with all vLLM disabled
        env = os.environ.copy()
        env.update({
            "POOL_HOST":               POOL_HOST,
            "POOL_PORT":               POOL_PORT,
            "POOL_TLS":                "false",
            "MDL_ADDRESS":             MDL_ADDRESS,
            "POOL_WORKER":             WORKER,
            "MODELOS_MINER_ONLY":      "1",
            "MODELOS_DIRECT_MINER_V2": "1",
            "MINER_NO_GATEWAY":        "true",
            "MINER_NO_VLLM_PLUGIN":    "true",
            "SKIP_VLLM":               "1",
            "NO_VLLM":                 "1",
            "VLLM_SKIP":               "1",
        })
        entrypoint = next(
            (e for e in ["/entrypoint.sh", "/start.sh", "/app/start.sh", "/app/entrypoint.sh"]
             if os.path.exists(e)), None
        )
        if entrypoint:
            print(f"[server] Falling back to entrypoint: {entrypoint}", flush=True)
            cmd = ["bash", entrypoint]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
            )
        else:
            print("[server] No entrypoint found either. Exiting.", flush=True)
            sys.exit(1)

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
            body = ('{"status":"ok","miner_running":%s,"pid":%s}'
                    % (str(miner_status["running"]).lower(),
                       miner_status["pid"] if miner_status["pid"] else "null"))
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    threading.Thread(target=run_miner, daemon=True).start()
    print(f"[server] Health server listening on 0.0.0.0:{PORT}", flush=True)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
