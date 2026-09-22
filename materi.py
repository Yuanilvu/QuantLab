"""materi.py — Katalog materi bootcamp Data Science (Pacmann + Rakamin).

Menyajikan materi lokal milik user sebagai halaman baca/putar di QuantLab —
video (.mp4) & slide (.pdf/.pptx) dibaca LANGSUNG dari folder sumber
(read-only, tanpa menyalin berkas):

  - ~/rakamin/Rakamin Data Science Bootcamp   (10 modul urut 01→10)
  - ~/pacmann_robot/Pacmann                   (4 kursus)

Dipakai app.py:
  - GET /data-science/materi            → katalog (render materi.html)
  - GET /data-science/materi/<slug>/<rel> → penyaji berkas (inline; Range utk video)
"""
from __future__ import annotations

import re
from pathlib import Path

from flask import abort, send_file

HOME = Path.home()

BOOTCAMP = [
    {
        "slug": "rakamin",
        "nama": "Rakamin — Data Science Bootcamp",
        "emoji": "📚",
        "deskripsi": "10 modul berurutan (01→10) + reading assignment: Business Understanding → SQL → Python → Data Processing → Statistics → Visualization → ML Prep → Supervised → Unsupervised → Deep Learning.",
        "root": HOME / "rakamin" / "Rakamin Data Science Bootcamp",
    },
    {
        "slug": "pacmann",
        "nama": "Pacmann — Bootcamp Data Science",
        "emoji": "🎓",
        "deskripsi": "4 kursus: Basic Python Programming, A/B Testing, Basic Machine Learning (video + slide), Advanced Machine Learning (slide).",
        "root": HOME / "pacmann_robot" / "Pacmann",
    },
]

EKST = {
    ".mp4": "🎬",
    ".pdf": "📄",
    ".pptx": "📊",
    ".ppt": "📊",
    ".ipynb": "📓",
    ".md": "📝",
    ".csv": "🧮",
    ".xlsx": "🧮",
    ".zip": "🗜️",
}

_SKIP = {"desktop.ini", ".ds_store", "thumbs.db", "__macosx"}
_MAKS_DALAM = 3


def _ukuran(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def _kunci(p: Path):
    """Urut ala manusia: '2' < '10', huruf case-insensitive."""
    potongan = re.split(r"(\d+)", p.name)
    return [(1, int(t)) if t.isdigit() else (0, t.lower()) for t in potongan if t]


def _node(folder: Path, root: Path, depth: int = 0) -> dict:
    """Baca satu folder → dict {nama, files, sub, n, b, sizeh} (maks _MAKS_DALAM level)."""
    berkas: list[dict] = []
    sub: list[dict] = []
    n_total, b_total = 0, 0
    try:
        isi = sorted(folder.iterdir(), key=_kunci)
    except OSError:
        isi = []
    for p in isi:
        if p.name.startswith(".") or p.name.lower() in _SKIP:
            continue
        if p.is_dir():
            if depth < _MAKS_DALAM:
                anak = _node(p, root, depth + 1)
                sub.append(anak)
                n_total += anak["n"]
                b_total += anak["b"]
        elif p.is_file():
            try:
                ukuran = p.stat().st_size
            except OSError:
                continue
            n_total += 1
            b_total += ukuran
            berkas.append({
                "nama": p.name,
                "emoji": EKST.get(p.suffix.lower(), "📄"),
                "ukuran": _ukuran(ukuran),
                "rel": p.relative_to(root).as_posix(),
            })
    return {"nama": folder.name, "emoji": "🗂️", "files": berkas, "sub": sub,
            "n": n_total, "b": b_total, "sizeh": _ukuran(b_total)}


def katalog() -> list[dict]:
    """Struktur siap render untuk halaman /data-science/materi."""
    hasil = []
    for b in BOOTCAMP:
        root = b["root"]
        if not root.is_dir():
            continue
        node = _node(root, root, 0)
        hasil.append({
            "slug": b["slug"], "nama": b["nama"], "emoji": b["emoji"],
            "deskripsi": b["deskripsi"],
            "grup": node["sub"], "files": node["files"],
            "n": node["n"], "size": node["sizeh"], "n_grup": len(node["sub"]),
        })
    return hasil


def ringkas() -> dict:
    """Jumlah & ukuran total semua materi (untuk kartu di hub DS)."""
    n, b = 0, 0
    for meta in BOOTCAMP:
        root = meta["root"]
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and not p.name.startswith(".") and p.name.lower() not in _SKIP:
                n += 1
                try:
                    b += p.stat().st_size
                except OSError:
                    pass
    return {"n": n, "size": _ukuran(b)}


def ambil(slug: str, rel: str):
    """Kirim satu berkas materi (inline). Tolak path di luar folder materi."""
    meta = next((b for b in BOOTCAMP if b["slug"] == slug), None)
    if not meta:
        abort(404)
    root = meta["root"].resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        abort(404)
    if not p.is_file():
        abort(404)
    return send_file(p, conditional=True, download_name=p.name)
