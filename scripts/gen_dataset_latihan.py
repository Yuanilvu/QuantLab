#!/usr/bin/env python3
"""Generator dataset latihan QuantLab (SINTETIS, deterministik).

Menambah 10 dataset latihan BARU untuk Notebook + soal coding:
  harga_saham_harian.csv   transaksi_toko.csv     pelanggan_telco.csv
  nilai_siswa.csv          cuaca_jakarta.csv      log_server.csv
  transaksi_umkm.csv       gaji_karyawan.csv      kalori_makanan.csv
  film_nonton.csv

Semua ditulis ke data/notebook_datasets/ (mount /datasets di notebook) lalu
disinkronkan ke data/soal/ (mount /soaldata di soal coding) supaya DUA folder
selalu identik — data yang sama bisa dibaca dari kedua tempat.

Jalankan: cd ~/quantlab && .venv/bin/python scripts/gen_dataset_latihan.py
Idempoten (seed tetap): dijalankan ulang menghasilkan angka yang sama.

⚠️ File LAMA (kredit_umkm*, harga_bbri/btc/ihsg/tlkm, sample_submission) TIDAK
diregenerasi — angkanya dibekukan di materi & tes kurikulum. Skrip ini hanya
membuat file baru + menyalin file yang belum ada di sisi folder lain.
"""
import csv
import os
import random
import shutil
from datetime import date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTEBOOK_DIR = os.path.join(REPO, "data", "notebook_datasets")
SOAL_DIR = os.path.join(REPO, "data", "soal")

BULAN = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
         7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}


def tulis(nama, header, baris):
    """Tulis CSV ke folder notebook (sumber), mirror menyusul di akhir."""
    path = os.path.join(NOTEBOOK_DIR, nama)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(baris)
    print(f"  tulis {nama:28s} {len(baris):>6} baris x {len(header)} kolom")
    return len(baris)


def hari_kerja(mulai, jumlah):
    """Daftar tanggal hari kerja (Senin-Jumat)."""
    hasil = []
    hari = mulai
    while len(hasil) < jumlah:
        if hari.weekday() < 5:
            hasil.append(hari)
        hari += timedelta(days=1)
    return hasil


# ---------------------------------------------------------------- 1. saham
def gen_harga_saham():
    """Long format: satu baris per (tanggal, kode) — latihan groupby & sort."""
    rnd = random.Random(101)
    emiten = {"ANTM": 1600, "ASII": 4800, "BBRI": 4500, "BRPT": 1100, "TLKM": 2900}
    hari = hari_kerja(date(2025, 9, 1), 250)
    posisi = {kode: float(base) for kode, base in emiten.items()}
    baris = []
    for tgl in hari:
        for kode, _ in sorted(emiten.items()):
            close_lalu = posisi[kode]
            buka = int(close_lalu * (1 + rnd.uniform(-0.012, 0.012)))
            close = int(max(50.0, close_lalu * (1 + rnd.uniform(-0.028, 0.030))))
            tinggi = int(max(buka, close) * (1 + rnd.uniform(0.0, 0.02)))
            rendah = int(min(buka, close) * (1 - rnd.uniform(0.0, 0.02)))
            volume = int(rnd.uniform(5e5, 90e6))
            posisi[kode] = float(close)
            baris.append([tgl.isoformat(), kode, buka, tinggi, rendah, close, volume])
    return tulis("harga_saham_harian.csv",
                 ["tanggal", "kode", "open", "high", "low", "close", "volume"], baris)


# ---------------------------------------------------------------- 2. toko
def gen_transaksi_toko():
    rnd = random.Random(202)
    produk = [
        ("Kopi Susu", "Minuman", 18000), ("Teh Manis", "Minuman", 8000),
        ("Es Teh", "Minuman", 6000), ("Air Mineral", "Minuman", 4000),
        ("Susu UHT", "Minuman", 7000), ("Nasi Goreng", "Makanan", 25000),
        ("Mie Ayam", "Makanan", 20000), ("Sate Ayam", "Makanan", 30000),
        ("Ayam Geprek", "Makanan", 22000), ("Bakso", "Makanan", 18000),
        ("Keripik", "Snack", 12000), ("Kue Lapis", "Snack", 15000),
        ("Pisang Goreng", "Snack", 10000), ("Martabak", "Snack", 35000),
    ]
    kota = ["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar"]
    mulai = date(2026, 1, 1)
    baris = []
    for i in range(2000):
        nama_produk, kategori, harga_dasar = rnd.choice(produk)
        harga_satuan = harga_dasar + rnd.choice([0, 500, 1000])
        jumlah = rnd.randint(1, 4)
        tanggal = (mulai + timedelta(days=rnd.randrange(0, 181))).isoformat()
        baris.append([tanggal, f"TRX-{i + 1:04d}", nama_produk, kategori,
                      jumlah, harga_satuan, jumlah * harga_satuan, rnd.choice(kota)])
    return tulis("transaksi_toko.csv",
                 ["tanggal", "id_transaksi", "produk", "kategori", "jumlah",
                  "harga_satuan", "total", "kota"], baris)


# ---------------------------------------------------------------- 3. telco
def gen_pelanggan_telco():
    rnd = random.Random(303)
    kota = ["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar", "Semarang"]
    paket_dasar = {"Hemat": 55000, "Data Only": 85000, "Sultan": 150000, "Sultan+": 250000}
    baris = []
    for i in range(1200):
        paket = rnd.choice(list(paket_dasar))
        lama = rnd.randint(1, 60)
        tagihan = paket_dasar[paket] + rnd.randrange(-5, 16) * 1000
        peluang_churn = 0.05 + 0.22 * (1 - min(lama, 24) / 24)
        if paket == "Hemat":
            peluang_churn += 0.12
        if tagihan > 200000:
            peluang_churn += 0.08
        churn = 1 if rnd.random() < peluang_churn else 0
        baris.append([f"C-{i + 1:04d}", rnd.randint(17, 70), rnd.choice(kota), paket,
                      lama, tagihan, churn])
    return tulis("pelanggan_telco.csv",
                 ["id_pelanggan", "umur", "kota", "paket", "lama_berlangganan_bulan",
                  "tagihan_bulanan", "churn"], baris)


# ---------------------------------------------------------------- 4. siswa
def gen_nilai_siswa():
    rnd = random.Random(404)
    depan = ["Andi", "Budi", "Citra", "Dewi", "Eko", "Fajar", "Gita", "Hadi",
             "Indah", "Joko", "Kartika", "Lukman", "Maya", "Nanda", "Oscar",
             "Putri", "Rangga", "Sari", "Taufik", "Umi"]
    belakang = ["Pratama", "Saputra", "Wijaya", "Lestari", "Nugroho", "Ramadhan",
                "Safitri", "Hidayat", "Anggraini", "Firmansyah", "Kusuma", "Maulana",
                "Purnama", "Siregar", "Tambunan", "Utami", "Wibowo", "Yuliana",
                "Zulaikha", "Halim"]
    kelas = ["7A", "7B", "7C", "8A", "8B", "8C", "9A", "9B", "9C"]
    baris = []
    for i in range(400):
        dasar = rnd.randint(55, 95)
        def nilai():
            return max(40, min(100, dasar + rnd.randint(-10, 10)))
        baris.append([f"S-{i + 1:04d}", f"{rnd.choice(depan)} {rnd.choice(belakang)}",
                      rnd.choice(kelas), nilai(), nilai(), nilai(),
                      rnd.randint(70, 100)])
    return tulis("nilai_siswa.csv",
                 ["nis", "nama", "kelas", "nilai_matematika", "nilai_ipa",
                  "nilai_ips", "kehadiran_persen"], baris)


# ---------------------------------------------------------------- 5. cuaca
def gen_cuaca_jakarta():
    rnd = random.Random(505)
    mulai = date(2025, 9, 1)
    baris = []
    for i in range(365):
        tgl = mulai + timedelta(days=i)
        musim_hujan = tgl.month in (11, 12, 1, 2, 3)
        suhu_min = rnd.randint(23, 26)
        suhu_max = suhu_min + rnd.randint(4, 10)
        hujan = rnd.expovariate(1 / 8.0 if musim_hujan else 1 / 25.0)
        hujan = round(min(hujan, 120.0), 1)
        lembap = rnd.randint(60, 95) if hujan > 5 else rnd.randint(58, 85)
        baris.append([tgl.isoformat(), suhu_min, suhu_max, hujan, lembap])
    return tulis("cuaca_jakarta.csv",
                 ["tanggal", "suhu_min", "suhu_max", "curah_hujan_mm",
                  "kelembapan_persen"], baris)


# ---------------------------------------------------------------- 6. log
def gen_log_server():
    rnd = random.Random(606)
    mulai = date(2026, 8, 1)
    baris = []
    for i in range(3000):
        level = rnd.choices(["INFO", "WARN", "ERROR"], weights=[70, 20, 10])[0]
        if level == "INFO":
            pesan = rnd.choice([
                "login berhasil user={u}", "halaman dashboard dimuat",
                "sinkronisasi data selesai", "backup harian selesai",
                "email notifikasi terkirim", "cache diperbarui"])
            status, durasi = 200, rnd.randint(5, 300)
        elif level == "WARN":
            pesan = rnd.choice([
                "respons lambat endpoint=/api/harga", "memori 80% terpakai",
                "retry koneksi database", "token kedaluwarsa user={u}"])
            status, durasi = rnd.choice([200, 429]), rnd.randint(300, 2000)
        else:
            pesan = rnd.choice([
                "gagal koneksi database", "pembayaran gagal order=INV-{n}",
                "file tidak ditemukan /data/{n}.csv", "timeout endpoint=/api/laporan"])
            status, durasi = rnd.choice([500, 404]), rnd.randint(500, 4000)
        pesan = pesan.replace("{u}", f"user-{rnd.randint(1, 400):03d}")
        pesan = pesan.replace("{n}", str(rnd.randint(1000, 9999)))
        detik = rnd.randrange(0, 31 * 24 * 3600)
        waktu = f"{(mulai + timedelta(seconds=detik)).isoformat()}T" \
                f"{rnd.randrange(24):02d}:{rnd.randrange(60):02d}:{rnd.randrange(60):02d}"
        baris.append([waktu, level, pesan, durasi, status])
    baris.sort(key=lambda r: r[0])
    return tulis("log_server.csv",
                 ["waktu", "level", "pesan", "durasi_ms", "status"], baris)


# ---------------------------------------------------------------- 7. UMKM
def gen_transaksi_umkm():
    """Dataset BESAR (20 ribu baris) — latihan pandas di skala nyata."""
    rnd = random.Random(707)
    kota = ["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar", "Semarang",
            "Yogyakarta", "Denpasar", "Palembang", "Balikpapan"]
    kategori = ["Kuliner", "Retail", "Jasa", "Pertanian", "Kerajinan"]
    mulai = date(2025, 6, 1)
    baris = []
    for i in range(20000):
        nominal = min(25.0, max(0.05, round(rnd.lognormvariate(0.9, 0.9), 2)))
        baris.append([
            f"T-{i + 1:06d}",
            (mulai + timedelta(days=rnd.randrange(0, 458))).isoformat(),
            rnd.choice(kota), rnd.choice(kategori), nominal,
            rnd.choices(["QRIS", "Transfer", "Tunai"], weights=[45, 30, 25])[0],
            rnd.choices(["Lunas", "Tempo", "Belum"], weights=[82, 12, 6])[0]])
    return tulis("transaksi_umkm.csv",
                 ["id", "tanggal", "kota", "kategori_usaha", "nominal_juta",
                  "metode", "lunas"], baris)


# ---------------------------------------------------------------- 8. gaji
def gen_gaji_karyawan():
    rnd = random.Random(808)
    divisi_bonus = {"Teknologi": 2.0, "Keuangan": 1.5, "Marketing": 0.8,
                    "Operasional": 0.3, "SDM": 0.5}
    didik_bonus = {"SMA": 0.0, "S1": 0.8, "S2": 2.2}
    baris = []
    for i in range(500):
        divisi = rnd.choice(list(divisi_bonus))
        didik = rnd.choices(["SMA", "S1", "S2"], weights=[15, 68, 17])[0]
        masa = rnd.randint(0, 20)
        gaji = 5.5 + 0.45 * masa + divisi_bonus[divisi] + didik_bonus[didik]
        gaji = round(gaji + rnd.uniform(-1.0, 1.0), 1)
        baris.append([f"K-{i + 1:03d}", divisi, masa, gaji,
                      rnd.randint(0, 30), didik])
    return tulis("gaji_karyawan.csv",
                 ["id", "divisi", "masa_kerja_tahun", "gaji_juta", "lembur_jam",
                  "pendidikan"], baris)


# ---------------------------------------------------------------- 9. kalori
def gen_kalori_makanan():
    """Angka perkiraan utk latihan (bukan acuan gizi resmi)."""
    masakan = [
        ("Nasi Goreng", 520, 12, 18, 62), ("Mie Goreng", 480, 10, 16, 60),
        ("Mie Ayam", 430, 14, 12, 58), ("Bakso", 350, 16, 12, 42),
        ("Soto Ayam", 300, 18, 9, 32), ("Rendang", 470, 24, 34, 12),
        ("Sate Ayam", 380, 26, 20, 18), ("Gado-Gado", 350, 12, 18, 34),
        ("Ayam Geprek", 560, 28, 30, 40), ("Nasi Padang", 640, 26, 28, 70),
        ("Nasi Uduk", 500, 11, 16, 72), ("Bubur Ayam", 370, 15, 10, 52),
        ("Ketoprak", 400, 13, 15, 52), ("Nasi Kuning", 460, 10, 12, 76),
        ("Rawon", 420, 22, 26, 20), ("Gudeg", 480, 12, 14, 74),
        ("Pecel Lele", 450, 24, 26, 30), ("Martabak Manis", 640, 12, 24, 88),
        ("Martabak Telur", 550, 20, 32, 40), ("Pisang Goreng", 240, 3, 12, 32),
        ("Tahu Isi", 180, 6, 10, 16), ("Risoles", 200, 5, 11, 20),
        ("Batagor", 320, 12, 16, 30), ("Siomay", 300, 11, 14, 30),
        ("Pempek", 340, 13, 13, 40), ("Kerak Telor", 400, 14, 20, 38),
        ("Nasi Kari", 520, 15, 18, 68), ("Bakmi Jawa", 470, 13, 15, 60),
        ("Kupat Tahu", 330, 10, 12, 42), ("Lontong Sayur", 420, 11, 16, 56),
        ("Sate Padang", 400, 22, 18, 34), ("Ayam Bakar", 480, 30, 28, 20),
        ("Ikan Bakar", 420, 32, 22, 10), ("Pepes Ikan", 300, 28, 14, 8),
        ("Capcay", 220, 8, 10, 22), ("Sayur Asem", 120, 4, 5, 16),
        ("Tempe Orek", 260, 12, 14, 20), ("Perkedel", 190, 5, 11, 18),
        ("Telur Balado", 300, 15, 20, 10), ("Kue Lapis", 190, 2, 6, 32),
    ]
    porsi = [("1 porsi", 1.0), ("1 porsi besar", 1.6), ("100 gram", 0.55)]
    baris = []
    for nama, kal, pro, lem, kar in masakan:
        for label, faktor in porsi:
            baris.append([nama, label, int(round(kal * faktor)),
                          round(pro * faktor, 1), round(lem * faktor, 1),
                          round(kar * faktor, 1)])
    return tulis("kalori_makanan.csv",
                 ["nama_makanan", "porsi", "kalori", "protein_g", "lemak_g",
                  "karbohidrat_g"], baris)


# ---------------------------------------------------------------- 10. film
def gen_film_nonton():
    rnd = random.Random(1010)
    awal = ["Misteri", "Petualangan", "Kisah", "Legenda", "Rahasia", "Perjalanan",
            "Badai", "Cahaya", "Bayangan", "Pulang", "Senja", "Fajar", "Jejak",
            "Suara", "Peta", "Menara", "Ombak", "Hujan", "Bintang", "Api"]
    akhir = ["di Jakarta", "di Bali", "di Laut Selatan", "dari Kampung Halaman",
             "di Kota Tua", "di Gunung Merapi", "di Pulau Terpencil", "Sang Juara",
             "Terakhir", "Pertama", "di Stasiun Tua", "di Pasar Subuh",
             "di Danau Toba", "di Bawah Tanah", "di Menara Air", "Tanpa Nama",
             "di Hari Kemerdekaan", "di Ujung Tahun"]
    genre = ["Laga", "Drama", "Komedi", "Horor", "Animasi", "Petualangan", "Misteri"]
    judul_terpakai = set()
    baris = []
    percobaan = 0
    # 20 x 18 = 360 kombinasi > 300 yang diminta; batas percobaan = pengaman
    while len(baris) < 300 and percobaan < 20000:
        percobaan += 1
        judul = f"{rnd.choice(awal)} {rnd.choice(akhir)}"
        if judul in judul_terpakai:
            continue
        judul_terpakai.add(judul)
        baris.append([judul, rnd.randint(2005, 2026), rnd.choice(genre),
                      round(rnd.uniform(5.0, 9.9), 1),
                      round(rnd.uniform(0.1, 12.0), 1)])
    baris.sort(key=lambda r: r[1])
    return tulis("film_nonton.csv",
                 ["judul", "tahun", "genre", "rating", "jumlah_penonton_juta"], baris)


# ---------------------------------------------------------------- mirror
def sinkron_mirror():
    """Samakan isi kedua folder: notebook baca /datasets, soal baca /soaldata."""
    os.makedirs(SOAL_DIR, exist_ok=True)
    os.makedirs(NOTEBOOK_DIR, exist_ok=True)
    nama_semua = set()
    for folder in (NOTEBOOK_DIR, SOAL_DIR):
        nama_semua |= {n for n in os.listdir(folder) if n.endswith(".csv")}
    baru = 0
    for nama in sorted(nama_semua):
        a = os.path.join(NOTEBOOK_DIR, nama)
        b = os.path.join(SOAL_DIR, nama)
        if not os.path.exists(a):
            shutil.copy2(b, a)
            print(f"  mirror soal→notebook : {nama}")
            baru += 1
        elif not os.path.exists(b):
            shutil.copy2(a, b)
            print(f"  mirror notebook→soal : {nama}")
            baru += 1
        else:
            with open(a, "rb") as fa, open(b, "rb") as fb:
                sama = fa.read() == fb.read()
            if not sama:
                shutil.copy2(a, b)
                print(f"  sync (beda isi)      : {nama}")
                baru += 1
    print(f"  mirror: {baru} file diselaraskan; {len(nama_semua)} nama file unik di dua folder")


def main():
    os.makedirs(NOTEBOOK_DIR, exist_ok=True)
    os.makedirs(SOAL_DIR, exist_ok=True)
    print("== Generator dataset latihan QuantLab ==")
    gen_harga_saham()
    gen_transaksi_toko()
    gen_pelanggan_telco()
    gen_nilai_siswa()
    gen_cuaca_jakarta()
    gen_log_server()
    gen_transaksi_umkm()
    gen_gaji_karyawan()
    gen_kalori_makanan()
    gen_film_nonton()
    print("== Mirror dua folder ==")
    sinkron_mirror()
    print("Selesai.")


if __name__ == "__main__":
    main()
