# QuantLab ⚡

Platform belajar **quant trading ala kelas interaktif (Kaggle-style)** — dibuat untuk trader
yang belajar dari nol: **belajar teori → kerjakan latihan coding yang disuruh** (kotak
"🎯 Tugasmu" + starter `# TODO` di editor) → uji pemahaman lewat **skenario keputusan**
(pilih keputusan → lihat hasil simulasi). Plus **Chart Drill** (latihan baca grafik
harga nyata), **soal coding** yang dinilai otomatis di sandbox, **📓 Notebook**
(workspace ala Kaggle: kernel Python hidup — variabel tersimpan antar sel — plus dataset
IDX siap pakai di `/datasets`), dan **📊 Data Science** (jalur + halaman fitur persiapan
kompetisi: cleaning → EDA → feature engineering → ML → evaluasi → deep learning —
lengkap dengan **starter notebook per bab** dan menu **Data Science** di navigasi, serta **🏁 Kompetisi Simulasi** — kirim submission,
dinilai otomatis, dapat skor & medali).

## Isi

- **7 track · 33 bab · 330 skenario keputusan · 69 soal coding · 37 Lab Teknikal + Ujian**
  - 🧮 Math 1-3 → 🐍 Python 4-7 → 💰 Finance 8-10 → 📈 Quant 11-21
  - 🚀 Advanced 22-24 → 📦 Libraries 25-27 (NumPy/Pandas/Matplotlib)
  - 📊 Data Science 28-33 (bersihin data → EDA → fitur → ML → evaluasi → deep learning;
    setiap bab punya **starter notebook** yang bisa dibuka dari halaman bab)
  - Setiap bab: 2 pelajaran teori → **latihan coding** (semua bab punya!) → 10 skenario
- **Skenario keputusan**: cerita kasus pasar (konteks Bybit funding, saham IDX) →
  4 pilihan → jawaban benar + hitungan + kode Python + hasil simulasi (return/drawdown/win rate).
- **Soal coding (69, gaya Kaggle)**: SETIAP bab punya latihan coding — kotak **🎯 Tugasmu**
  (langkah "disuruh apa") + **starter code** ber-`# TODO` yang terpasang otomatis di editor.
  Kalau soal memakai data, muncul kotak **📂 Data untuk soal ini** (path + jumlah baris/kolom).
  **Editor pintar**: kurung & kutip menutup otomatis, Tab = 4 spasi (Shift+Tab kurangi),
  Enter ikut indentasi. Ditulis & dinilai di sandbox terisolasi (bubblewrap — tanpa akses
  file/internet dari kode user); termasuk soal **"data nyata"** yang membaca CSV di `/soaldata`.
- **📓 Notebook (ala Kaggle)** — workspace Python ber-sel (kode + markdown): **kernel
  persisten per user** (variabel tersimpan antar sel), output di bawah sel (teks, nilai
  `Out[n]`, grafik matplotlib), **▶▶ Jalankan Semua** & **⟳ Restart Kernel**, simpan
  otomatis, **editor sel pintar** (auto-tutup kurung/kutip, Tab blok, Enter indent), template
  siap pakai (Kosong / Pandas / Watchlist / Backtest Mini), rail **📦 Dataset** (klik = contoh
  kode), **⬆️ upload CSV sendiri** (data latihan/lombamu — maks 5 MB, terbaca dari
  `/work/uploads/`, preview + kelola di `/notebook/datasets`). Sandbox bubblewrap terpisah (`notebook_kerneld.py`
  + worker `notebook_kernel.py`, service `quantlab-kernel.service`, port 5211, timeout
  30 dtk/sel); file tulis per user di `/work` (tersimpan antar sesi).
- **📦 Dataset latihan (22, `/notebook/datasets`)**: dikelompokkan per kategori — **Pasar &
  Saham** (IHSG, watchlist panjang/lebar, harga 5 emiten × 250 hari, BBRI/TLKM/BTC),
  **Bisnis & UMKM** (transaksi toko 2.000, transaksi UMKM 20.000 baris, gaji karyawan, kredit
  UMKM kotor/bersih/uji + sample submission), **Data Sehari-hari** (cuaca Jakarta, nilai
  siswa, kalori makanan, film) dan **ML & Teks** (pelanggan telco, log server). Semua
  read-only, dua alamat yang sama-sama jalan: `/datasets/...` (Notebook) & `/soaldata/...`
  (soal coding). Generator deterministik: `scripts/gen_dataset_latihan.py`.
- **📈 Lab Teknikal (37 drill, 4 modul, + Ujian Teknikal)** — latihan analisa teknikal pakai
  grafik harga NYATA (BBRI, TLKM, IHSG, BRPT, CUAN, ALII, BTC): baca candle & tren → level &
  struktur → indikator & risiko → **praktik klik langsung di grafik** (tandai support, pasang
  stop loss, tentukan entry/TP — dinilai dengan toleransi zona). Ada **level "Mahir"**
  (drill multi-langkah: jebakan breakout, divergensi, gap, volume, sizing) dan
  **🎓 Ujian Teknikal** (10 soal acak, 15 menit, lulus ≥70% → +100 XP + rank).
  Grafik SVG server-side (line & candlestick + volume + RSI), data dibekukan di
  `data/chart/*.csv` supaya kunci jawaban tidak pernah basi (dijaga `scripts/verify_charts.py`).
  Halaman `/chart` & `/chart/ujian`, XP 20/35/50 per tingkat.
- **🏁 Kompetisi Simulasi (`/kompetisi`)** — alur lomba sungguhan: kerjakan di notebook →
  `submission.csv` dinilai otomatis vs **150 label rahasia**: akurasi, presisi/recall,
  confusion matrix, medali (🥇≥87% · 🥈≥84% · 🥉≥78% · ✅≥76%) + riwayat percobaan.
  Pembanding terukur: tebakan mayoritas 76,0% · model contoh 84,7%.
- **📊 Data Science (`/data-science`)** — halaman fitur: **kartu level** (8 tingkat 🌱→🏆),
  **checklist per bab** (teori/coding/skenario/notebook), 6 bab terurut (28-33),
  notebook latihan starter per bab + **🏆 Playbook Kompetisi** (end-to-end sampai
  `submission.csv`), kartu **Ujian & Sertifikat**, panduan **Cara Belajar** urut 6 langkah, dan dataset
 latihan (kredit UMKM **sintetis, sengaja kotor** + **sample submission** ala kompetisi;
 read-only di `/datasets`).
- **📦 Materi Bootcamp (`/data-science/materi`)** — katalog video (🎬), slide (📄/📊)
  & reading dari bootcamp **Pacmann + Rakamin**, dibaca LANGSUNG dari folder materi
  (read-only, tanpa salin) — video didukung HTTP Range; tersusun urut siap putar/baca.
- **🎥 Panduan Belajar per bab DS** — tiap bab 28-33 menyandingkan **video/slide bootcamp**
  (deep-link ke berkas asli), **ringkasan inti teori**, **praktek terpandu**, dan snippet
  **coba sendiri** (semua snippet diuji jalan) — alur bab: panduan → teori → coding → skenario.
- Fitur lain: tantangan harian, radar kemampuan, ujian per track, ulasan cerdas
  (spaced repetition), jurnal + export CSV, leaderboard, badge, sertifikat, PWA.

## Stack

Flask + gunicorn (systemd user service `quantlab.service`), SQLite (`data/quantlab.db`,
WAL), YAML curriculum di `curriculum/levels/babNN.yaml` + `curriculum/charts.yaml`,
sandbox bubblewrap (`judge.py`), chart SVG pure-Python (`chartgen.py` + `chartfacts.py`),
daemon kernel notebook (`notebook_kerneld.py` + `notebook_kernel.py`, service
`quantlab-kernel.service`).

Konten kurikulum: `curriculum/levels/babNN.yaml` — 2 pelajaran + soal coding + 10 skenario
per bab (urutan UI: Tahap 1 Teori → Tahap 2 Coding → Tahap 3 Skenario). Setelah edit YAML,
restart service (kurikulum di-cache per proses).

Data pendukung (beku, jangan di-refresh):
`data/chart/*.csv` (grafik Lab Teknikal) · `data/soal/*.csv` (bahan soal "data nyata",
di-bind read-only ke `/soaldata` dalam sandbox) · `data/ohlc/*.csv` (snapshot OHLCV —
sumber beku drill candle; JANGAN dipakai langsung oleh drill) ·
`data/notebook_datasets/*.csv` (dataset notebook, di-bind read-only ke `/datasets`;
berisi juga 3 dataset **kredit UMKM sintetis** — kotor/bersih/uji — untuk track Data
Science; regenerate: skrip generator deterministik).

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
cp quantlab-kernel.service ~/.config/systemd/user/   # daemon Notebook (untuk /notebook)
systemctl --user daemon-reload && systemctl --user enable --now quantlab quantlab-kernel
```

Sandbox soal coding butuh `bubblewrap` (`bwrap`) di sistem.

## Deploy funnel Tailscale (referensi)

`tailscale funnel --bg --set-path /quant http://127.0.0.1:5200` — app memakai
`SubPathMiddleware` (prefix `/quant`), PWA manifest dinamis.

> Konten edukasi; angka simulasi skenario dibuat konsisten secara pedagogis,
> bukan data pasar asli. Data pasar di `data/market/` & snapshot `data/soal/`
> untuk latihan; bukan saran investasi.
