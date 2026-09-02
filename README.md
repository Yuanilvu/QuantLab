# QuantLab ⚡

Platform belajar **quant trading lewat skenario keputusan** — ala freeCodeCamp/HackerRank,
dibuat untuk trader yang tidak ngoding: baca kasus pasar → pilih keputusan → lihat
terjemahan Python-nya → lihat hasil simulasi 4 keputusan.

## Isi

- **6 track · 27 bab · 135 skenario keputusan · 33 soal coding**
  - 🧮 Math 1-3 → 🐍 Python 4-7 → 💰 Finance 8-10 → 📈 Quant 11-20
  - 🚀 Advanced 21-24 → 📦 Libraries 25-27 (NumPy/Pandas/Matplotlib)
- **Skenario keputusan**: cerita kasus pasar (konteks Bybit funding, saham IDX) →
  4 pilihan → jawaban benar + hitungan + kode Python + hasil simulasi (return/drawdown/win rate).
- **Soal coding**: ditulis & dinilai di sandbox terisolasi (bubblewrap — tanpa akses
  file/internet dari kode user).
- **Backtest Lab**: data pasar nyata (`data/market/*.csv`, 1 tahun) + strategi
  MA/RSI/Bollinger/Breakout → metrik + equity curve + export CSV.
- Fitur lain: tantangan harian, radar kemampuan, ujian per track, ulasan cerdas
  (spaced repetition), jurnal + export CSV, analitik, leaderboard, badge, sertifikat, PWA.

## Stack

Flask + gunicorn (systemd user service `quantlab.service`), SQLite (`data/quantlab.db`,
WAL), YAML curriculum di `curriculum/levels/babNN.yaml`, sandbox bubblewrap (`judge.py`).

Konten kurikulum: `curriculum/levels/babNN.yaml` — 2 pelajaran + 5 skenario + (opsional)
soal coding per bab. Setelah edit YAML, restart service (kurikulum di-cache per proses).

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
> bukan data pasar asli. Data pasar di `data/market/` untuk backtest lab.
