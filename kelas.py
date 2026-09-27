"""kelas.py — Rangkuman kelas bootcamp (Rakamin & Pacmann) untuk dibaca di QuantLab.

Berkas rangkuman = markdown di `content/kelas/**` (TIDAK di-commit — turunan materi
kursus berbayar; sumber asli tetap read-only di ~/rakamin & ~/pacmann_robot).
Setiap berkas punya frontmatter YAML:

    judul: "02 — SQL: dari DBMS sampai Query Kompleks"
    grup: rakamin            # rakamin | pacmann
    kursus: "Rakamin Data Science Bootcamp"
    emoji: 🗄️
    urut: 2
    menit: 40
    singkat: "satu kalimat isi modul"
    sumber:                  # path relatif ke root grup (utk link sumber asli)
      - "02 - SQL/1 - DBMS Fundamentals & Basic Operations.pdf"
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

try:
    import markdown as _py_md
except ImportError:  # fallback: renderer mini bawaan QuantLab
    _py_md = None

ROOT = Path(__file__).resolve().parent / "content" / "kelas"

GRUP = {
    "rakamin": {
        "nama": "Rakamin — Data Science Bootcamp",
        "emoji": "📚",
        "track": "rakamin",
        "desc": "10 modul berurutan: Business Understanding → SQL → Python → "
                "Data Processing → Statistics → Data Visualization → ML Preparation → "
                "Supervised Learning → Unsupervised Learning → Deep Learning.",
    },
    "pacmann": {
        "nama": "Pacmann — Data Science",
        "emoji": "🎓",
        "track": "pacmann",
        "desc": "Kursus: Basic Python Programming, Basic Machine Learning, "
                "Advanced Machine Learning, A/B Testing (Excel), dan Market Research.",
    },
}

# Urutan tampil kursus di dalam grup (yang tidak terdaftar → paling belakang).
URUTAN_KURSUS = [
    "Rakamin Data Science Bootcamp",
    "Basic Python Programming",
    "Basic Machine Learning Algorithm",
    "Advanced Machine Learning Algorithm",
    "A/B Testing in Ecommerce using Excel",
    "Market Research",
]


def _baca(path: Path):
    """Parse frontmatter + isi → (meta, isi) atau None."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not m:
        return None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    return meta, m.group(2)


def ke_html(md_text: str) -> str:
    """Markdown → HTML (tabel/link didukung). Fallback: renderer mini QuantLab."""
    if _py_md is None:
        import curriculum
        return curriculum.render_markdown(md_text)
    html = _py_md.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    # Blok kode pakai gaya QuantLab (pre.block-code — sama dengan halaman pelajaran)
    return html.replace("<pre><code", "<pre class='block-code'><code")


def _items(grup: str) -> list[dict]:
    """Semua item rangkuman satu grup (urut kursus+urut)."""
    base = ROOT / grup
    out = []
    if not base.is_dir():
        return out
    for f in sorted(base.rglob("*.md")):
        if f.name.startswith("_"):
            continue
        data = _baca(f)
        if not data:
            continue
        meta, _ = data
        out.append({
            "sub": f.relative_to(ROOT).with_suffix("").as_posix(),
            "judul": str(meta.get("judul") or f.stem),
            "kursus": str(meta.get("kursus") or "Umum"),
            "emoji": str(meta.get("emoji") or "📄"),
            "urut": int(meta.get("urut") or 0),
            "menit": int(meta.get("menit") or 0),
            "singkat": str(meta.get("singkat") or ""),
        })
    return out


def katalog() -> list[dict]:
    """Struktur siap-render utk halaman indeks /data-science/kelas."""
    hasil = []
    for grup, gmeta in GRUP.items():
        items = _items(grup)
        per_kursus: dict[str, list] = {}
        for it in items:
            per_kursus.setdefault(it["kursus"], []).append(it)
        daftar = []
        for nm in sorted(per_kursus, key=lambda k: (
                URUTAN_KURSUS.index(k) if k in URUTAN_KURSUS else 99, k)):
            lsn = sorted(per_kursus[nm], key=lambda x: (x["urut"], x["judul"]))
            daftar.append({"nama": nm, "lessons": lsn, "n": len(lsn),
                           "emoji": lsn[0]["emoji"] if lsn else "📄"})
        if not daftar:
            continue
        hasil.append({**gmeta, "grup": grup, "kursus": daftar, "n": len(items)})
    return hasil


def ringkas() -> dict:
    """Jumlah total rangkuman siap (utk kartu di hub Data Science)."""
    n = 0
    for grup in GRUP:
        n += len(_items(grup))
    return {"n": n, "grup": len(GRUP)}


def muat(sub: str):
    """Muat 1 rangkuman → dict lengkap + navigasi, atau None kalau tak ada."""
    sub = (sub or "").strip().strip("/")
    if not sub or ".." in sub or "\\" in sub:
        return None
    p = (ROOT / (sub + ".md")).resolve()
    root_r = ROOT.resolve()
    if root_r not in p.parents or not p.is_file():
        return None
    data = _baca(p)
    if not data:
        return None
    meta, isi = data
    grup = str(meta.get("grup") or "")
    kursus = str(meta.get("kursus") or "Umum")

    # prev/next dalam kursus yang sama
    semua = [it for it in _items(grup) if it["kursus"] == kursus]
    semua.sort(key=lambda x: (x["urut"], x["judul"]))
    prev = nxt = None
    for i, it in enumerate(semua):
        if it["sub"] == sub:
            prev = semua[i - 1] if i > 0 else None
            nxt = semua[i + 1] if i + 1 < len(semua) else None
            break

    gm = GRUP.get(grup, {})
    return {
        "sub": sub,
        "judul": str(meta.get("judul") or p.stem),
        "grup": grup,
        "grup_nama": gm.get("nama", grup),
        "grup_emoji": gm.get("emoji", "📄"),
        "track": gm.get("track", grup),
        "kursus": kursus,
        "emoji": str(meta.get("emoji") or "📄"),
        "menit": int(meta.get("menit") or 0),
        "sumber": [str(s) for s in (meta.get("sumber") or [])],
        "isi_md": isi,
        "isi_html": ke_html(isi),
        "prev": prev,
        "next": nxt,
        "pos": next((i + 1 for i, it in enumerate(semua) if it["sub"] == sub), 0),
        "n_kursus": len(semua),
    }
