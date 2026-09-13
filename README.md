# QuantLab ⚡

Platform belajar **quant trading lewat skenario keputusan** — ala freeCodeCamp/HackerRank,
dibuat untuk trader yang tidak ngoding: baca kasus pasar → pilih keputusan → lihat
terjemahan Python-nya → lihat hasil simulasi 4 keputusan. Plus **Chart Drill** (latihan
baca grafik harga nyata) dan **soal coding** yang dinilai otomatis.

## Isi

- **6 track · 27 bab · 270 skenario keputusan · 43 soal coding · 37 Lab Teknikal + Ujian**
  - 🧮 Math 1-3 → 🐍 Python 4-7 → 💰 Finance 8-10 → 📈 Quant 11-21
  - 🚀 Advanced 22-24 → 📦 Libraries 25-27 (NumPy/Pandas/Matplotlib)
- **Skenario keputusan**: cerita kasus pasar (konteks Bybit funding, saham IDX) →
  4 pilihan → jawaban benar + hitungan + kode Python + hasil simulasi (return/drawdown/win rate).
- **Soal coding (43)**: ditulis & dinilai di sandbox terisolasi (bubblewrap — tanpa akses
  file/internet dari kode user). Track Python & Advanced/Libraries + track Quant (bab 11-21,
  termasuk 2 soal **"data nyata"** yang membaca snapshot harga di `/soaldata`).
- **📈 Lab Teknikal (37 drill, 4 modul, + Ujian Teknikal)** — latihan analisa teknikal pakai
  grafik harga NYATA (BBRI, TLKM, IHSG, BRPT, CUAN, ALII, BTC): baca candle & tren → level &
  struktur → indikator & risiko → **praktik klik langsung di grafik** (tandai support, pasang
  stop loss, tentukan entry/TP — dinilai dengan toleransi zona). Ada **level "Mahir"**
  (drill multi-langkah: jebakan breakout, divergensi, gap, volume, sizing) dan
  **🎓 Ujian Teknikal** (10 soal acak, 15 menit, lulus ≥70% → +100 XP + rank).
  Grafik SVG server-side (line & candlestick + volume + RSI), data dibekukan di
  `data/chart/*.csv` supaya kunci jawaban tidak pernah basi (dijaga `scripts/verify_charts.py`).
  Halaman `/chart` & `/chart/ujian`, XP 20/35/50 per tingkat.
- **Backtest Lab**: data pasar nyata (`data/market/*.csv`, 1 tahun) + strategi
  MA/RSI/Bollinger/Breakout → metrik + equity curve + export CSV.
- Fitur lain: tantangan harian, radar kemampuan, ujian per track, ulasan cerdas
  (spaced repetition), jurnal + export CSV, analitik, leaderboard, badge, sertifikat, PWA.

## Stack

Flask + gunicorn (systemd user service `quantlab.service`), SQLite (`data/quantlab.db`,
WAL), YAML curriculum di `curriculum/levels/babNN.yaml` + `curriculum/charts.yaml`,
sandbox bubblewrap (`judge.py`), chart SVG pure-Python (`chartgen.py` + `chartfacts.py`).

Konten kurikulum: `curriculum/levels/babNN.yaml` — 2 pelajaran + 10 skenario + (opsional)
soal coding per bab. Setelah edit YAML, restart service (kurikulum di-cache per proses).

Data pendukung (beku, jangan di-refresh):
`data/chart/*.csv` (grafik Lab Teknikal) · `data/soal/*.csv` (bahan soal "data nyata",
di-bind read-only ke `/soaldata` dalam sandbox) · `data/ohlc/*.csv` (snapshot OHLCV —
sumber beku drill candle; JANGAN dipakai langsung oleh drill).

## Verifikasi

```bash
cd ~/quantlab
.venv/bin/python scripts/verify_charts.py   # Chart Drill: fakta dihitung ulang dari CSV
.venv/bin/python scripts/smoke_test.py      # smoke app
# verifier kurikulum penuh (struktur + menjalankan SEMUA solusi soal di sandbox):
.venv/bin/python ~/.hermes/skills/productivity/quantlab-app/scripts/verify_curriculum.py
```

## Jalankan

```bash
# venv + deps
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# dev
.venv/bin/python app.py          # http://127.0.0.1:5200

# produksi (systemd user)
cp quantlab.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now quantlab
```

Sandbox soal coding butuh `bubblewrap` (`bwrap`) di sistem.

## Deploy funnel Tailscale (referensi)

`tailscale funnel --bg --set-path /quant http://127.0.0.1:5200` — app memakai
`SubPathMiddleware` (prefix `/quant`), PWA manifest dinamis.

> Konten edukasi; angka simulasi skenario dibuat konsisten secara pedagogis,
> bukan data pasar asli. Data pasar di `data/market/` & snapshot `data/soal/`
> untuk latihan; bukan saran investasi.
