"""chartgen.py — generator chart harga SVG + indikator sederhana (pure Python).

Dipakai halaman Chart Drill: memuat deret harga beku dari data/chart/*.csv,
menghitung SMA/RSI, dan menggambar chart SVG inline (tanpa JS/library luar).

Semua fungsi deterministik — data beku (frozen) supaya kunci jawaban
latihan tidak pernah basi.

Catatan layout: canvas default 640×340 (rasio ~1.9) supaya label tetap
terbaca saat chart tampil menyempit di HP; panel RSI ikut masuk viewBox.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CHART_DIR = os.path.join(HERE, "data", "chart")


def load_csv(path: str) -> tuple[list, list]:
    """Baca CSV (date,close) -> (dates, closes). Mendukung \\r\\n."""
    dates, closes = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            dates.append(row["date"].strip())
            closes.append(float(row["close"]))
    return dates, closes


def load_frozen(chart_id: str) -> tuple[list, list]:
    """Deret harga beku utk 1 drill: data/chart/<id>.csv."""
    return load_csv(os.path.join(CHART_DIR, f"{chart_id}.csv"))


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


def svg_price_chart(dates, closes, *, width=640, height=340, ma=(20, 50),
                    rsi_panel=False, garis=None, pad=46) -> str:
    """Chart harga SVG inline (siap tempel di HTML).

    - garis: list level harga horizontal (dashed) — penanda level dari konteks soal.
    - ma: tuple periode SMA yang digambar (label di legenda).
    - rsi_panel: panel RSI-14 di bawah chart harga (ikut viewBox, tidak terpotong).
    """
    if not closes:
        return "<svg></svg>"
    w = width
    left, right = pad, w - 14
    top = 18
    harga_bawah = height - 36
    rsi_judul_y = height + 18
    rsi_atas = height + 26
    rsi_bawah = rsi_atas + 86
    total_h = (rsi_bawah + 16) if rsi_panel else height
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1
    lo -= span * 0.06
    hi += span * 0.06
    besar = hi >= 100000

    def x(i):
        return left + (right - left) * i / max(1, len(closes) - 1)

    def y(v):
        return top + (harga_bawah - top) * (1 - (v - lo) / (hi - lo))

    parts = [
        f'<svg viewBox="0 0 {w} {total_h}" role="img" '
        f'aria-label="Grafik harga {dates[0]} sampai {dates[-1]}" '
        f'style="width:100%;height:auto;display:block">',
        '<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#22d3ee" stop-opacity="0.35"/>'
        '<stop offset="1" stop-color="#22d3ee" stop-opacity="0.02"/>'
        '</linearGradient></defs>',
        f'<rect x="0" y="0" width="{w}" height="{total_h}" rx="14" fill="#0f172a"/>',
    ]

    # grid horizontal + label harga
    for k in range(5):
        gy = top + (harga_bawah - top) * k / 4
        val = hi - (hi - lo) * k / 4
        parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                     f'stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8}" y="{gy + 4.5:.1f}" text-anchor="end" '
                     f'font-size="13" fill="#64748b">{_label_harga(val, besar)}</text>')

    # garis level (dashed)
    for g in (garis or []):
        if lo <= g <= hi:
            gy = y(g)
            parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" '
                         f'stroke="#f59e0b" stroke-width="1.6" stroke-dasharray="6 4"/>')

    # area + garis harga
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(closes))
    parts.append(f'<polygon points="{x(0):.1f},{harga_bawah:.1f} {pts} '
                 f'{x(len(closes) - 1):.1f},{harga_bawah:.1f}" fill="url(#cg)"/>')
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#22d3ee" '
                 f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')

    # MA overlays + legenda
    ma_colors = ["#a78bfa", "#f472b6", "#4ade80"]
    legend = []
    for k, n in enumerate(ma or ()):
        s = sma(closes, n)
        seg = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(s) if v is not None)
        if seg:
            color = ma_colors[k % len(ma_colors)]
            parts.append(f'<polyline points="{seg}" fill="none" stroke="{color}" '
                         f'stroke-width="1.9" opacity="0.95"/>')
            legend.append((f"MA{n}", color))
    lx = left + 2
    for label, color in legend:
        parts.append(f'<line x1="{lx}" y1="{top + 10}" x2="{lx + 20}" y2="{top + 10}" '
                     f'stroke="{color}" stroke-width="2.4"/>')
        parts.append(f'<text x="{lx + 26}" y="{top + 14.5}" font-size="13" '
                     f'fill="#94a3b8">{label}</text>')
        lx += 70

    # label tanggal (kiri / tengah / kanan)
    for idx, anchor in ((0, "start"), (len(closes) // 2, "middle"), (len(closes) - 1, "end")):
        tx = min(max(x(idx), left), right)
        parts.append(f'<text x="{tx:.1f}" y="{harga_bawah + 20:.1f}" text-anchor="{anchor}" '
                     f'font-size="13" fill="#64748b">{dates[idx]}</text>')

    # panel RSI (opsional) — di dalam viewBox
    if rsi_panel:
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

    parts.append("</svg>")
    return "".join(parts)
