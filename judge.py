"""QuantLab — Judge: eksekusi kode Python user dalam sandbox.

SEMUA eksekusi lewat bubblewrap: sistem /usr & /etc read-only, /home & /tmp
di-tmpfs (file pribadi user TIDAK terlihat), jaringan di-unshare (off),
venv di-ro-bind (numpy/pandas/matplotlib tersedia). RLIMIT CPU/mem/file
sebagai lapisan kedua. Output dibaca bertahap & dibatasi (2MB).
"""
import os
import re
import resource
import select
import subprocess
import sys
import tempfile
import time

TIMEOUT = 3            # detik
MEM_LIMIT = 768        # MB (OpenBLAS butuh virtual memori besar)
FILE_LIMIT = 1         # MB
OUTPUT_LIMIT = 2 * 1024 * 1024   # 2MB per stream

LIB_RE = re.compile(r"^\s*(import|from)\s+(numpy|pandas|matplotlib)\b", re.M)


def needs_lib(code):
    """Kompatibilitas: semua mode kini punya library."""
    return bool(LIB_RE.search(code or ""))


def _limits(mem_mb=MEM_LIMIT):
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT, TIMEOUT + 1))
    resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_LIMIT * 1024 * 1024,) * 2)


def _sandbox_command(code):
    """bubblewrap: sistem read-only + venv ro-bind, /home & /tmp tmpfs, net off."""
    venv_root = os.path.dirname(os.path.dirname(sys.executable))
    return [
        "/usr/bin/bwrap",
        "--unshare-all", "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/etc", "/etc",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/sbin", "/sbin",
        "--proc", "/proc",
        "--dev", "/dev",
        "--ro-bind", venv_root, "/venv",
        "--tmpfs", "/tmp",
        "--tmpfs", "/home",
        "--tmpfs", "/root",
        "--chdir", "/tmp",
        "--setenv", "HOME", "/tmp",
        "--setenv", "MPLCONFIGDIR", "/tmp/.mpl",
        "--setenv", "OPENBLAS_NUM_THREADS", "1",
        "--setenv", "OMP_NUM_THREADS", "1",
        "--setenv", "PATH", "/usr/bin:/bin",
        "/venv/bin/python", "-E", "-s", "-B", "-c", code,
    ]


def _read_limited(pipe, limit):
    """Baca pipe sampai EOF/limit. Return (data, truncated)."""
    chunks = []
    total = 0
    while True:
        ready, _, _ = select.select([pipe], [], [], 0.05)
        if not ready:
            if pipe.closed:
                break
            continue
        chunk = os.read(pipe.fileno(), 65536)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            chunks.append(chunk[: max(0, limit - (total - len(chunk)))])
            try:
                while os.read(pipe.fileno(), 65536):
                    pass
            except OSError:
                pass
            return b"".join(chunks), True
        chunks.append(chunk)
    return b"".join(chunks), False


def _normalize(s: str) -> str:
    lines = [ln.rstrip() for ln in (s or "").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def run_code(code: str, stdin: str = "", mode: str = "auto") -> dict:
    """Jalankan kode dengan stdin dalam sandbox bwrap.
    Return {ok, stdout, stderr, error_type}."""
    if len(code) > 8000:
        return {"ok": False, "stdout": "", "stderr": "Kode terlalu panjang (maks 8000 karakter).",
                "error_type": "toolong"}
    cmd = _sandbox_command(code)
    # env minimal: cegah kode user membaca SECRET_KEY dll dari environment
    env = {"PATH": "/usr/bin:/bin"}
    with tempfile.TemporaryDirectory() as td:
        t0 = time.time()
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=False,
                cwd=td, preexec_fn=_limits, env=env,
            )
        except OSError as e:
            return {"ok": False, "stdout": "", "stderr": f"Gagal menjalankan: {e}",
                    "error_type": "oserror"}
        try:
            p.stdin.write((stdin or "").encode())
            p.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        out_b, out_trunc = _read_limited(p.stdout, OUTPUT_LIMIT)
        err_b, err_trunc = _read_limited(p.stderr, OUTPUT_LIMIT)
        try:
            rc = p.wait(timeout=TIMEOUT)
            elapsed = time.time() - t0
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return {"ok": False, "stdout": out_b.decode("utf-8", "replace")[:2000],
                    "stderr": "Kode berjalan terlalu lama (>3 detik) dan dihentikan.",
                    "error_type": "timeout"}
        stdout = out_b.decode("utf-8", "replace")[:4000]
        stderr = err_b.decode("utf-8", "replace")[:2000]
        if out_trunc:
            stdout += "\n...[output dipotong: terlalu besar]"
        if err_trunc:
            stderr += "\n...[error dipotong]"
        if rc != 0 and elapsed >= TIMEOUT - 0.5:
            # bwrap menyamarkan exit code anak yang dibunuh RLIMIT_CPU → deteksi via waktu
            return {"ok": False, "stdout": stdout,
                    "stderr": "Kode berjalan terlalu lama (>3 detik) dan dihentikan.",
                    "error_type": "timeout"}
        return {"ok": rc == 0, "stdout": stdout, "stderr": stderr,
                "error_type": "" if rc == 0 else "runtime"}


def run_tests(code: str, tests) -> dict:
    """Jalankan solusi terhadap daftar tes [{input, output}].

    Return {passed, total, results: [{input, expected, got, ok}], error}.
    """
    results = []
    for t in tests:
        r = run_code(code, t.get("input", ""))
        got = _normalize(r["stdout"])
        exp = _normalize(t.get("output", ""))
        results.append({
            "input": t.get("input", ""),
            "expected": exp,
            "got": got,
            "ok": r["ok"] and got == exp,
            "error": r["stderr"].strip() if not r["ok"] else "",
        })
    passed = sum(1 for x in results if x["ok"])
    return {"passed": passed, "total": len(results), "results": results}


def friendly_error(stderr: str) -> str:
    """Terjemahkan error umum Python ke bahasa manusia."""
    s = (stderr or "").strip()
    if not s:
        return "Ada yang salah saat menjalankan kode."
    last = s.splitlines()[-1] if s.splitlines() else s
    if "SyntaxError" in s:
        return f"❌ Kesalahan penulisan kode: {last}"
    if "NameError" in s:
        return f"❌ Nama tidak dikenal: {last}"
    if "TypeError" in s:
        return f"❌ Tipe data tidak cocok: {last}"
    if "ValueError" in s:
        return f"❌ Nilai tidak valid: {last}"
    if "IndexError" in s:
        return "❌ Indeks list di luar jangkauan (IndexError)."
    if "KeyError" in s:
        return "❌ Kunci dict tidak ditemukan (KeyError)."
    if "ZeroDivisionError" in s:
        return "❌ Tidak bisa membagi dengan nol."
    if "EOFError" in s:
        return "❌ Kode meminta input (input()) tapi tidak ada data."
    if "IndentationError" in s:
        return "❌ Salah indentasi (spasi/tab) — cek rapikan kode."
    if "ModuleNotFoundError" in s:
        return "❌ Library tidak ada: " + last
    if "unexpected EOF" in s:
        return "❌ Kode belum selesai — ada kurung yang belum ditutup?"
    return f"❌ Error: {last}"
