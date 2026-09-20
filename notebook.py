"""QuantLab — Notebook (ala Kaggle): integrasi app <-> daemon kernel sandbox.

Kernel = proses Python persisten per user DI DALAM bubblewrap (variabel
tersimpan antar sel). Flask memanggil notebook_kerneld.py via HTTP lokal
127.0.0.1:5211 — lihat notebook_kerneld.py & notebook_kernel.py.
"""
import csv
import json
import os
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

TEMPLATES = {
    "kosong": _TPL_KOSONG,
    "pandas": _TPL_PANDAS,
    "saham": _TPL_SAHAM,
    "backtest": _TPL_BACKTEST,
}

TEMPLATE_META = {
    "kosong": {"nama": "Kosong", "emoji": "📄", "judul": "Notebook Pertamaku",
               "desc": "Mulai dari nol — satu sel kode + panduan singkat."},
    "pandas": {"nama": "Pandas Pertama", "emoji": "🐼", "judul": "Belajar Pandas — IHSG",
               "desc": "Baca data IHSG nyata, ringkasan statistik, dan grafik pertama."},
    "saham": {"nama": "Analisa Watchlist", "emoji": "📈", "judul": "Analisa Saham Watchlist",
              "desc": "Bandingkan 6 saham: performa, volatilitas, korelasi."},
    "backtest": {"nama": "Backtest Mini", "emoji": "🔁", "judul": "Backtest Mini MA",
                 "desc": "Uji aturan moving average di IHSG — lihat hasilnya."},
}

DATASET_META = {
    "ihsg_harian.csv": "IHSG (indeks bursa) harian — date, open, high, low, close, volume. 1 tahun.",
    "saham_watchlist.csv": "6 saham pantauan (ALII, BBRI, BRPT, CUAN, MPPA, TLKM) — format panjang, satu baris per tanggal+simbol.",
    "saham_lebar.csv": "Harga penutupan 6 saham yang sama — format lebar (satu kolom per saham), siap untuk banding performa & korelasi.",
    "btc_harian.csv": "Bitcoin (BTC-USD) harian — lebih dari 1 tahun, untuk latihan aset kripto.",
}


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
                    "desc": DATASET_META.get(name, "")})
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
