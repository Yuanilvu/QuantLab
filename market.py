"""QuantLab — Market: data harga historis NYATA (bundled CSV) + engine backtest.

Data: diunduh dari Yahoo Finance (1 tahun harian) pada 2026-09-01.
Tujuan: edukasi backtesting. Bukan saran investasi; hasil masa lalu
tidak menjamin masa depan. Fee diasumsikan (default IDX 0.15%/sisi).
"""
import csv
import math
import os

MARKET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "market")

_cache = {}

FEE_DEFAULT = 0.0015   # 0.15% per sisi (IDX)

STRATEGIES = [
    ("ma", "MA Crossover", ["fast", "slow"]),
    ("rsi", "RSI", ["period", "buy", "sell"]),
    ("boll", "Bollinger", ["period", "k"]),
    ("breakout", "Breakout", ["window"]),
]


def available():
    """Daftar aset: symbol, nama, jumlah hari, harga terakhir."""
    out = []
    for fn in sorted(os.listdir(MARKET_DIR)):
        if not fn.endswith(".csv"):
            continue
        sym = fn[:-4]
        d = load(sym)
        out.append({"sym": sym, "n": len(d["close"]),
                    "last": d["close"][-1], "first": d["close"][0],
                    "start": d["dates"][0], "end": d["dates"][-1]})
    return out


def load(sym):
    if sym in _cache:
        return _cache[sym]
    path = os.path.join(MARKET_DIR, sym + ".csv")
    if not os.path.exists(path):
        return None
    dates, closes = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dates.append(row["date"])
            closes.append(float(row["close"]))
    data = {"dates": dates, "close": closes}
    _cache[sym] = data
    return data


def sma(values, n):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = values[i] - values[i - 1]
        gains += max(ch, 0)
        losses += max(-ch, 0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(values)):
        ch = values[i] - values[i - 1]
        avg_g = (avg_g * (period - 1) + max(ch, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-ch, 0)) / period
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def run_lab(sym, strategy, params, fee=FEE_DEFAULT):
    """Jalankan backtest long-only. Return dict hasil (atau error)."""
    data = load(sym)
    if not data:
        return {"error": f"Aset {sym} tidak ditemukan."}
    closes = data["close"]
    dates = data["dates"]
    n = len(closes)
    sig = [False] * n   # True = posisi long

    if strategy == "ma":
        fast = max(2, int(params.get("fast", 10)))
        slow = max(fast + 1, int(params.get("slow", 30)))
        fma, sma_ = sma(closes, fast), sma(closes, slow)
        for i in range(n):
            if fma[i] is not None and sma_[i] is not None:
                sig[i] = fma[i] > sma_[i]
    elif strategy == "rsi":
        period = max(2, int(params.get("period", 14)))
        buy = float(params.get("buy", 30))
        sell = float(params.get("sell", 70))
        r = rsi(closes, period)
        for i in range(n):
            if r[i] is None:
                continue
            if r[i] < buy:
                sig[i] = True
            elif r[i] > sell:
                sig[i] = False
            elif i > 0:
                sig[i] = sig[i - 1]
    elif strategy == "boll":
        period = max(2, int(params.get("period", 20)))
        k = float(params.get("k", 2))
        mid = sma(closes, period)
        sd = [None] * n
        for i in range(period - 1, n):
            window = closes[i - period + 1:i + 1]
            m = mid[i]
            sd[i] = math.sqrt(sum((x - m) ** 2 for x in window) / period)
        for i in range(n):
            if mid[i] is None:
                continue
            lower = mid[i] - k * sd[i]
            if closes[i] < lower:
                sig[i] = True
            elif closes[i] > mid[i]:
                sig[i] = False
            elif i > 0:
                sig[i] = sig[i - 1]
    elif strategy == "breakout":
        window = max(2, int(params.get("window", 20)))
        for i in range(n):
            if i < window:
                continue
            hi = max(closes[i - window:i])
            lo = min(closes[i - window:i])
            if closes[i] > hi:
                sig[i] = True
            elif closes[i] < lo:
                sig[i] = False
            elif i > 0:
                sig[i] = sig[i - 1]
    else:
        return {"error": "Strategi tidak dikenal."}

    # Eksekusi long-only dengan fee — eq SELALU sejajar dengan dates (len n)
    eq = [100.0] * n
    in_pos = False
    entry_i = 0
    trades = []
    for i in range(1, n):
        if sig[i] and not in_pos:
            in_pos = True
            entry_i = i
            eq[i] = eq[i - 1] * (1 - fee)
        elif not sig[i] and in_pos:
            in_pos = False
            ret = closes[i] / closes[entry_i] - 1
            eq[i] = eq[i - 1] * (1 + ret) * (1 - fee)
            trades.append({"entry": dates[entry_i], "exit": dates[i],
                           "entry_px": closes[entry_i], "exit_px": closes[i],
                           "ret": round(ret * 100, 2)})
        else:
            eq[i] = eq[i - 1] * (closes[i] / closes[i - 1]) if in_pos else eq[i - 1]
    if in_pos:  # tutup posisi di harga terakhir (dengan fee)
        ret = closes[-1] / closes[entry_i] - 1
        eq[-1] = eq[-1] * (1 + ret) * (1 - fee)
        trades.append({"entry": dates[entry_i], "exit": dates[-1],
                       "entry_px": closes[entry_i], "exit_px": closes[-1],
                       "ret": round(ret * 100, 2)})

    # Metrik
    total_ret = (eq[-1] / 100 - 1) * 100
    peak = 100.0
    maxdd = 0.0
    for v in eq:
        peak = max(peak, v)
        maxdd = max(maxdd, (peak - v) / peak * 100)
    daily = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    mean = sum(daily) / len(daily) if daily else 0
    var = sum((d - mean) ** 2 for d in daily) / len(daily) if daily else 0
    sd = math.sqrt(var)
    sharpe = mean / sd * math.sqrt(252) if sd > 0 else 0
    wins = [t for t in trades if t["ret"] > 0]
    bh = (closes[-1] / closes[0] - 1) * 100
    step = max(1, n // 160)
    eq_diff = eq[::step]
    eq_dates = dates[::step]
    bh_eq = [round(100 * closes[i] / closes[0], 2) for i in range(0, n, step)]
    if len(eq_diff) < 2:
        eq_diff, eq_dates, bh_eq = eq, dates, [100 * c / closes[0] for c in closes]

    return {
        "sym": sym, "strategy": strategy, "params": params, "fee": fee,
        "n_days": n, "start": dates[0], "end": dates[-1],
        "ret": round(total_ret, 2), "maxdd": round(maxdd, 2),
        "sharpe": round(sharpe, 2), "win_rate": round(len(wins) / len(trades) * 100) if trades else 0,
        "trades_n": len(trades), "buy_hold": round(bh, 2),
        "eq": eq_diff, "eq_dates": eq_dates, "bh_eq": bh_eq, "trades": trades[-30:],
    }
