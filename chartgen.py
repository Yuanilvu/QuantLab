"""chartgen.py — generator chart harga SVG (line & candlestick) + indikator.

Dipakai halaman Lab Teknikal (`/chart`): memuat deret harga beku dari
data/chart/*.csv (format `date,close` ATAU `date,open,high,low,close[,volume]`),
menghitung SMA/RSI, dan menggambar SVG inline (tanpa JS/library luar).

Fitur:
- chart garis (harga + MA + panel RSI opsional + marker titik)
- chart candlestick + panel volume + MA (untuk latihan baca candle)
- atribut `data-*` pada <svg> agar halaman bisa memetakan klik → harga
  (dipakai drill "praktik langsung")

Semua fungsi deterministik — data BEKU supaya kunci jawaban tidak pernah basi.
Layout canvas default 640-an px supaya label tetap terbaca saat menyempit di HP.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CHART_DIR = os.path.join(HERE, "data", "chart")

MA_COLORS = ["#a78bfa", "#f472b6", "#4ade80"]
GRID = "#1e293b"
TXT_DIM = "#64748b"
WARNA_NAIK = "#34d399"
WARNA_TURUN = "#f87171"


# ── Data ────────────────────────────────────────────────────────────────────

def load_rows(path: str) -> list:
    """Baca CSV harga → list dict {date, open?, high?, low?, close, volume?}."""
    baris = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            r = {"date": row["date"].strip(), "close": float(row["close"])}
            for k in ("open", "high", "low"):
                if row.get(k) not in (None, ""):
                    r[k] = float(row[k])
            if row.get("volume") not in (None, ""):
                r["volume"] = float(row["volume"])
            baris.append(r)
    return baris


def load_csv(path: str) -> tuple[list, list]:
    """Baca CSV → (dates, closes). Mendukung \\r\\n."""
    rows = load_rows(path)
    return [r["date"] for r in rows], [r["close"] for r in rows]


def load_frozen(chart_id: str) -> tuple[list, list]:
    """Deret (dates, closes) utk 1 drill: data/chart/<id>.csv."""
    return load_csv(os.path.join(CHART_DIR, f"{chart_id}.csv"))


def load_frozen_rows(chart_id: str) -> list:
    """Deret penuh (dict) utk 1 drill — candle/volume butuh open/high/low."""
    return load_rows(os.path.join(CHART_DIR, f"{chart_id}.csv"))


def punya_ohlc(rows: list) -> bool:
    return bool(rows) and all(("open" in r and "high" in r and "low" in r) for r in rows)


# ── Indikator ───────────────────────────────────────────────────────────────

def sma(values: list, n: int) -> list:
    """SMA; index < n-1 -> None."""
    out: list = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def rsi(closes: list, period: int = 14) -> list:
    """RSI sederhana (rata-rata gain/loss dibagi period); index < period -> None."""
    out: list = [None] * len(closes)
    for i in range(period, len(closes)):
        window = closes[i - period + 1:i + 1]
        naik = turun = 0.0
        for a, b in zip(window, window[1:]):
            d = b - a
            if d > 0:
                naik += d
            else:
                turun += -d
        avg_naik = naik / period
        avg_turun = turun / period
        if avg_turun == 0:
            out[i] = 100.0
        else:
            rs = avg_naik / avg_turun
            out[i] = 100 - 100 / (1 + rs)
    return out


def _label_harga(v: float, besar: bool) -> str:
    """Label sumbu harga — disingkat ke k utk nilai besar (BTC)."""
    if besar:
        return f"{v / 1000:,.1f}k"
    return f"{v:,.0f}"


# ── Kerangka bersama (grid, label, legenda, garis, RSI, marker) ─────────────

def _data_attrs(lo, hi, y_atas, y_bawah, x_kiri, x_kanan, vb_h, w, interaktif):
    """Atributagar JS bisa memetakan klik (x,y) → harga."""
    if not interaktif:
        return ""
    return (f' data-interaktif="1" data-harga-min="{lo:.4f}" data-harga-max="{hi:.4f}"'
            f' data-y-atas="{y_atas:.2f}" data-y-bawah="{y_bawah:.2f}"'
            f' data-x-kiri="{x_kiri:.1f}" data-x-kanan="{x_kanan:.1f}"'
            f' data-vb-h="{vb_h:.1f}" data-vb-w="{w:.1f}"')


def _grid_harga(parts, left, right, top, bawah, lo, hi, besar):
    for k in range(5):
        gy = top + (bawah - top) * k / 4
        val = hi - (hi - lo) * k / 4
        parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8}" y="{gy + 4.5:.1f}" text-anchor="end" '
                     f'font-size="13" fill="{TXT_DIM}">{_label_harga(val, besar)}</text>')


def _legenda_ma(parts, closes, top, left, ma):
    legenda = []
    for k, n in enumerate(ma or ()):
        warna = MA_COLORS[k % len(MA_COLORS)]
        legenda.append((f"MA{n}", warna, sma(closes, n)))
    lx = left + 2
    for label, warna, _ in legenda:
        parts.append(f'<line x1="{lx}" y1="{top + 10}" x2="{lx + 20}" y2="{top + 10}" '
                     f'stroke="{warna}" stroke-width="2.4"/>')
        parts.append(f'<text x="{lx + 26}" y="{top + 14.5}" font-size="13" '
                     f'fill="#94a3b8">{label}</text>')
        lx += 70
    return legenda


def _panel_rsi(parts, closes, left, right, x, rsi_judul_y, rsi_atas, rsi_bawah):
    r = rsi(closes, 14)
    parts.append(f'<text x="{left}" y="{rsi_judul_y:.1f}" font-size="13" '
                 f'fill="#94a3b8">RSI-14 (kuning) · batas 70 / 30</text>')
    parts.append(f'<rect x="{left}" y="{rsi_atas}" width="{right - left}" '
                 f'height="{rsi_bawah - rsi_atas}" rx="8" fill="#0b1220"/>')
    for lvl, col in ((70, "#f87171"), (30, "#34d399")):
        gy = rsi_atas + (rsi_bawah - rsi_atas) * (1 - lvl / 100)
        parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                     f'stroke="{col}" stroke-width="1.2" stroke-dasharray="6 5" opacity="0.8"/>')
        parts.append(f'<text x="{right - 6}" y="{gy - 3:.1f}" text-anchor="end" '
                     f'font-size="12" fill="#7d8fa1">{lvl}</text>')
    seg = []
    for i, v in enumerate(r):
        if v is None:
            continue
        gy = rsi_atas + (rsi_bawah - rsi_atas) * (1 - v / 100)
        seg.append(f"{x(i):.1f},{gy:.1f}")
    if seg:
        parts.append(f'<polyline points="{" ".join(seg)}" fill="none" '
                     f'stroke="#fbbf24" stroke-width="2"/>')


def _markers(parts, rows, markers, x, y):
    for m in (markers or []):
        idx = m.get("idx", -1)
        idx = idx if idx >= 0 else len(rows) + idx
        if not (0 <= idx < len(rows)):
            continue
        r = rows[idx]
        px, py = x(idx), y(r.get("high", r["close"]))
        pos = m.get("pos", "atas")
        py = py - 14 if pos == "atas" else y(r.get("low", r["close"])) + 18
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="#f59e0b"/>')
        parts.append(f'<text x="{px:.1f}" y="{py - 7:.1f}" text-anchor="middle" '
                     f'font-size="13" font-weight="700" fill="#f59e0b">{m.get("label", "")}</text>')


def _tanggal(parts, rows, harga_bawah, y_label, left, right, x):
    for idx, anchor in ((0, "start"), (len(rows) // 2, "middle"), (len(rows) - 1, "end")):
        tx = min(max(x(idx), left), right)
        parts.append(f'<text x="{tx:.1f}" y="{y_label:.1f}" text-anchor="{anchor}" '
                     f'font-size="13" fill="{TXT_DIM}">{rows[idx]["date"]}</text>')


# ── Chart garis ─────────────────────────────────────────────────────────────

def svg_price_chart(dates, closes, *, width=640, height=340, ma=(20, 50),
                    rsi_panel=False, garis=None, pad=46, markers=None,
                    interaktif=False) -> str:
    """Chart harga garis (SVG inline)."""
    if not closes:
        return "<svg></svg>"
    rows = [{"date": d, "close": c} for d, c in zip(dates, closes)]
    return svg_candle_chart(rows, tipe="line", width=width, height=height, ma=ma,
                            rsi_panel=rsi_panel, garis=garis, pad=pad,
                            markers=markers, volume=False, interaktif=interaktif)


# ── Chart candlestick ───────────────────────────────────────────────────────

def svg_candle_chart(rows, *, tipe="candle", width=640, height=340, ma=(20, 50),
                     rsi_panel=False, garis=None, pad=46, markers=None,
                     volume=True, interaktif=False, garis_user=None) -> str:
    """Chart candlestick + panel volume opsional (SVG inline).

    rows: list dict {date, close [, open, high, low, volume]}.
    tipe="line" → gambar garis close saja (tanpa candle/volume).
    garis_user: level jawaban user (drill praktik) — garis cyan dashed.
    """
    if not rows:
        return "<svg></svg>"
    w = width
    left, right = pad, w - 14
    top = 18
    harga_bawah = height - 36
    ada_vol = bool(volume) and any("volume" in r for r in rows) and tipe == "candle"
    if ada_vol:
        vol_atas = harga_bawah + 26
        vol_bawah = vol_atas + 56
        rsi_judul_y = vol_bawah + 28
        rsi_atas = vol_bawah + 34
        rsi_bawah = rsi_atas + 80
    else:
        vol_atas = vol_bawah = 0
        rsi_judul_y = height + 18
        rsi_atas = height + 26
        rsi_bawah = rsi_atas + 86
    y_label_tanggal = (rsi_bawah if rsi_panel else (vol_bawah if ada_vol else harga_bawah)) + 22
    total_h = y_label_tanggal + 10

    closes = [r["close"] for r in rows]
    lo, hi = min((r.get("low", r["close"]) for r in rows)), max((r.get("high", r["close"]) for r in rows))
    span = (hi - lo) or 1
    lo -= span * 0.06
    hi += span * 0.06
    besar = hi >= 100000

    def x(i):
        return left + (right - left) * i / max(1, len(rows) - 1)

    def y(v):
        return top + (harga_bawah - top) * (1 - (v - lo) / (hi - lo))

    parts = [
        f'<svg viewBox="0 0 {w} {total_h}" role="img" '
        f'aria-label="Grafik harga {rows[0]["date"]} sampai {rows[-1]["date"]}" '
        f'style="width:100%;height:auto;display:block"'
        + _data_attrs(lo, hi, top, harga_bawah, left, right, total_h, w, interaktif) + '>',
        '<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#22d3ee" stop-opacity="0.35"/>'
        '<stop offset="1" stop-color="#22d3ee" stop-opacity="0.02"/>'
        '</linearGradient></defs>',
        f'<rect x="0" y="0" width="{w}" height="{total_h}" rx="14" fill="#0f172a"/>',
    ]

    _grid_harga(parts, left, right, top, harga_bawah, lo, hi, besar)
    for g in (garis or []):
        if lo <= g <= hi:
            gy = y(g)
            parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                         f'stroke="#f59e0b" stroke-width="1.6" stroke-dasharray="6 4"/>')
    for g in ([garis_user] if garis_user else []):
        if lo <= g <= hi:
            gy = y(g)
            parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                         f'stroke="#22d3ee" stroke-width="1.6" stroke-dasharray="6 4"/>')

    n = len(rows)
    lebar = max(2.2, (right - left) / max(1, n) * 0.68)

    if tipe == "line":
        pts = " ".join(f"{x(i):.1f},{y(r['close']):.1f}" for i, r in enumerate(rows))
        parts.append(f'<polygon points="{x(0):.1f},{harga_bawah:.1f} {pts} '
                     f'{x(n - 1):.1f},{harga_bawah:.1f}" fill="url(#cg)"/>')
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#22d3ee" '
                     f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
    else:
        for i, r in enumerate(rows):
            o = r["open"]; c = r["close"]
            h = r["high"]; l = r["low"]
            warna = WARNA_NAIK if c >= o else WARNA_TURUN
            cx = x(i)
            parts.append(f'<line x1="{cx:.1f}" y1="{y(h):.1f}" x2="{cx:.1f}" y2="{y(l):.1f}" '
                         f'stroke="{warna}" stroke-width="1.1"/>')
            yo, yc = y(o), y(c)
            if abs(yo - yc) < 1.2:
                yo = yc - 1.2
            parts.append(f'<rect x="{cx - lebar / 2:.1f}" y="{min(yo, yc):.1f}" '
                         f'width="{lebar:.1f}" height="{max(1.2, abs(yc - yo)):.1f}" '
                         f'fill="{warna}" rx="0.8"/>')

    legenda = _legenda_ma(parts, closes, top, left, ma)
    for label, warna, seri in legenda:
        seg = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(seri) if v is not None)
        if seg:
            parts.append(f'<polyline points="{seg}" fill="none" stroke="{warna}" '
                         f'stroke-width="1.9" opacity="0.95"/>')

    # panel volume
    if ada_vol:
        max_vol = max(r.get("volume", 0) for r in rows) or 1
        parts.append(f'<text x="{left}" y="{vol_atas - 6:.1f}" font-size="13" '
                     f'fill="#94a3b8">Volume</text>')
        parts.append(f'<rect x="{left}" y="{vol_atas}" width="{right - left}" '
                     f'height="{vol_bawah - vol_atas}" rx="8" fill="#0b1220"/>')
        for i, r in enumerate(rows):
            v = r.get("volume", 0)
            if not v:
                continue
            vb = (v / max_vol) * (vol_bawah - vol_atas - 6)
            warna = WARNA_NAIK if r["close"] >= r.get("open", r["close"]) else WARNA_TURUN
            parts.append(f'<rect x="{x(i) - lebar / 2:.1f}" y="{vol_bawah - vb:.1f}" '
                         f'width="{lebar:.1f}" height="{vb:.1f}" fill="{warna}" '
                         f'opacity="0.55" rx="0.8"/>')

    if rsi_panel:
        _panel_rsi(parts, closes, left, right, x, rsi_judul_y, rsi_atas, rsi_bawah)

    _markers(parts, rows, markers, x, y)
    _tanggal(parts, rows, harga_bawah, y_label_tanggal, left, right, x)
    parts.append("</svg>")
    return "".join(parts)


# ── Dispatcher drill ────────────────────────────────────────────────────────

def render_drill(drill, *, interaktif=False, garis_extra=None, garis_user=None) -> str:
    """Gambar SVG utk 1 drill (pilih line/candle + opsi dari YAML drill)."""
    cid = drill["id"]
    rows = load_frozen_rows(cid)
    garis = list(drill.get("garis") or []) + list(garis_extra or [])
    jenis = drill.get("jenis", "line")
    return svg_candle_chart(
        rows,
        tipe="line" if jenis == "line" else "candle",
        ma=tuple(drill.get("ma") or ()),
        rsi_panel=bool(drill.get("rsi_panel")),
        garis=garis,
        garis_user=garis_user,
        markers=drill.get("markers") or [],
        volume=bool(drill.get("volume", False)),
        interaktif=interaktif,
    )
