"""QuantLab — Loader kurikulum skenario dari file YAML di curriculum/levels/.

CATATAN PENTING: kurikulum di-cache per proses (lihat _load_all). Setelah
mengubah file YAML, restart service: systemctl --user restart quantlab
"""
import os
import re
import yaml

CURRICULUM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "curriculum", "levels")

_babs = None
_by_scenario = None
_by_soal = None

TRACKS = [
    ("math", "Fondasi Matematika", "🧮", "Angka, persen, statistik & probabilitas — bahasa dasar semua keputusan."),
    ("python", "Python dari Nol", "🐍", "Koding pertama: variabel sampai fungsi, lewat contoh pasar."),
    ("finance", "Finance Dasar", "💰", "Uang, bunga, saham, dan risiko — cara kerja pasar modal."),
    ("quant", "Quant Integrasi", "📈", "Gabungkan semuanya: skenario trading, backtest, dan bot."),
    ("advanced", "Advanced: Data & Bot", "🚀", "Data, debugging, dan proyek mini — jembatan ke bot sungguhan."),
    ("libs", "Python Libraries", "📦", "NumPy, Pandas, Matplotlib — senjata standar analisis quant."),
]

TRACK_ORDER = [t[0] for t in TRACKS]


def _load_all():
    global _babs, _by_scenario, _by_soal
    if _babs is not None:
        return
    babs = []
    by_scenario = {}
    by_soal = {}
    for fn in sorted(os.listdir(CURRICULUM_DIR)):
        if not fn.endswith(".yaml"):
            continue
        with open(os.path.join(CURRICULUM_DIR, fn), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "bab" in data:
            if not data.get("track"):
                data["track"] = "quant"  # bab lama default quant
            babs.append(data)
            for s in (data.get("skenario") or []):
                by_scenario[s["id"]] = {"bab": data, "data": s}
            for q in (data.get("soal") or []):
                by_soal[q["id"]] = {"bab": data, "data": q}
    babs.sort(key=lambda b: (TRACK_ORDER.index(b.get("track", "quant")), b.get("bab", 999)))
    _babs, _by_scenario, _by_soal = babs, by_scenario, by_soal


def get_tracks():
    _load_all()
    out = []
    for code, name, emoji, desc in TRACKS:
        babs = [b for b in _babs if b.get("track") == code]
        out.append({"code": code, "name": name, "emoji": emoji, "desc": desc, "babs": babs})
    return out


def track_of(bab):
    return bab.get("track", "quant")


def get_babs():
    _load_all()
    return _babs


def get_bab(n):
    _load_all()
    for b in _babs:
        if b["bab"] == n:
            return b
    return None


def get_scenario(sid):
    _load_all()
    entry = _by_scenario.get(sid)
    return entry if entry else None


def get_lesson_by_id(lid):
    _load_all()
    for b in _babs:
        for l in (b.get("pelajaran") or []):
            if l.get("id") == lid:
                return {"bab": b, "data": l}
    return None


def get_soal(qid):
    _load_all()
    entry = _by_soal.get(qid)
    return entry if entry else None


def get_soals_by_bab(bab_num):
    _load_all()
    bab = get_bab(bab_num)
    return bab.get("soal") or [] if bab else []


def get_scenarios_by_bab(bab_num):
    _load_all()
    bab = get_bab(bab_num)
    return bab.get("skenario") or [] if bab else []


def total_scenarios():
    _load_all()
    return sum(len(b.get("skenario") or []) for b in _babs)


def xp_for_scenario(s):
    return int(s.get("xp", 20))


# ---------- Chart Drill (latihan baca grafik) ----------

CHARTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "curriculum", "charts.yaml")
CHART_XP = {"mudah": 20, "sedang": 35, "sulit": 50}

CHART_MODULES = [
    ("dasar", "🕯️ Baca Candle & Tren",
     "Anatomi candle, pola penting (engulfing, doji, hammer), dan struktur tren."),
    ("level", "📐 Level & Struktur",
     "Support, resistance, dan breakout — level tempat harga berbalik atau menembus."),
    ("indikator", "📊 Indikator & Risiko",
     "RSI, moving average, dan drawdown — alat ukur momentum dan risiko."),
    ("praktik", "🎯 Praktik Langsung",
     "Klik grafiknya: tandai level, pasang stop loss, tentukan entry dan take profit."),
]

_charts = None


def _load_charts():
    global _charts
    if _charts is not None:
        return
    with open(CHARTS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _charts = data.get("drills") or []


def get_charts():
    _load_charts()
    return _charts or []


def get_chart(cid):
    _load_charts()
    for d in (_charts or []):
        if d.get("id") == cid:
            return d
    return None


def xp_for_chart(d):
    return int(CHART_XP.get((d or {}).get("tingkat"), 20))


def charts_by_modul(drills=None):
    """Kelompokkan drill per modul (urutan tetap; dalam modul: tingkat lalu id)."""
    isi = drills if drills is not None else get_charts()
    urut_tingkat = {"mudah": 0, "sedang": 1, "sulit": 2}
    out = []
    for code, nama, desc in CHART_MODULES:
        anggota = [d for d in isi if d.get("modul") == code]
        anggota.sort(key=lambda d: (urut_tingkat.get(d.get("tingkat"), 9), d["id"]))
        out.append({"code": code, "nama": nama, "desc": desc, "drills": anggota})
    return out


def stats():
    _load_all()
    return {
        "babs": len(_babs),
        "skenario": sum(len(b.get("skenario") or []) for b in _babs),
        "pelajaran": sum(len(b.get("pelajaran") or []) for b in _babs),
        "soal": sum(len(b.get("soal") or []) for b in _babs),
    }


def render_markdown(md: str) -> str:
    """Markdown mini: heading, bold, inline code, list, paragraf, fenced code."""
    md = (md or "").strip()
    lines = md.split("\n")
    out = []
    in_list = False
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_list:
                out.append("</ul>")
                in_list = False
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre class='block-code'><code>")
                in_code = True
            continue
        if in_code:
            out.append(_esc(line))
            continue
        if not stripped:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h4>{_inline(stripped[4:])}</h4>")
        elif stripped.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(stripped[2:])}</li>")
        elif stripped.startswith("1. "):
            if not in_list:
                out.append("<ol>")
                in_list = True
            out.append(f"<li>{_inline(stripped[3:])}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_inline(stripped)}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    s = _esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s
