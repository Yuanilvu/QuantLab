"""QuantLab — kernel notebook (worker di dalam sandbox bubblewrap).

Proses Python persisten: variabel tersimpan antar sel (seperti kernel Kaggle).
Komunikasi dengan daemon via JSON per baris di stdin/stdout.
stdout = kanal protokol; print() user ditangkap ke buffer terpisah.
"""
import ast
import base64
import io
import json
import os
import resource
import sys
import time
import traceback

OUT_CAP = 120_000
RES_CAP = 20_000
ERR_CAP = 30_000
IMG_MAX = 4
IMG_B64_CAP = 1_500_000
TOTAL_IMG_CAP = 3_000_000

MSG_INPUT = ("input() tidak bisa dipakai di Notebook ini — tulis nilainya "
             "langsung di dalam kode.")


class _NoStdin:
    """Ganti sys.stdin: input() ramah-error, kanal protokol tidak dibajak."""

    def readline(self, *a, **k):
        raise EOFError(MSG_INPUT)

    read = readline

    def readlines(self, *a, **k):
        raise EOFError(MSG_INPUT)

    def __iter__(self):
        return self

    def __next__(self):
        raise EOFError(MSG_INPUT)


def _cap(s, limit):
    if s is None:
        return None
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n… [dipotong, total {len(s):,} karakter]".replace(",", ".")


def _fmt_error(exc):
    """Traceback untuk user; frame internal kernel & parser dibuang."""
    if isinstance(exc, SyntaxError):
        loc = f"{exc.filename or '<sel>'}:{exc.lineno}"
        text = f"SyntaxError: {exc.msg} ({loc})"
        if exc.text:
            text += "\n    " + exc.text.rstrip()
            if exc.offset:
                text += "\n    " + " " * max(0, exc.offset - 1) + "^"
        return text
    chunks = traceback.format_exception(type(exc), exc, exc.__traceback__)
    keep = [c for c in chunks
            if "notebook_kernel.py" not in c and "/kernel.py" not in c
            and "ast.py" not in c]
    if not keep:  # exception murni internal kernel — tampilkan apa adanya
        keep = chunks[-1:]
    text = "".join(keep).strip()
    return text or f"{type(exc).__name__}: {exc}"


def _grab_figures():
    """Ambil gambar matplotlib yang dibuat sel ini (base64 PNG), lalu tutup."""
    plt = sys.modules.get("matplotlib.pyplot")
    if plt is None:
        return []
    images = []
    total = 0
    try:
        for num in plt.get_fignums()[:IMG_MAX]:
            fig = plt.figure(num)
            buf = io.BytesIO()
            try:
                fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
            except Exception:
                continue
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            if len(data) > IMG_B64_CAP or total + len(data) > TOTAL_IMG_CAP:
                continue
            total += len(data)
            images.append(data)
        plt.close("all")
    except Exception:
        pass
    return images


def _exec_cell(msg, ns, counter):
    code = str(msg.get("code") or "")
    counter["n"] += 1
    out_buf, err_buf = io.StringIO(), io.StringIO()
    old_out, old_err, old_in = sys.stdout, sys.stderr, sys.stdin
    sys.stdout, sys.stderr, sys.stdin = out_buf, err_buf, _NoStdin()
    result = None
    error = None
    error_type = ""
    t0 = time.time()
    try:
        tree = ast.parse(code, "<sel>", "exec")
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = tree.body.pop()
        if tree.body:
            exec(compile(tree, "<sel>", "exec"), ns)
        if last is not None:
            val = eval(compile(ast.Expression(last.value), "<sel>", "eval"), ns)
            if val is not None:
                result = repr(val)
    except SyntaxError as exc:
        error_type = "syntax"
        error = _fmt_error(exc)
    except BaseException as exc:  # noqa: BLE001 — kernel tidak boleh mati karena kode user
        error_type = "error"
        error = _fmt_error(exc)
    finally:
        sys.stdout, sys.stderr, sys.stdin = old_out, old_err, old_in

    images = _grab_figures()
    return {
        "type": "result",
        "cell": msg.get("cell"),
        "n": counter["n"],
        "stdout": _cap(out_buf.getvalue(), OUT_CAP),
        "stderr": _cap(err_buf.getvalue(), OUT_CAP),
        "result": _cap(result, RES_CAP),
        "error": _cap(error, ERR_CAP),
        "error_type": error_type,
        "images": images,
        "ms": int((time.time() - t0) * 1000),
    }


def main():
    try:
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass

    real_out = sys.stdout
    real_in = sys.stdin
    ns = {"__name__": "__main__"}
    counter = {"n": 0}

    def send(obj):
        real_out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        real_out.flush()

    send({"type": "ready", "python": sys.version.split()[0], "cwd": os.getcwd()})

    for raw in real_in:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue  # tulis-menulis non-protokol dari kode user → abaikan
        kind = msg.get("type")
        if kind == "exit":
            break
        if kind == "ping":
            send({"type": "pong"})
        elif kind == "exec":
            send(_exec_cell(msg, ns, counter))


if __name__ == "__main__":
    main()
