#!/usr/bin/env python3
"""Verifier Chart Drill QuantLab — struktur + FAKTA dihitung ulang dari data beku.

Jalankan dari repo:
    cd ~/quantlab && .venv/bin/python scripts/verify_charts.py

Cek:
- struktur: id unik, 4 pilihan (string), jawaban 0-3, tingkat valid, field lengkap;
- data: setiap drill punya data/chart/<id>.csv, jumlah baris == `hari` YAML;
- fakta: angka di blok `fakta` dihitung ulang dari CSV (SMA/RSI/drawdown/posisi)
  dan harus COCOK — ini pengaman agar kunci jawaban tidak pernah basi;
- render: chartgen.svg_price_chart() tidak error utk tiap drill.
Exit code 1 kalau ada FAIL.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import yaml  # noqa: E402
import chartgen  # noqa: E402

CHARTS_YAML = os.path.join(REPO, "curriculum", "charts.yaml")


def hitung_fakta(dates, closes):
    """Hitung semua besaran yang boleh dipin di blok `fakta`."""
    m20 = chartgen.sma(closes, 20)
    m50 = chartgen.sma(closes, 50)
    r = chartgen.rsi(closes, 14)
    puncak = 0.0
    dd = 0.0
    for c in closes:
        puncak = max(puncak, c)
        dd = max(dd, (puncak - c) / puncak * 100)
    cross_up = cross_dn = 0
    for i in range(max(1, len(closes) - 30), len(closes)):
        if None in (m20[i], m20[i - 1], m50[i], m50[i - 1]):
            continue
        if m20[i - 1] <= m50[i - 1] and m20[i] > m50[i]:
            cross_up += 1
        if m20[i - 1] >= m50[i - 1] and m20[i] < m50[i]:
            cross_dn += 1
    return {
        "terakhir": round(closes[-1], 2),
        "ma20": round(m20[-1], 2) if m20[-1] is not None else None,
        "ma50": round(m50[-1], 2) if m50[-1] is not None else None,
        "rsi": round(r[-1], 2) if r[-1] is not None else None,
        "low20": round(min(closes[-20:]), 2),
        "high30": round(max(closes[-30:]), 2),
        "dd": round(dd, 2),
        "imax": closes.index(max(closes)),
        "n": len(closes),
        "cross_up_30": cross_up,
        "cross_dn_30": cross_dn,
    }


def main():
    with open(CHARTS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    drills = data.get("drills") or []
    fails = 0
    ids = set()
    for d in drills:
        cid = d.get("id", "?")
        errs = []
        if cid in ids:
            errs.append("id duplikat")
        ids.add(cid)
        for k in ("judul", "emoji", "tingkat", "menit", "simbol", "hari",
                  "pertanyaan", "pilihan", "jawaban", "penjelasan", "petunjuk"):
            if k not in d:
                errs.append(f"field {k} hilang")
        if d.get("tingkat") not in ("mudah", "sedang", "sulit"):
            errs.append(f"tingkat invalid: {d.get('tingkat')}")
        pilihan = d.get("pilihan") or []
        if len(pilihan) != 4:
            errs.append(f"pilihan != 4 ({len(pilihan)})")
        if any(not isinstance(p, str) for p in pilihan):
            errs.append("ada pilihan bukan string")
        if not (0 <= d.get("jawaban", -1) <= 3):
            errs.append("jawaban invalid")
        if not len(d.get("petunjuk") or []):
            errs.append("petunjuk kosong")

        try:
            dates, closes = chartgen.load_frozen(cid)
        except (OSError, ValueError) as e:
            errs.append(f"data beku tidak terbaca: {e}")
            dates, closes = [], []
        if closes:
            if len(closes) != d.get("hari"):
                errs.append(f"jumlah baris CSV {len(closes)} != hari {d.get('hari')}")
            fk = hitung_fakta(dates, closes)
            for k, v in (d.get("fakta") or {}).items():
                if k not in fk:
                    errs.append(f"fakta.{k} tidak dikenal")
                    continue
                if isinstance(v, float) or isinstance(fk[k], float):
                    cocok = abs(float(v) - float(fk[k])) < 0.005
                else:
                    cocok = v == fk[k]
                if not cocok:
                    errs.append(f"FAKTA BEDA {k}: yaml={v} hitung={fk[k]}")
            try:
                chartgen.svg_price_chart(
                    dates, closes, ma=tuple(d.get("ma") or ()),
                    rsi_panel=bool(d.get("rsi_panel")), garis=d.get("garis") or [])
            except Exception as e:  # noqa: BLE001
                errs.append(f"render SVG error: {e}")
        status = "FAIL" if errs else "ok  "
        if errs:
            fails += 1
        print(f"{status} {cid} {d.get('simbol')} {d.get('hari')}h "
              f"{d.get('tingkat')} jawaban={d.get('jawaban')}"
              + (f" -> {errs}" if errs else ""))
    print(f"\nTotal drill: {len(drills)} | FAIL: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
