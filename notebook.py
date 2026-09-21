"""QuantLab — Notebook (ala Kaggle): integrasi app <-> daemon kernel sandbox.

Kernel = proses Python persisten per user DI DALAM bubblewrap (variabel
tersimpan antar sel). Flask memanggil notebook_kerneld.py via HTTP lokal
127.0.0.1:5211 — lihat notebook_kerneld.py & notebook_kernel.py.
"""
import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(REPO, "data", "notebook_datasets")
KERNELD_URL = os.environ.get("KERNELD_URL", "http://127.0.0.1:5211")
EXEC_TIMEOUT_S = float(os.environ.get("KERNEL_EXEC_TIMEOUT", "30"))

CODE_CAP = 20_000
CELLS_CAP = 200
SOURCE_CAP = 50_000
PAYLOAD_CAP = 1_500_000
OUT_CAP = 20_000


def _cells(*specs):
    return [{"type": t, "source": s} for (t, s) in specs]


_TPL_KOSONG = _cells(
    ("md", "# 📓 Notebook Pertamaku\n\n"
           "Selamat datang — ini notebook pertamamu, seperti di Kaggle.\n\n"
           "- **Sel kode** dijalankan dengan tombol ▶ atau `Shift+Enter`.\n"
           "- **Sel markdown** (seperti teks ini) jadi catatan penjelasan.\n"
           "- Variabel **tersimpan antar sel** — coba `x` di sel bawah, lalu pakai lagi di sel berikutnya.\n\n"
           "📦 Data siap pakai ada di panel kanan → dibaca dari `/datasets/`."),
    ("code", "x = 5\nprint('Halo dari QuantLab! x =', x)"),
    ("code", "x * 10  # baris terakhir = nilai yang ditampilkan (Out)"),
    ("md", "## Giliranmu 🎯\n\n"
           "Ubah isi sel kode di atas, atau tambah sel baru dengan tombol **＋ Kode** di bawah. "
           "Selamat bereksperimen!"),
)

_TPL_PANDAS = _cells(
    ("md", "# 🐼 Pandas Pertama — Data IHSG\n\n"
           "Kita membaca data NYATA indeks IHSG (1 tahun) dari `/datasets/ihsg_harian.csv`.\n\n"
           "Jalankan tiap sel: klik ▶ atau tekan `Shift+Enter`."),
    ("code", "import pandas as pd\n\n"
             "df = pd.read_csv('/datasets/ihsg_harian.csv')\n"
             "print('Jumlah baris data:', len(df))\n"
             "df.head()"),
    ("code", "# Ringkasan statistik kolom angka\n"
             "df.describe().round(1)"),
    ("code", "# Return harian (perubahan harga dalam %)\n"
             "df['return_harian'] = df['close'].pct_change() * 100\n"
             "print(f\"Rata-rata return harian : {df['return_harian'].mean():.3f}%\")\n"
             "print(f\"Volatilitas (simpangan) : {df['return_harian'].std():.3f}%\")"),
    ("code", "# Grafik harga penutupan\n"
             "import matplotlib.pyplot as plt\n\n"
             "df.plot(x='date', y='close', figsize=(9, 3.5), legend=False,\n"
             "        title='IHSG — harga penutupan 1 tahun')\n"
             "plt.xlabel('tanggal')\n"
             "plt.tight_layout()\n"
             "plt.show()"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Cari **hari dengan volume terbesar**: `df.loc[df['volume'].idxmax()]`.\n"
           "2. Ganti file dengan `pd.read_csv('/datasets/btc_harian.csv')` — bandingkan!"),
)

_TPL_SAHAM = _cells(
    ("md", "# 📈 Analisa Watchlist Keluarga\n\n"
           "Enam saham pantauan: **ALII, BBRI, BRPT, CUAN, MPPA, TLKM** — data 1 tahun di "
           "`/datasets/saham_lebar.csv` (format lebar: satu kolom per saham)."),
    ("code", "import pandas as pd\n\n"
             "harga = pd.read_csv('/datasets/saham_lebar.csv', index_col='date')\n"
             "harga.tail(3)"),
    ("code", "# Performa selama setahun (%)\n"
             "performa = (harga.iloc[-1] / harga.iloc[0] - 1) * 100\n"
             "print('Performa setahun:')\n"
             "print(performa.round(1).sort_values(ascending=False))"),
    ("code", "# Volatilitas tahunan (%) — seberapa 'liar' tiap saham\n"
             "volatilitas = harga.pct_change().std() * (252 ** 0.5) * 100\n"
             "print('Volatilitas tahunan:')\n"
             "print(volatilitas.round(1).sort_values(ascending=False))"),
    ("code", "# Korelasi — seberapa searah gerakannya (1.0 = selalu bersama)\n"
             "print(harga.pct_change().corr().round(2))"),
    ("code", "# Grafik performa relatif (semua dimulai dari 100)\n"
             "import matplotlib.pyplot as plt\n\n"
             "(harga / harga.iloc[0] * 100).plot(\n"
             "    figsize=(9, 4), title='Performa relatif 1 tahun (awal = 100)')\n"
             "plt.tight_layout()\n"
             "plt.show()"),
    ("md", "## Giliranmu 🎯\n\n"
           "Hitung **drawdown** (turun terbesar dari puncak) untuk salah satu saham:\n"
           "`dd = (harga['TLKM'] / harga['TLKM'].cummax() - 1).min() * 100`."),
)

_TPL_BACKTEST = _cells(
    ("md", "# 🔁 Backtest Mini — Moving Average IHSG\n\n"
           "Uji aturan sederhana: **ikut pasar saat MA5 di atas MA20, keluar saat di bawah**.\n"
           "Ini cara paling dasar menguji ide — sama semangatnya dengan Backtest Lab."),
    ("code", "import pandas as pd\n\n"
             "df = pd.read_csv('/datasets/ihsg_harian.csv')\n"
             "df['ma5'] = df['close'].rolling(5).mean()\n"
             "df['ma20'] = df['close'].rolling(20).mean()\n"
             "df['return'] = df['close'].pct_change() * 100\n"
             "df = df.dropna()\n"
             "print('Hari siap diuji:', len(df))"),
    ("code", "# Aturan: ikut pasar hanya saat MA5 > MA20\n"
             "df['posisi'] = (df['ma5'] > df['ma20']).astype(int)\n"
             "df['hasil'] = df['posisi'].shift(1) * df['return']\n"
             "print(f\"Total return aturan MA : {df['hasil'].sum():.1f}%\")\n"
             "print(f\"Return beli-tahan saja  : {df['return'].sum():.1f}%\")"),
    ("code", "# Seberapa sering ganti posisi (transaksi)?\n"
             "ganti = df['posisi'].diff().abs().sum()\n"
             "print('Jumlah ganti posisi:', int(ganti), 'kali')"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Ganti angka MA-nya: coba `rolling(10)` vs `rolling(30)` — lebih bagus atau lebih jelek?\n"
           "2. Tambah biaya transaksi 0,15% setiap ganti posisi — masih untung?"),
)

_TPL_PLAYBOOK = _cells(
    ("md", "# 🏆 Playbook Kompetisi — dari Data ke Submission\n\n"
           "Alur standar 8 langkah. Nanti tinggal ganti dataset-nya dengan data lombamu (upload CSV-mu di panel kanan, baca dari /work/uploads/); "
           "strukturnya tetap sama:\n\n"
           "1. Lihat data → 2. Bersihin → 3. EDA → 4. Fitur → 5. Split → 6. Model → "
           "7. Evaluasi → 8. Prediksi & simpan."),
    ("code", "import pandas as pd\n\n"
             "latih = pd.read_csv('/datasets/kredit_umkm_bersih.csv')\n"
             "uji = pd.read_csv('/datasets/kredit_umkm_uji.csv')\n"
             "print('Data latih:', latih.shape, '| Data uji:', uji.shape)\n"
             "uji.head(2)"),
    ("code", "def siapkan(df):\n"
             "    hasil = df.copy()\n"
             "    hasil['rasio_pinjaman'] = hasil['pinjaman_diajukan_juta'] / hasil['omzet_bulanan_juta']\n"
             "    hasil['punya_npwp_angka'] = hasil['punya_npwp'].map({'Ya': 1, 'Tidak': 0})\n"
             "    return hasil\n\n"
             "latih = siapkan(latih)\n"
             "uji = siapkan(uji)\n"
             "print('Fitur baru siap ✔')"),
    ("code", "from sklearn.model_selection import train_test_split\n"
             "from sklearn.linear_model import LogisticRegression\n\n"
             "fitur = ['omzet_bulanan_juta', 'lama_usaha_bulan', 'pinjaman_diajukan_juta',\n"
             "         'riwayat_telat_12m', 'skor_kredit', 'rasio_pinjaman']\n"
             "X = latih[fitur]\n"
             "y = (latih['status'] == 'Macet').astype(int)\n"
             "X_latih, X_val, y_latih, y_val = train_test_split(X, y, test_size=0.25, random_state=1)\n"
             "model = LogisticRegression(max_iter=400).fit(X_latih, y_latih)\n"
             "print('Akurasi validasi:', round(model.score(X_val, y_val), 3))"),
    ("code", "# Langkah 8 — prediksi data uji & simpan submission\n"
             "prediksi = model.predict(uji[fitur])\n"
             "hasil = pd.DataFrame({\n"
             "    'id_pengajuan': uji['id_pengajuan'],\n"
             "    'status_prediksi': ['Macet' if p == 1 else 'Lancar' for p in prediksi],\n"
             "})\n"
             "hasil.to_csv('/work/submission.csv', index=False)\n"
             "print('Tersimpan di /work/submission.csv —', len(hasil), 'baris')\n"
             "hasil.head()"),
    ("md", "## Checklist kompetisi 📝\n\n"
           "- [ ] **Lihat data**: `shape`, `head`, `info` — catat kolom target.\n"
           "- [ ] **Bersihin**: nilai kosong, duplikat, tipe, outlier.\n"
           "- [ ] **EDA**: distribusi target, pola per kelompok.\n"
           "- [ ] **Fitur**: rasio, encode kategori, scaling.\n"
           "- [ ] **Split & validasi jujur** (jangan lihat test berkali-kali).\n"
           "- [ ] **Model**: mulai simpel (logreg/pohon), baru yang canggih.\n"
           "- [ ] **Evaluasi** sesuai metrik lomba (akurasi? F1? RMSE?).\n"
           "- [ ] **Submission**: kolom sesuai aturan lomba, cek jumlah baris!\n\n"
           "Selamat berlomba! 🚀"),
)

_TPL_DS28 = _cells(
    ("md", "# Latihan Bab 28 — Bersihin Data Kotor\n\n"
           "Dataset: `/datasets/kredit_umkm.csv` — data pengajuan kredit UMKM yang **kotor**: "
           "ada nilai kosong, baris duplikat, tanggal campur format, teks kategori berantakan, "
           "dan beberapa outlier.\n\n**Alur latihan:** ukur masalahnya → buang duplikat → rapikan tipe & teks "
           "→ putuskan nilai kosong & outlier.\n\nJalankan sel satu per satu dengan ▶ atau `Shift+Enter`."),
    ("code", "import pandas as pd\n\n"
             "kotor = pd.read_csv('/datasets/kredit_umkm.csv')\n"
             "print('Jumlah baris    :', len(kotor))\n"
             "print('Baris duplikat  :', kotor.duplicated().sum())\n"
             "print('Nilai kosong    :', kotor.isna().sum().sum(), 'sel')\n"
             "kotor.head(3)"),
    ("code", "# Langkah 1 — lihat nilai kosong PER KOLOM\n"
             "kosong = kotor.isna().sum()\n"
             "print(kosong[kosong > 0].sort_values(ascending=False))"),
    ("code", "# Langkah 2 — buang baris duplikat\n"
             "bersih = kotor.drop_duplicates()\n"
             "print('Sebelum:', len(kotor), '→ sesudah:', len(bersih), 'baris')"),
    ("code", "# Lihat contoh tanggal — ada 3 format berbeda, kan?\n"
             "contoh_tanggal = kotor['tanggal_pengajuan'].dropna().unique()[:8]\n"
             "print(list(contoh_tanggal))"),
    ("code", "# Lihat contoh teks kategori — berantakan (huruf kecil, spasi, singkatan)\n"
             "contoh_kota = kotor['kota'].dropna().unique()[:10]\n"
             "print(list(contoh_kota))"),
    ("code", "# TODO (giliranmu 1): rapikan teks kota & sektor\n"
             "# bersih['kota']   = bersih['kota'].str.strip().str.title()\n"
             "# bersih['sektor'] = bersih['sektor'].str.strip().str.title()\n"
             "# lalu cek: print(bersih['kota'].dropna().unique()[:10])"),
    ("code", "# TODO (giliranmu 2): temukan outlier omzet\n"
             "# print(kotor['omzet_bulanan_juta'].nlargest(3))\n"
             "# print(kotor['omzet_bulanan_juta'].nsmallest(3))\n"
             "# Pertanyaan: dibuang, di-clip, atau dibiarkan? Jelaskan alasanmu di sel markdown."),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Hitung **rata-rata omzet** sebelum vs sesudah membuang nilai kosong "
           "(`kotor['omzet_bulanan_juta'].mean()` vs `dropna().mean()`).\n"
           "2. Cek `kotor['punya_npwp'].unique()` — berapa variasi penulisannya?\n"
           "3. Lanjut kerjakan **soal Bab 28** di halaman bab (dinilai otomatis)."),
)

_TPL_DS29 = _cells(
    ("md", "# Latihan Bab 29 — EDA: Kenalan Sama Data\n\n"
           "Data: `/datasets/kredit_umkm_bersih.csv` (sudah bersih). EDA = menjawab pertanyaan "
           "sederhana dengan angka: *seperti apa datanya? apa yang berkaitan dengan 'Macet'?*"),
    ("code", "import pandas as pd\n\n"
             "df = pd.read_csv('/datasets/kredit_umkm_bersih.csv')\n"
             "kolom_angka = ['omzet_bulanan_juta', 'pinjaman_diajukan_juta',\n"
             "               'riwayat_telat_12m', 'skor_kredit']\n"
             "df[kolom_angka].describe().round(1)"),
    ("code", "# Distribusi target — kelas tidak seimbang!\n"
             "print(df['status'].value_counts())\n"
             "print('Porsi Macet:', round((df['status'] == 'Macet').mean(), 3))"),
    ("code", "# Tingkat Macet per sektor\n"
             "macet_sektor = (df.assign(macet=df['status'] == 'Macet')\n"
             "                  .groupby('sektor')['macet'].mean()\n"
             "                  .sort_values(ascending=False))\n"
             "print((macet_sektor * 100).round(1))"),
    ("code", "# Bandingkan riwayat telat: Lancar vs Macet\n"
             "banding = df.groupby('status')['riwayat_telat_12m'].mean().round(2)\n"
             "print(banding)"),
    ("code", "# TODO (giliranmu 1): bandingkan OMZET Lancar vs Macet\n"
             "# print(df.groupby('status')['omzet_bulanan_juta'].mean().round(1))"),
    ("code", "# Korelasi antar kolom angka (1.00 = selalu bersama, 0 = tidak berkaitan)\n"
             "print(df[kolom_angka[:-1]].corr().round(2))"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Kota mana yang paling banyak Macet? (`groupby('kota')`)\n"
           "2. Dari angka-angka di atas — fitur mana yang paling membedakan Macet vs Lancar?\n"
           "3. Tulis 3 temuan terbaikmu: klik **＋ Markdown** di bawah dan catat di sana."),
)

_TPL_DS30 = _cells(
    ("md", "# Latihan Bab 30 — Feature Engineering\n\n"
           "Mengubah kolom mentah jadi fitur yang **lebih berguna**. Bintang utamanya: "
           "`rasio_pinjaman = pinjaman ÷ omzet` — ukuran 'beban utang'."),
    ("code", "import pandas as pd\n\n"
             "df = pd.read_csv('/datasets/kredit_umkm_bersih.csv')\n"
             "df['rasio_pinjaman'] = (df['pinjaman_diajukan_juta']\n"
             "                        / df['omzet_bulanan_juta']).round(3)\n"
             "print(df.groupby('status')['rasio_pinjaman'].mean().round(3))"),
    ("code", "# Fitur baru: umur usaha dalam TAHUN (biar skalanya ramah)\n"
             "df['umur_usaha_tahun'] = (df['lama_usaha_bulan'] / 12).round(1)\n"
             "print(df.groupby('status')['umur_usaha_tahun'].mean().round(2))"),
    ("code", "# Encode kategori: Ya/Tidak → 1/0\n"
             "df['punya_npwp_angka'] = df['punya_npwp'].map({'Ya': 1, 'Tidak': 0})\n"
             "print(df['punya_npwp_angka'].value_counts())"),
    ("code", "# TODO (giliranmu 1): binning riwayat telat jadi 3 kategori\n"
             "# df['kategori_telat'] = pd.cut(df['riwayat_telat_12m'],\n"
             "#     bins=[-1, 1, 3, 99], labels=['rendah', 'sedang', 'tinggi'])\n"
             "# print(df.groupby('kategori_telat')['status']\n"
             "#         .apply(lambda s: (s == 'Macet').mean().round(3)))"),
    ("code", "# TODO (giliranmu 2): one-hot kolom sektor\n"
             "# dum = pd.get_dummies(df['sektor'], prefix='sek')\n"
             "# print(dum.head())"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Jalankan TODO binning — kategori telat mana yang paling Macet?\n"
           "2. Scaling (samakan skala): `(x - mean) / std` untuk kolom pinjaman — "
           "kenapa ini penting untuk model seperti neural network (bab 33)?\n"
           "3. Fitur rasio mana yang **beda paling jauh** antara Lancar vs Macet? Itu petunjuk fitur kuat!"),
)

_TPL_DS31 = _cells(
    ("md", "# Latihan Bab 31 — Machine Learning Dasar\n\n"
           "Resep ML: **fitur (X)** + **target (y)** → pisah latih/uji → latih model → ukur akurasi. "
           "Target kita: apakah pengajuan akan **Macet**?"),
    ("code", "import pandas as pd\n\n"
             "df = pd.read_csv('/datasets/kredit_umkm_bersih.csv')\n"
             "fitur = ['omzet_bulanan_juta', 'lama_usaha_bulan', 'pinjaman_diajukan_juta',\n"
             "         'riwayat_telat_12m', 'skor_kredit']\n"
             "X = df[fitur]\n"
             "y = (df['status'] == 'Macet').astype(int)\n"
             "print('Jumlah data :', len(X))\n"
             "print('Porsi Macet :', round(y.mean(), 3))"),
    ("code", "# Pisah 75% untuk latih, 25% untuk uji — WAJIB\n"
             "from sklearn.model_selection import train_test_split\n\n"
             "X_latih, X_uji, y_latih, y_uji = train_test_split(\n"
             "    X, y, test_size=0.25, random_state=1)\n"
             "print('Latih:', len(X_latih), '| Uji:', len(X_uji))"),
    ("code", "# Baseline: tebak SEMUA 'Lancar' — pembanding wajib untuk setiap model\n"
             "baseline = 1 - y_uji.mean()\n"
             "print('Akurasi baseline:', round(baseline, 3))"),
    ("code", "# Model pertama: Logistic Regression\n"
             "from sklearn.linear_model import LogisticRegression\n\n"
             "model = LogisticRegression(max_iter=400)\n"
             "model.fit(X_latih, y_latih)\n"
             "print('Akurasi model:', round(model.score(X_uji, y_uji), 3))"),
    ("code", "# TODO (giliranmu 1): coba ganti random_state (7, 42) — akurasinya berubah?\n"
             "# lalu bandingkan: 5 fitur vs 3 fitur saja (omzet, telat, skor)"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Model harus **lebih tinggi dari baseline** — kalau tidak, ada yang salah!\n"
           "2. Coba tebak dulu di markdown: fitur mana yang paling berpengaruh? "
           "Baru cek di bab 32 (evaluasi) & bandingkan dengan tebakanmu.\n"
           "3. Kalau akurasi berubah-ubah saat `random_state` diganti — itu tandanya "
           "satu split saja kurang cukup (bab 32 punya solusinya: cross-validation)."),
)

_TPL_DS32 = _cells(
    ("md", "# Latihan Bab 32 — Evaluasi & Validasi Model\n\n"
           "Akurasi saja menipu. Kita bongkar dengan **confusion matrix**, "
           "**precision/recall**, dan **cross-validation**."),
    ("code", "import pandas as pd\n"
             "from sklearn.linear_model import LogisticRegression\n"
             "from sklearn.model_selection import train_test_split\n"
             "from sklearn.metrics import confusion_matrix\n\n"
             "df = pd.read_csv('/datasets/kredit_umkm_bersih.csv')\n"
             "fitur = ['omzet_bulanan_juta', 'lama_usaha_bulan', 'pinjaman_diajukan_juta',\n"
             "         'riwayat_telat_12m', 'skor_kredit']\n"
             "X = df[fitur]\n"
             "y = (df['status'] == 'Macet').astype(int)\n"
             "X_latih, X_uji, y_latih, y_uji = train_test_split(X, y, test_size=0.25, random_state=1)\n"
             "model = LogisticRegression(max_iter=400).fit(X_latih, y_latih)\n"
             "tebakan = model.predict(X_uji)\n"
             "cm = confusion_matrix(y_uji, tebakan)\n"
             "print(cm)"),
    ("code", "# Bongkar 4 angka di atas\n"
             "TN, FP, FN, TP = cm.ravel()\n"
             "print('TP = benar tebak Macet  :', TP)\n"
             "print('TN = benar tebak Lancar :', TN)\n"
             "print('FP = salah tuduh        :', FP)\n"
             "print('FN = Macet lolos        :', FN)\n"
             "print('Akurasi  :', round((TP + TN) / (TP + TN + FP + FN), 3))\n"
             "print('Precision:', round(TP / (TP + FP), 3), '(dari yang dituduh Macet, berapa yang benar)')\n"
             "print('Recall   :', round(TP / (TP + FN), 3), '(dari Macet sungguhan, berapa yang tertangkap)')\n"
             "print('Ingat baseline:', round(1 - y_uji.mean(), 3))"),
    ("code", "# Cross-validation: ukur 5x di potongan berbeda\n"
             "from sklearn.model_selection import cross_val_score\n\n"
             "skor = cross_val_score(LogisticRegression(max_iter=400), X, y, cv=5)\n"
             "print('Skor tiap fold:', skor.round(3))\n"
             "print('Rata-rata     :', round(skor.mean(), 3), '| simpangan:', round(skor.std(), 3))"),
    ("code", "# Overfitting: pohon tanpa batas vs dibatasi\n"
             "from sklearn.tree import DecisionTreeClassifier\n\n"
             "tanpa_batas = DecisionTreeClassifier(random_state=1)\n"
             "print('Tanpa batas (CV-3):', round(cross_val_score(tanpa_batas, X, y, cv=3).mean(), 3))\n"
             "dibatasi = DecisionTreeClassifier(max_depth=4, random_state=1)\n"
             "print('max_depth=4 (CV-3):', round(cross_val_score(dibatasi, X, y, cv=3).mean(), 3))"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Bank lebih takut **Macet lolos** daripada **salah tuduh** — metrik mana yang "
           "harus dikejar: precision atau recall?\n"
           "2. Coba `max_depth` = 2, 4, 8, None — mana CV terbaik?\n"
           "3. Kenapa test set tidak boleh dipakai berulang-ulang untuk memilih model? "
           "(Tulis jawabanmu di sel markdown baru.)"),
)

_TPL_DS33 = _cells(
    ("md", "# Latihan Bab 33 — Deep Learning Dasar\n\n"
           "Neuron = **jumlah berbobot** + bias → **aktivasi**. Jaringan = banyak neuron bersusun. "
           "Kita mulai dari 1 neuron manual, lalu langsung pakai MLPClassifier."),
    ("code", "import numpy as np\n\n"
             "# 1 neuron manual: z = w·x + b, lalu aktivasi ReLU (negatif → 0)\n"
             "x = np.array([2.0, 3.0, 1.0])    # 3 sinyal masuk (mis. 3 fitur)\n"
             "w = np.array([0.5, 0.8, -0.2])   # bobot tiap sinyal\n"
             "b = -0.4                         # bias\n"
             "z = float(np.dot(w, x) + b)\n"
             "keluaran = max(0.0, z)\n"
             "print('z        =', round(z, 3))\n"
             "print('aktivasi =', round(keluaran, 3))"),
    ("code", "import pandas as pd\n"
             "from sklearn.pipeline import make_pipeline\n"
             "from sklearn.preprocessing import StandardScaler\n"
             "from sklearn.neural_network import MLPClassifier\n"
             "from sklearn.model_selection import train_test_split\n\n"
             "df = pd.read_csv('/datasets/kredit_umkm_bersih.csv')\n"
             "fitur = ['omzet_bulanan_juta', 'lama_usaha_bulan', 'pinjaman_diajukan_juta',\n"
             "         'riwayat_telat_12m', 'skor_kredit']\n"
             "X = df[fitur]\n"
             "y = (df['status'] == 'Macet').astype(int)\n"
             "X_latih, X_uji, y_latih, y_uji = train_test_split(X, y, test_size=0.25, random_state=1)\n\n"
             "mlp = make_pipeline(StandardScaler(),\n"
             "                    MLPClassifier(hidden_layer_sizes=(8,), max_iter=400, random_state=1))\n"
             "mlp.fit(X_latih, y_latih)\n"
             "print('Akurasi MLP (DENGAN scaling):', round(mlp.score(X_uji, y_uji), 3))"),
    ("code", "# Tanpa scaling — lihat sendiri kenapa scaling itu penting\n"
             "import warnings\n"
             "warnings.filterwarnings('ignore')\n\n"
             "mlp2 = MLPClassifier(hidden_layer_sizes=(8,), max_iter=400, random_state=1)\n"
             "mlp2.fit(X_latih, y_latih)\n"
             "print('Akurasi MLP (TANPA scaling):', round(mlp2.score(X_uji, y_uji), 3))"),
    ("md", "## Giliranmu 🎯\n\n"
           "1. Ganti arsitektur: `hidden_layer_sizes=(4,)` vs `(16, 16)` — mana lebih baik di data ini?\n"
           "2. Bandingkan MLP terbaik vs **LogisticRegression** (bab 31). Kalau selisihnya tipis: "
           "data ini belum butuh deep learning — itu pelajaran penting!\n"
           "3. Untuk kompetisi nyata, DL biasanya pakai **PyTorch/TensorFlow di Colab** — "
           "konsep neuron, aktivasi, dan scaling-nya sama persis seperti di sini."),
)

TEMPLATES = {
    "kosong": _TPL_KOSONG,
    "pandas": _TPL_PANDAS,
    "saham": _TPL_SAHAM,
    "backtest": _TPL_BACKTEST,
    "playbook": _TPL_PLAYBOOK,
    "ds28": _TPL_DS28,
    "ds29": _TPL_DS29,
    "ds30": _TPL_DS30,
    "ds31": _TPL_DS31,
    "ds32": _TPL_DS32,
    "ds33": _TPL_DS33,
}

# Bab track Data Science yang punya starter notebook (dibuat dari halaman bab).
BAB_TEMPLATES = {28: "ds28", 29: "ds29", 30: "ds30", 31: "ds31", 32: "ds32", 33: "ds33"}


def bab_template_key(n):
    return BAB_TEMPLATES.get(int(n))

TEMPLATE_META = {
    "kosong": {"nama": "Kosong", "emoji": "📄", "judul": "Notebook Pertamaku",
               "desc": "Mulai dari nol — satu sel kode + panduan singkat."},
    "pandas": {"nama": "Pandas Pertama", "emoji": "🐼", "judul": "Belajar Pandas — IHSG",
               "desc": "Baca data IHSG nyata, ringkasan statistik, dan grafik pertama."},
    "saham": {"nama": "Analisa Watchlist", "emoji": "📈", "judul": "Analisa Saham Watchlist",
              "desc": "Bandingkan 6 saham: performa, volatilitas, korelasi."},
    "backtest": {"nama": "Backtest Mini", "emoji": "🔁", "judul": "Backtest Mini MA",
                 "desc": "Uji aturan moving average di IHSG — lihat hasilnya."},
    "playbook": {"nama": "Playbook Kompetisi", "emoji": "🏆", "judul": "Playbook Kompetisi Data Science",
                 "desc": "Alur lengkap 8 langkah: bersihin → fitur → model → submission."},
    "ds28": {"nama": "Bersihin Data (Bab 28)", "emoji": "🧹", "judul": "Latihan Bab 28 — Bersihin Data",
             "group": "ds", "desc": "Ukur & bersihkan data kotor langkah demi langkah."},
    "ds29": {"nama": "EDA (Bab 29)", "emoji": "🔍", "judul": "Latihan Bab 29 — EDA",
             "group": "ds", "desc": "Jelajahi data: distribusi target & pola per kelompok."},
    "ds30": {"nama": "Feature Engineering (Bab 30)", "emoji": "🛠️", "judul": "Latihan Bab 30 — Fitur Baru",
             "group": "ds", "desc": "Rasio, binning, encode kategori, dan scaling."},
    "ds31": {"nama": "ML Dasar (Bab 31)", "emoji": "🤖", "judul": "Latihan Bab 31 — ML Pertama",
             "group": "ds", "desc": "Split data, baseline, dan model klasifikasi pertama."},
    "ds32": {"nama": "Evaluasi Model (Bab 32)", "emoji": "🎯", "judul": "Latihan Bab 32 — Evaluasi",
             "group": "ds", "desc": "Confusion matrix, precision/recall, dan cross-validation."},
    "ds33": {"nama": "Deep Learning (Bab 33)", "emoji": "🧠", "judul": "Latihan Bab 33 — Neuron & MLP",
             "group": "ds", "desc": "Neuron manual sampai MLPClassifier dengan scaling."},
}

DATASET_META = {
    # 📈 Pasar & saham
    "ihsg_harian.csv": "IHSG (indeks bursa) harian — date, open, high, low, close, volume. 1 tahun.",
    "saham_watchlist.csv": "6 saham pantauan (ALII, BBRI, BRPT, CUAN, MPPA, TLKM) — format panjang, satu baris per tanggal+simbol.",
    "saham_lebar.csv": "Harga penutupan 6 saham yang sama — format lebar (satu kolom per saham), siap untuk banding performa & korelasi.",
    "harga_saham_harian.csv": "5 emiten (ANTM, ASII, BBRI, BRPT, TLKM) x 250 hari bursa — format PANJANG: satu baris per tanggal+kode. Latihan: groupby, hitung return, banding volume.",
    "harga_bbri.csv": "Harga penutupan BBRI harian (snapshot beku) — date, close. Cocok untuk latihan tren & moving average.",
    "harga_tlkm.csv": "Harga penutupan TLKM harian (snapshot beku) — date, close.",
    "harga_ihsg.csv": "IHSG harian versi kecil (snapshot beku) — date, close.",
    "btc_harian.csv": "Bitcoin (BTC-USD) harian — lebih dari 1 tahun, untuk latihan aset kripto.",
    "harga_btc.csv": "Harga penutupan BTC harian versi kecil (snapshot beku) — date, close.",
    # 🏪 Bisnis & UMKM
    "transaksi_toko.csv": "2.000 transaksi toko (Jan-Jun 2026) — produk, kategori, jumlah, harga satuan, total, kota. Latihan: total per kategori, produk terlaris, tren per kota.",
    "transaksi_umkm.csv": "20.000 transaksi UMKM (data BESAR) — kota, kategori usaha, nominal (juta), metode bayar, status lunas. Latihan groupby/pivot skala ribuan baris.",
    "gaji_karyawan.csv": "500 karyawan — divisi, masa kerja, gaji (juta), lembur, pendidikan. Latihan: rata-rata per divisi, korelasi masa kerja vs gaji.",
    "kredit_umkm.csv": "Data pengajuan kredit UMKM (SINTETIS untuk latihan) — SENGAJA kotor: nilai kosong, duplikat, tanggal campur format, teks berantakan, outlier. 636 baris.",
    "kredit_umkm_bersih.csv": "Versi BERSIH dari data kredit UMKM — siap untuk EDA, fitur, dan machine learning. 620 baris.",
    "kredit_umkm_uji.csv": "Data uji kredit UMKM TANPA kolom status — bahan latihan prediksi & submission ala kompetisi. 150 baris.",
    "sample_submission-kredit_umkm.csv": "Contoh FORMAT submission ala kompetisi — kolom id_pengajuan + status_prediksi (isi placeholder 'Lancar'; ganti dengan hasil prediksimu). 150 baris.",
    # 🧑‍💻 Sehari-hari
    "cuaca_jakarta.csv": "Cuaca Jakarta 365 hari (Sep 2025 - Agu 2026) — suhu min/max, curah hujan (mm), kelembapan. Latihan: tren musiman, cari hari terbasah.",
    "nilai_siswa.csv": "400 siswa kelas 7-9 — nilai matematika/ipa/ips + kehadiran (%). Latihan: statistik, ranking, korelasi kehadiran vs nilai.",
    "kalori_makanan.csv": "40 masakan Indonesia x 3 ukuran porsi — kalori & gizi PERKIRAAN untuk latihan. Latihan: sort, filter kalori, makanan paling berprotein.",
    "film_nonton.csv": "300 film fiktif (2005-2026) — genre, rating, jumlah penonton (juta). Latihan: film terbaik per genre, korelasi tahun vs rating.",
    # 🤖 ML & teks
    "pelanggan_telco.csv": "1.200 pelanggan operator — umur, kota, paket, lama berlangganan, tagihan bulanan, churn (0/1). Latihan EDA + prediksi churn.",
    "log_server.csv": "3.000 baris log server Agustus 2026 — level (INFO/WARN/ERROR), pesan, durasi (ms), status. Latihan: filter ERROR, rata-rata durasi, olah teks pesan.",
}

# Kategori untuk halaman Dataset (urutan tampil mengikuti urutan kunci).
DATASET_KATEGORI = {
    "📈 Pasar & Saham": [
        "ihsg_harian.csv", "harga_ihsg.csv", "harga_saham_harian.csv",
        "saham_watchlist.csv", "saham_lebar.csv",
        "harga_bbri.csv", "harga_tlkm.csv", "btc_harian.csv", "harga_btc.csv",
    ],
    "🏪 Bisnis & UMKM": [
        "transaksi_toko.csv", "transaksi_umkm.csv", "gaji_karyawan.csv",
        "kredit_umkm.csv", "kredit_umkm_bersih.csv", "kredit_umkm_uji.csv",
        "sample_submission-kredit_umkm.csv",
    ],
    "🧑‍💻 Data Sehari-hari": [
        "cuaca_jakarta.csv", "nilai_siswa.csv", "kalori_makanan.csv",
        "film_nonton.csv",
    ],
    "🤖 ML & Teks": [
        "pelanggan_telco.csv", "log_server.csv",
    ],
}
KATEGORI_KUNCI = list(DATASET_KATEGORI)


def kategori_dataset(name):
    """Kategori tampil untuk sebuah file dataset."""
    for kat, daftar in DATASET_KATEGORI.items():
        if name in daftar:
            return kat
    return "📦 Lainnya"


def group_datasets(items):
    """Kelompokkan item dataset per kategori, urutan tetap (kategori kosong dibuang)."""
    grup = {kat: [] for kat in KATEGORI_KUNCI}
    lainnya = []
    for it in items:
        kat = kategori_dataset(it.get("name", ""))
        if kat in grup:
            grup[kat].append(it)
        else:
            lainnya.append(it)
    hasil = [(kat, isi) for kat, isi in grup.items() if isi]
    if lainnya:
        hasil.append(("📦 Lainnya", lainnya))
    return hasil


def template_cells(tpl):
    return [dict(c) for c in TEMPLATES.get(tpl) or TEMPLATES["kosong"]]


def cells_to_json(cells):
    return json.dumps(cells, ensure_ascii=False)


def cells_for_js(cells):
    """JSON aman untuk disematkan di <script type=application/json>."""
    return json.dumps(cells, ensure_ascii=False).replace("</", "<\\/")


def list_datasets():
    if not os.path.isdir(DATASETS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(DATASETS_DIR)):
        if not name.endswith(".csv"):
            continue
        path = os.path.join(DATASETS_DIR, name)
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, [])
                rows = sum(1 for _ in reader)
            size_kb = max(1, os.path.getsize(path) // 1024)
        except OSError:
            continue
        out.append({"name": name, "rows": rows, "cols": len(header), "kb": size_kb,
                    "desc": DATASET_META.get(name, ""), "header": header,
                    "kategori": kategori_dataset(name)})
    return out


def dataset_preview(name, n=5):
    if not name or "/" in name or ".." in name or not name.endswith(".csv"):
        return None
    path = os.path.join(DATASETS_DIR, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = []
            for i, row in enumerate(reader):
                if i >= n:
                    break
                rows.append(row)
    except OSError:
        return None
    return {"header": header, "rows": rows}


# ---------- Upload CSV sendiri (data latihan / data lomba user) ----------

WORKROOT = os.path.join(REPO, "data", "notebook_work")
UPLOAD_DIRNAME = "uploads"
UPLOAD_MAX_MB = 5
UPLOAD_MAX_FILES = 30
UPLOAD_EXTS = (".csv", ".tsv", ".txt")


def work_dir(username):
    """Folder kerja user (di-bind ke sandbox sebagai /work)."""
    safe = "".join(ch for ch in str(username or "") if ch.isalnum() or ch in "._-") or "user"
    return os.path.join(WORKROOT, safe)


def uploads_dir(username):
    """Folder uploads user = subfolder /work user (terlihat di sandbox sebagai /work/uploads)."""
    return os.path.join(work_dir(username), UPLOAD_DIRNAME)


def submission_path(username):
    """Berkas submission Kompetisi Simulasi: /work/submission.csv."""
    return os.path.join(work_dir(username), "submission.csv")


def safe_upload_name(filename):
    """Nama file aman: basename saja, charset terbatas, ekstensi .csv/.tsv/.txt."""
    name = os.path.basename(str(filename or "").strip())
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    if not name:
        return None
    base, ext = os.path.splitext(name)
    if ext.lower() not in UPLOAD_EXTS:
        return None
    return (base[:60] or "data") + ext.lower()


def _up_meta_path(username):
    return os.path.join(uploads_dir(username), "_meta.json")


def _up_load_meta(username):
    try:
        with open(_up_meta_path(username), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _up_save_meta(username, meta):
    os.makedirs(uploads_dir(username), exist_ok=True)
    with open(_up_meta_path(username), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)


def _count_csv(path, cap=500_000):
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = 0
            for _ in reader:
                rows += 1
                if rows >= cap:
                    break
        return {"rows": rows, "cols": len(header)}
    except (OSError, csv.Error):
        return {"rows": 0, "cols": 0}


def list_uploads(username):
    """Daftar file upload user: [{name, rows, cols, kb}] (baca cache _meta.json)."""
    d = uploads_dir(username)
    if not os.path.isdir(d):
        return []
    meta = _up_load_meta(username)
    out = []
    for name in sorted(os.listdir(d)):
        if name == "_meta.json" or name.startswith("."):
            continue
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        info = meta.get(name)
        if not info:
            info = {**_count_csv(p), "kb": max(1, os.path.getsize(p) // 1024)}
            meta[name] = info
        out.append({"name": name, "rows": info.get("rows", 0),
                    "cols": info.get("cols", 0), "kb": info.get("kb", 1)})
    names = {o["name"] for o in out}
    if set(meta) - names:
        meta = {k: v for k, v in meta.items() if k in names}
        _up_save_meta(username, meta)
    return out


def save_upload(username, file_storage):
    """Simpan upload user -> /work/uploads. return (ok, nama_atau_pesan)."""
    name = safe_upload_name(getattr(file_storage, "filename", ""))
    if not name:
        return False, "Hanya file .csv / .tsv / .txt yang bisa diupload."
    d = uploads_dir(username)
    meta = _up_load_meta(username)
    stream = file_storage.stream
    try:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
    except (OSError, AttributeError):
        size = 0
    if size <= 0:
        return False, "File kosong / tidak terbaca."
    if size > UPLOAD_MAX_MB * 1024 * 1024:
        return False, f"Ukuran maksimal {UPLOAD_MAX_MB} MB."
    if name not in meta and len(meta) >= UPLOAD_MAX_FILES:
        return False, f"Maksimal {UPLOAD_MAX_FILES} file \u2014 hapus dulu yang tidak terpakai."
    base, ext = os.path.splitext(name)
    nama, n = name, 2
    while nama in meta or os.path.exists(os.path.join(d, nama)):
        nama = f"{base}-{n}{ext}"
        n += 1
        if n > 99:
            return False, "Terlalu banyak file dengan nama sama."
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, nama)
    file_storage.save(path)
    info = _count_csv(path)
    meta[nama] = {**info, "kb": max(1, size // 1024)}
    _up_save_meta(username, meta)
    return True, nama


def delete_upload(username, name):
    name = safe_upload_name(name)
    if not name:
        return False, "Nama file tidak valid."
    path = os.path.join(uploads_dir(username), name)
    if not os.path.isfile(path):
        return False, "File tidak ditemukan."
    os.remove(path)
    meta = _up_load_meta(username)
    if meta.pop(name, None) is not None:
        _up_save_meta(username, meta)
    return True, name


def upload_preview(username, name, n=4):
    name = safe_upload_name(name)
    if not name:
        return None
    path = os.path.join(uploads_dir(username), name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = []
            for i, row in enumerate(reader):
                if i >= n:
                    break
                rows.append(row)
    except OSError:
        return None
    return {"header": header, "rows": rows}


def parse_payload(raw):
    """Validasi payload simpan dari klien → (judul, cells_json). Raises ValueError."""
    if not raw or len(raw) > PAYLOAD_CAP:
        raise ValueError("payload kosong atau terlalu besar")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("payload bukan JSON") from None
    judul = str(obj.get("judul") or "").strip()[:80] or "Notebook Tanpa Judul"
    cells_in = obj.get("cells")
    if not isinstance(cells_in, list) or len(cells_in) > CELLS_CAP:
        raise ValueError("daftar sel tidak valid")
    cells = []
    for c in cells_in:
        if not isinstance(c, dict):
            continue
        typ = c.get("type") if c.get("type") in ("code", "md") else "code"
        cell = {"type": typ, "source": str(c.get("source") or "")[:SOURCE_CAP]}
        out = c.get("output")
        if isinstance(out, dict):
            keep = {}
            for key in ("stdout", "stderr", "error", "result"):
                if out.get(key):
                    keep[key] = str(out.get(key))[:OUT_CAP]
            if isinstance(out.get("n"), int):
                keep["n"] = out["n"]
            if out.get("status") in ("ok", "error", "timeout"):
                keep["status"] = out["status"]
            if keep:
                cell["output"] = keep
        cells.append(cell)
    return judul, json.dumps(cells, ensure_ascii=False)


# ---------- Klien daemon kernel ----------

def _post(path, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(KERNELD_URL + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path, timeout=4):
    with urllib.request.urlopen(KERNELD_URL + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _down():
    return {"status": "unavailable",
            "message": "⚠️ Mesin kernel Notebook sedang mati. Coba lagi sebentar lagi atau hubungi admin."}


def run_cell(username, code, cell=None):
    try:
        return _post("/exec", {"user": username, "code": code, "cell": cell},
                     timeout=EXEC_TIMEOUT_S + 20)
    except (OSError, ValueError):
        return _down()


def kernel_restart(username):
    try:
        return _post("/restart", {"user": username}, timeout=25)
    except (OSError, ValueError):
        return _down()


def kernel_status(username):
    try:
        return _get("/status?user=" + urllib.parse.quote(username))
    except (OSError, ValueError):
        d = _down()
        d["exists"] = False
        d["alive"] = False
        return d
