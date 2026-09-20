"""QuantLab — daemon kernel Notebook (host).

Menjalankan kernel Python persisten per user DI DALAM bubblewrap (seperti
judge, tapi prosesnya hidup terus supaya variabel antar-sel tersimpan).
Flask (gunicorn multi-worker) memanggil daemon ini lewat HTTP lokal
127.0.0.1:5211 — jadi state kernel tidak bergantung pada worker mana yang
menangani request.

Jalankan via systemd: quantlab-kernel.service
"""
import atexit
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

REPO = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(REPO, ".venv")
WORKER = os.path.join(REPO, "notebook_kernel.py")
DATASETS = os.path.join(REPO, "data", "notebook_datasets")
WORKROOT = os.path.join(REPO, "data", "notebook_work")
HOST = os.environ.get("KERNELD_HOST", "127.0.0.1")
PORT = int(os.environ.get("KERNELD_PORT", "5211"))
EXEC_TIMEOUT = float(os.environ.get("KERNEL_EXEC_TIMEOUT", "30"))
IDLE_KILL = float(os.environ.get("KERNEL_IDLE", "1800"))
MAX_KERNELS = int(os.environ.get("KERNELD_MAX", "6"))
CODE_CAP = 20_000
USER_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


class _Spawner:
    """Thread panjang yang khusus mem-fork kernel bwrap.

    PENTING: bwrap `--die-with-parent` mengikat sandbox ke THREAD yang
    mem-fork-nya (PR_SET_PDEATHSIG = sinyal saat thread parent mati), jadi
    spawn dari thread handler HTTP = kernel ikut mati begitu request selesai.
    Semua spawn harus lewat thread ini yang hidup selama proses kerneld.
    """

    def __init__(self):
        self.jobs = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            cmd, reply = self.jobs.get()
            try:
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    errors="replace", env={"PATH": "/usr/bin:/bin"},
                    start_new_session=True,
                )
                reply.put(proc)
            except Exception as exc:  # noqa: BLE001
                reply.put(exc)

    def spawn(self, cmd, timeout=15.0):
        reply = queue.Queue(1)
        self.jobs.put((cmd, reply))
        proc = reply.get(timeout=timeout)
        if isinstance(proc, Exception):
            raise proc
        return proc


_SPAWNER = _Spawner()


class Kernel:
    """Satu proses python sandbox milik satu user."""

    def __init__(self, user: str):
        self.user = user
        self.lock = threading.Lock()
        self.responses = queue.Queue()
        self.proc = None
        self.alive = False
        self.created_at = time.time()
        self.last_used = self.created_at
        self.exec_count = 0
        self.python = "?"
        self.exit_reason = ""
        self._spawn()

    def _cmd(self):
        work = os.path.join(WORKROOT, self.user)
        os.makedirs(work, mode=0o700, exist_ok=True)
        return [
            "/usr/bin/bwrap", "--unshare-all", "--die-with-parent",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/etc", "/etc",
            "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64",
            "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/sbin", "/sbin",
            "--proc", "/proc",
            "--dev", "/dev",
            "--ro-bind", VENV, "/venv",
            "--ro-bind", DATASETS, "/datasets",
            "--ro-bind", WORKER, "/kernel.py",
            "--bind", work, "/work",
            "--tmpfs", "/tmp",
            "--tmpfs", "/home",
            "--tmpfs", "/root",
            "--chdir", "/work",
            "--setenv", "HOME", "/work",
            "--setenv", "MPLCONFIGDIR", "/tmp/.mpl",
            "--setenv", "MPLBACKEND", "Agg",
            "--setenv", "OPENBLAS_NUM_THREADS", "1",
            "--setenv", "OMP_NUM_THREADS", "1",
            "--setenv", "PYTHONUNBUFFERED", "1",
            "--setenv", "PATH", "/usr/bin:/bin",
            "/venv/bin/python", "-E", "-s", "-B", "-u", "/kernel.py",
        ]

    def _spawn(self):
        # Spawn HARUS dari thread panjang (_SPAWNER), bukan thread handler
        # HTTP — lihat catatan di kelas _Spawner.
        proc = _SPAWNER.spawn(self._cmd())
        self.proc = proc
        self.alive = True
        self.created_at = time.time()
        threading.Thread(target=self._read_loop, args=(proc,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True).start()

    def _read_loop(self, proc):
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue  # tulisan liar kode user ke fd 1 → abaikan
                if self.proc is not proc:
                    return  # generasi kernel ini sudah digantikan
                if msg.get("type") == "ready":
                    self.python = msg.get("python", "?")
                    continue
                self.responses.put(msg)
        except Exception:
            pass
        finally:
            # Jangan klobber status generasi kernel yang lebih baru.
            if self.proc is proc:
                self.alive = False
                self.exit_reason = self.exit_reason or "kernel berhenti"

    def _drain_stderr(self, proc):
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    print(f"[kernel:{self.user}] {line}", flush=True)
        except Exception:
            pass

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def run(self, code: str, cell=None) -> dict:
        acquired = self.lock.acquire(timeout=8)
        if not acquired:
            return {"status": "busy",
                    "message": "Sel lain masih berjalan — tunggu selesai lalu coba lagi."}
        try:
            while True:  # buang sisa pesan lama (kalau ada)
                try:
                    self.responses.get_nowait()
                except queue.Empty:
                    break
            if not self.alive:
                self._spawn()  # kernel mati → hidupkan ulang otomatis
            self.last_used = time.time()
            try:
                self.send({"type": "exec", "code": code, "cell": cell})
            except (BrokenPipeError, OSError):
                self.alive = False
                return {"status": "dead",
                        "message": "Kernel mati saat menerima kode. Coba jalan lagi."}
            deadline = time.time() + EXEC_TIMEOUT
            while True:
                remain = deadline - time.time()
                if remain <= 0:
                    self.kill("timeout")
                    return {
                        "status": "timeout",
                        "message": (f"⏱ Kode berjalan lebih dari {int(EXEC_TIMEOUT)} detik "
                                    "dan dihentikan. Kernel di-restart — variabel direset."),
                        "stdout": "", "stderr": "", "result": None, "images": [],
                    }
                try:
                    msg = self.responses.get(timeout=min(remain, 0.5))
                except queue.Empty:
                    if not self.alive:
                        return {"status": "dead",
                                "message": "Kernel berhenti mendadak. Coba jalan lagi."}
                    continue
                self.exec_count += 1
                return {
                    "status": "error" if msg.get("error") else "ok",
                    "stdout": msg.get("stdout") or "",
                    "stderr": msg.get("stderr") or "",
                    "result": msg.get("result"),
                    "error": msg.get("error"),
                    "error_type": msg.get("error_type") or "",
                    "images": msg.get("images") or [],
                    "ms": msg.get("ms") or 0,
                    "n": msg.get("n") or self.exec_count,
                }
        finally:
            self.lock.release()

    def status(self):
        return {
            "alive": self.alive,
            "busy": self.lock.locked(),
            "python": self.python,
            "uptime_s": int(time.time() - self.created_at),
            "exec_count": self.exec_count,
        }

    def kill(self, reason="manual", proc=None):
        proc = proc or self.proc
        if proc is None:
            return
        self.exit_reason = reason
        if self.proc is proc:
            self.alive = False
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


class Manager:
    def __init__(self):
        self.kernels = {}
        self.global_lock = threading.Lock()

    def get(self, user):
        with self.global_lock:
            k = self.kernels.get(user)
            if k is not None and k.alive:
                return k
            if k is not None:
                k.kill("dead")
            if len(self.kernels) >= MAX_KERNELS:
                oldest = min(self.kernels.values(), key=lambda x: x.last_used)
                oldest.kill("evicted")
                self.kernels.pop(oldest.user, None)
            k = Kernel(user)
            self.kernels[user] = k
            return k

    def restart(self, user):
        with self.global_lock:
            k = self.kernels.pop(user, None)
        if k:
            k.kill("restart")
        return self.get(user)

    def reap(self):
        now = time.time()
        with self.global_lock:
            targets = [u for u, k in self.kernels.items()
                       if (not k.alive) or (now - k.last_used) > IDLE_KILL]
            for u in targets:
                k = self.kernels.pop(u)
                k.kill("idle" if k.alive else "dead")
        return len(targets)


MANAGER = Manager()


class Handler(BaseHTTPRequestHandler):
    server_version = "qlkernel/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[kerneld] %s\n" % (fmt % args))

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 3_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _user(self, data):
        user = str((data or {}).get("user") or "")
        return user if USER_RE.match(user) else None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True, "kernels": len(MANAGER.kernels),
                                    "time": int(time.time())})
        if path == "/status":
            qs = parse_qs(urlparse(self.path).query)
            user = (qs.get("user") or [""])[0]
            if not USER_RE.match(user):
                return self._json(400, {"error": "user invalid"})
            k = MANAGER.kernels.get(user)
            if not k:
                return self._json(200, {"exists": False, "alive": False})
            st = k.status()
            st["exists"] = True
            return self._json(200, st)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._body()
        user = self._user(data)
        if user is None:
            return self._json(400, {"error": "user invalid"})
        if path == "/exec":
            code = str(data.get("code") or "")
            if not code.strip():
                return self._json(200, {"status": "ok", "stdout": "", "stderr": "",
                                        "result": None, "images": [], "ms": 0})
            if len(code) > CODE_CAP:
                return self._json(200, {"status": "error", "error_type": "toolong",
                                        "error": f"Kode terlalu panjang (maks {CODE_CAP} karakter).",
                                        "stdout": "", "stderr": "", "result": None, "images": []})
            try:
                k = MANAGER.get(user)
                return self._json(200, k.run(code, data.get("cell")))
            except Exception as exc:  # noqa: BLE001
                return self._json(200, {"status": "error", "error_type": "kerneld",
                                        "error": f"Kernel gagal dijalankan: {exc}",
                                        "stdout": "", "stderr": "", "result": None, "images": []})
        if path == "/restart":
            try:
                MANAGER.restart(user)
                return self._json(200, {"status": "ok", "message": "Kernel di-restart. Variabel direset."})
            except Exception as exc:  # noqa: BLE001
                return self._json(200, {"status": "error",
                                        "error": f"Restart kernel gagal: {exc}",
                                        "stdout": "", "stderr": "", "result": None, "images": []})
        return self._json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST")
        self.end_headers()


def _reaper_loop():
    while True:
        time.sleep(60)
        try:
            n = MANAGER.reap()
            if n:
                print(f"[kerneld] reaper: {n} kernel dihentikan", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[kerneld] reaper error: {exc}", flush=True)


def shutdown():
    for k in list(MANAGER.kernels.values()):
        k.kill("shutdown")
    MANAGER.kernels.clear()


def main():
    atexit.register(shutdown)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    threading.Thread(target=_reaper_loop, daemon=True).start()
    print(f"[kerneld] listen di http://{HOST}:{PORT} "
          f"(timeout exec {EXEC_TIMEOUT:.0f}s, idle kill {IDLE_KILL:.0f}s)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
