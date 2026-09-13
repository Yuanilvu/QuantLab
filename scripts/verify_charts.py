#!/usr/bin/env python3
"""Verifier Lab Teknikal (Chart Drill) QuantLab — struktur + FAKTA dari data beku.

Jalankan dari repo:
    cd ~/quantlab && .venv/bin/python scripts/verify_charts.py

Cek per drill:
- struktur: field wajib, pilihan==4 & jawaban valid (kecuali `jenis: praktik`),
  modul dikenal, tingkat valid, jumlah baris CSV == `hari` (dan punya OHLC
  kalau `jenis: candle` / praktik);
- FAKTA: tiap entri blok `fakta` dihitung ULANG dari CSV beku via chartfacts —
  kunci jawaban tidak boleh basi. Format entri: `nama: nilai` atau
  `nama: {nilai: X, ...param}`;
- praktik: `kunci` harus == fakta `kunci_fakta` dikali `kunci_faktor` (±1%);
- render: chartgen.render_drill() tidak error (line/candle/praktik).
Exit code 1 kalau ada FAIL.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import yaml  # noqa: E402
import chartgen  # noqa: E402
import chartfacts as cf  # noqa: E402

CHARTS_YAML = os.path.join(REPO, "curriculum", "charts.yaml")
MODUL = {"dasar", "level", "indikator", "praktik"}


def cocok(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.005
    return a == b


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
                  "pertanyaan", "penjelasan", "petunjuk"):
            if k not in d:
                errs.append(f"field {k} hilang")
        if d.get("tingkat") not in ("mudah", "sedang", "sulit"):
            errs.append(f"tingkat invalid: {d.get('tingkat')}")
        if d.get("modul") not in MODUL:
            errs.append(f"modul invalid: {d.get('modul')}")
        jenis = d.get("jenis", "line")
        if jenis == "praktik":
            if not isinstance(d.get("kunci"), (int, float)):
                errs.append("praktik tanpa kunci angka")
            if not isinstance(d.get("toleransi_pct"), (int, float)):
                errs.append("praktik tanpa toleransi_pct")
            if "kunci_fakta" not in d:
                errs.append("praktik tanpa kunci_fakta")
        else:
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
            rows = chartgen.load_frozen_rows(cid)
        except (OSError, ValueError) as e:
            errs.append(f"data beku tidak terbaca: {e}")
            rows = []
        if rows:
            if len(rows) != d.get("hari"):
                errs.append(f"jumlah baris CSV {len(rows)} != hari {d.get('hari')}")
            if jenis in ("candle", "praktik") and not chartgen.punya_ohlc(rows):
                errs.append("data candle/praktik tidak punya kolom OHLC")
            # fakta: boleh dict {nama: nilai|{nilai,...param}} ATAU list
            # [{nama, nilai, ...param}] (utk fakta berulang, mis. 2 index).
            fakta = d.get("fakta") or {}
            if isinstance(fakta, list):
                entri_iter = []
                for e in fakta:
                    nama = e.get("nama")
                    param = {k: v for k, v in e.items() if k not in ("nama", "nilai")}
                    entri_iter.append((nama, param or None, e.get("nilai")))
            else:
                entri_iter = []
                for kunci, entri in fakta.items():
                    if isinstance(entri, dict):
                        param = {k: v for k, v in entri.items() if k != "nilai"}
                        nilai_yaml = entri.get("nilai")
                    else:
                        param, nilai_yaml = None, entri
                    entri_iter.append((kunci, param, nilai_yaml))
            for kunci, param, nilai_yaml in entri_iter:
                try:
                    nilai_hitung = cf.hitung_fakta(rows, kunci, param)
                except KeyError:
                    errs.append(f"fakta `{kunci}` tidak dikenal")
                    continue
                except Exception as e:  # noqa: BLE001
                    errs.append(f"fakta `{kunci}` error: {e}")
                    continue
                if not cocok(nilai_yaml, nilai_hitung):
                    errs.append(f"FAKTA BEDA {kunci}: yaml={nilai_yaml} hitung={nilai_hitung}")
            if jenis == "praktik":
                kf = d.get("kunci_fakta")
                if isinstance(kf, dict):
                    nama = kf.get("nama")
                    param = {k: v for k, v in kf.items() if k != "nama"}
                else:
                    nama, param = kf, None
                try:
                    nilai = cf.hitung_fakta(rows, nama, param)
                    faktor = float(d.get("kunci_faktor", 1.0))
                    harap = float(nilai) * faktor
                    if abs(float(d["kunci"]) - harap) > max(0.5, abs(harap) * 0.01):
                        errs.append(f"KUNCI BEDA: yaml={d['kunci']} hitung={harap:.2f} "
                                    f"({nama}×{faktor})")
                except Exception as e:  # noqa: BLE001
                    errs.append(f"kunci_fakta error: {e}")
            try:
                chartgen.render_drill(d, interaktif=jenis == "praktik")
            except Exception as e:  # noqa: BLE001
                errs.append(f"render SVG error: {e}")
        status = "FAIL" if errs else "ok  "
        if errs:
            fails += 1
        print(f"{status} {cid} [{d.get('modul', '?')}] {d.get('simbol')} {d.get('hari')}h "
              f"{d.get('jenis', 'line')} {d.get('tingkat')}"
              + (f" -> {errs}" if errs else ""))
    print(f"\nTotal drill: {len(drills)} | FAIL: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
