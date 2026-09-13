"""chartfacts.py — mesin fakta Lab Teknikal (Chart Drill).

Fakta dihitung dari baris data BEKU (chartgen.load_frozen_rows) dan dipakai
dua arah:
- authoring: menghitung angka untuk ditulis ke `penjelasan` + blok `fakta:` YAML;
- verifikasi: scripts/verify_charts.py menghitung ULANG dan membandingkan —
  kunci jawaban tidak pernah basi.

Cara pakai:
    from chartfacts import hitung_fakta
    hitung_fakta(rows, "low_n", {"n": 20})
"""
import chartgen


def _idx(rows, idx):
    return idx if idx >= 0 else len(rows) + idx


def _low(r):
    return r.get("low", r["close"])


def _high(r):
    return r.get("high", r["close"])


# ── fakta dasar ─────────────────────────────────────────────────────────────

def f_n(rows, p=None):
    return len(rows)


def f_terakhir(rows, p=None):
    return round(rows[-1]["close"], 2)


def f_ma20(rows, p=None):
    s = chartgen.sma([r["close"] for r in rows], 20)
    return round(s[-1], 2) if s and s[-1] is not None else None


def f_ma50(rows, p=None):
    s = chartgen.sma([r["close"] for r in rows], 50)
    return round(s[-1], 2) if s and s[-1] is not None else None


def f_rsi(rows, p=None):
    r = chartgen.rsi([r["close"] for r in rows], 14)
    return round(r[-1], 2) if r and r[-1] is not None else None


def f_dd(rows, p=None):
    puncak = 0.0
    dd = 0.0
    for r in rows:
        puncak = max(puncak, r["close"])
        dd = max(dd, (puncak - r["close"]) / puncak * 100)
    return round(dd, 2)


def f_imax(rows, p=None):
    """Indeks close tertinggi."""
    return max(range(len(rows)), key=lambda i: rows[i]["close"])


def f_imax_high(rows, p=None):
    """Indeks harga (high) tertinggi."""
    return max(range(len(rows)), key=lambda i: _high(rows[i]))


def f_cross_up_30(rows, p=None):
    return _hitung_cross(rows, atas=True)


def f_cross_dn_30(rows, p=None):
    return _hitung_cross(rows, atas=False)


def _hitung_cross(rows, atas):
    closes = [r["close"] for r in rows]
    m20, m50 = chartgen.sma(closes, 20), chartgen.sma(closes, 50)
    jml = 0
    for i in range(max(1, len(closes) - 30), len(closes)):
        if None in (m20[i], m20[i - 1], m50[i], m50[i - 1]):
            continue
        if atas and m20[i - 1] <= m50[i - 1] and m20[i] > m50[i]:
            jml += 1
        if not atas and m20[i - 1] >= m50[i - 1] and m20[i] < m50[i]:
            jml += 1
    return jml


# ── level / sentuhan ────────────────────────────────────────────────────────

def f_low_n(rows, p=None):
    n = (p or {}).get("n", 20)
    return round(min(_low(r) for r in rows[-n:]), 2)


def f_high_n(rows, p=None):
    n = (p or {}).get("n", 30)
    return round(max(_high(r) for r in rows[-n:]), 2)


def f_sentuh(rows, p=None):
    """Berapa bar yang 'menyentuh' level: rentang bar melewati level ±tol."""
    if not p or "level" not in p:
        raise ValueError("fakta `sentuh` butuh param level")
    level = p["level"]
    tol = p.get("tol_pct", 1.0)
    jml = 0
    for r in rows:
        if _low(r) <= level * (1 + tol / 100) and _high(r) >= level * (1 - tol / 100):
            jml += 1
    return jml


# ── candle & pola ───────────────────────────────────────────────────────────

def f_candle_arah(rows, p=None):
    idx = _idx(rows, (p or {}).get("idx", -1))
    r = rows[idx]
    return "hijau" if r["close"] >= r.get("open", r["close"]) else "merah"


def f_merah_beruntun(rows, p=None):
    return _beruntun(rows, merah=True)


def f_hijau_beruntun(rows, p=None):
    return _beruntun(rows, merah=False)


def _beruntun(rows, merah):
    terpanjang = jln = 0
    for r in rows:
        merah_bar = r["close"] < r.get("open", r["close"])
        if merah_bar == merah and (merah or r["close"] > r.get("open", r["close"])):
            jln += 1
            terpanjang = max(terpanjang, jln)
        else:
            jln = 0
    return terpanjang


def deteksi_pola(rows, idx):
    """Pola candle sederhana di bar idx: doji/engulfing/hammer/shooting_star/biasa."""
    i = _idx(rows, idx)
    if i < 1:
        return "none"
    b, sbl = rows[i], rows[i - 1]
    o, c, h, l = b["open"], b["close"], b["high"], b["low"]
    rng = h - l
    if rng <= 0:
        return "none"
    body = abs(c - o)
    up_wick = h - max(o, c)
    dn_wick = min(o, c) - l
    if body <= 0.10 * rng:
        return "doji"
    body_sbl = abs(sbl["close"] - sbl["open"])
    if c > o and sbl["close"] < sbl["open"] and c >= sbl["open"] \
            and o <= sbl["close"] and body > body_sbl:
        return "bullish_engulfing"
    if c < o and sbl["close"] > sbl["open"] and o >= sbl["close"] \
            and c <= sbl["open"] and body > body_sbl:
        return "bearish_engulfing"
    if dn_wick >= 2 * body and up_wick <= 0.6 * body:
        return "hammer"
    if up_wick >= 2 * body and dn_wick <= 0.6 * body:
        return "shooting_star"
    return "biasa"


def f_pola(rows, p=None):
    return deteksi_pola(rows, (p or {}).get("idx", -1))


def f_struktur_naik(rows, p=None):
    """3 segmen terakhir: high naik & low naik → struktur naik."""
    segmen = (p or {}).get("segmen", 3)
    panjang = (p or {}).get("panjang", 10)
    potong = rows[-segmen * panjang:]
    highs, lows = [], []
    for k in range(segmen):
        bagian = potong[k * panjang:(k + 1) * panjang]
        if not bagian:
            return None
        highs.append(max(_high(r) for r in bagian))
        lows.append(min(_low(r) for r in bagian))
    return (highs == sorted(highs) and lows == sorted(lows)
            and highs[-1] > highs[0] and lows[-1] > lows[0])


# ── indikator lanjutan ──────────────────────────────────────────────────────

def f_rsi_bawah30(rows, p=None):
    r = chartgen.rsi([r["close"] for r in rows], 14)
    return sum(1 for v in r if v is not None and v < 30)


def f_rsi_atas70(rows, p=None):
    r = chartgen.rsi([r["close"] for r in rows], 14)
    return sum(1 for v in r if v is not None and v > 70)


def f_hari_di_atas_ma20(rows, p=None):
    m = chartgen.sma([r["close"] for r in rows], 20)
    return sum(1 for i, r in enumerate(rows)
               if m[i] is not None and r["close"] > m[i])


def _slope_sma(rows, n, p):
    jendela = (p or {}).get("n", 10)
    s = chartgen.sma([r["close"] for r in rows], n)
    if len(s) < jendela + 1 or s[-1] is None or s[-1 - jendela] is None:
        return None
    return "naik" if s[-1] > s[-1 - jendela] else "turun"


def f_ma20_slope(rows, p=None):
    return _slope_sma(rows, 20, p)


def f_ma50_slope(rows, p=None):
    return _slope_sma(rows, 50, p)


def f_perubahan_pct(rows, p=None):
    n = (p or {}).get("n", 20)
    awal = rows[-n]["close"]
    return round((rows[-1]["close"] - awal) / awal * 100, 2)


def f_jarak_ma20_pct(rows, p=None):
    m = chartgen.sma([r["close"] for r in rows], 20)
    if m[-1] is None:
        return None
    return round((rows[-1]["close"] - m[-1]) / m[-1] * 100, 2)


# ── registry ────────────────────────────────────────────────────────────────

FAKTA = {
    "n": f_n,
    "terakhir": f_terakhir,
    "ma20": f_ma20,
    "ma50": f_ma50,
    "rsi": f_rsi,
    "dd": f_dd,
    "imax": f_imax,
    "imax_high": f_imax_high,
    "cross_up_30": f_cross_up_30,
    "cross_dn_30": f_cross_dn_30,
    "low20": lambda rows, p=None: f_low_n(rows, {"n": 20}),
    "high30": lambda rows, p=None: f_high_n(rows, {"n": 30}),
    "low_n": f_low_n,
    "high_n": f_high_n,
    "sentuh": f_sentuh,
    "candle_arah": f_candle_arah,
    "merah_beruntun": f_merah_beruntun,
    "hijau_beruntun": f_hijau_beruntun,
    "pola": f_pola,
    "struktur_naik": f_struktur_naik,
    "rsi_bawah30": f_rsi_bawah30,
    "rsi_atas70": f_rsi_atas70,
    "hari_di_atas_ma20": f_hari_di_atas_ma20,
    "ma20_slope": f_ma20_slope,
    "ma50_slope": f_ma50_slope,
    "perubahan_pct": f_perubahan_pct,
    "jarak_ma20_pct": f_jarak_ma20_pct,
}


def hitung_fakta(rows, kunci, param=None):
    """Hitung 1 fakta dari baris beku. Lempar KeyError kalau kunci tak dikenal."""
    return FAKTA[kunci](rows, param)
