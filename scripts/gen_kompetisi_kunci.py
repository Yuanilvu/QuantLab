#!/usr/bin/env python3
"""Bangun KUNCI penilaian Kompetisi Simulasi (Lomba Kredit UMKM).

Label uji direkonstruksi DETERMINISTIK dari generator yang sama (seed 777, n=150)
— fitur hasil rekonstruksi diverifikasi IDENTIK dengan kredit_umkm_uji.csv yang
dipakai user; kalau tidak cocok, script BERHENTI (tidak menulis kunci).

Output: data/kompetisi/kredit_umkm_uji_kunci.csv  (id_pengajuan, status)
        + cetak angka acuan (baseline mayoritas & skor model contoh).

Jalankan: cd ~/quantlab && .venv/bin/python scripts/gen_kompetisi_kunci.py
"""
import os

import numpy as np
import pandas as pd

REPO = "/home/yuan/quantlab"
NB_DIR = os.path.join(REPO, "data", "notebook_datasets")
KUNCI_DIR = os.path.join(REPO, "data", "kompetisi")


def base_frame(seed, n):
    """SALINAN PERSIS dari gen_kredit_dataset.py (jangan diubah tanpa sync)."""
    rng = np.random.default_rng(seed)
    omzet = rng.lognormal(3.3, .55, n)
    lama = rng.integers(6, 180, n).astype(float)
    karyawan = rng.integers(1, 9, n).astype(float)
    pinjaman = omzet * rng.uniform(0.25, 1.05, n)
    telat = rng.integers(0, 5, n).astype(float)
    telat += rng.random(n) < 0.2
    npwp_bad = (rng.random(n) < 0.35).astype(float)
    ratio = pinjaman / omzet
    skor = np.clip(620 - 45 * telat + 25 * (1 - npwp_bad)
                   + rng.normal(0, 55, n), 300, 850).round(0)
    risk = (3.6 * ratio + 0.65 * telat - 0.011 * lama + 1.0 * npwp_bad
            + rng.normal(0, 0.62, n))
    risk = (risk - risk.mean()) / risk.std()
    p_macet = 1 / (1 + np.exp(-(2.8 * risk - 2.2)))
    macet = rng.random(n) < p_macet
    sektor = rng.choice(["Kuliner", "Fashion", "Jasa", "Retail", "Pertanian", "Kerajinan"], n)
    kota = rng.choice(["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar", "Yogyakarta"],
                      n, p=[.30, .18, .18, .14, .10, .10])
    df = pd.DataFrame({
        "id_pengajuan": [f"K-{i+1:04d}" for i in range(n)],
        "tanggal_pengajuan": pd.to_datetime("2024-06-01")
        + pd.to_timedelta(rng.integers(0, 740, n), unit="D"),
        "kota": kota, "sektor": sektor,
        "omzet_bulanan_juta": omzet.round(1),
        "lama_usaha_bulan": lama,
        "jumlah_karyawan": karyawan,
        "pinjaman_diajukan_juta": pinjaman.round(1),
        "riwayat_telat_12m": telat,
        "punya_npwp": np.where(npwp_bad > 0, "Tidak", "Ya"),
        "skor_kredit": skor,
        "status": np.where(macet, "Macet", "Lancar"),
    })
    return df


# 1. Rekonstruksi + verifikasi fitur vs file yang dipakai user
uji_full = base_frame(777, 150)
uji_full = uji_full.copy()
uji_full["tanggal_pengajuan"] = uji_full["tanggal_pengajuan"].dt.strftime("%Y-%m-%d")
stored = pd.read_csv(os.path.join(NB_DIR, "kredit_umkm_uji.csv"))

feat_re = uji_full.drop(columns=["status"]).reset_index(drop=True)
feat_st = stored.reset_index(drop=True)
assert list(feat_re.columns) == list(feat_st.columns), (
    f"Kolom beda!\n{list(feat_re.columns)}\n{list(feat_st.columns)}")
for col in feat_re.columns:
    a, b = feat_re[col].astype(str), feat_st[col].astype(str)
    if not a.equals(b):
        bad = int((a != b).sum())
        raise SystemExit(f"FITUR TIDAK COCOK di kolom '{col}' ({bad} baris beda) — batal menulis kunci.")
print("✓ 11 kolom fitur identik dengan kredit_umkm_uji.csv (150 baris) — label valid")

# 2. Tulis kunci
os.makedirs(KUNCI_DIR, exist_ok=True)
kunci = uji_full[["id_pengajuan", "status"]]
kunci.to_csv(os.path.join(KUNCI_DIR, "kredit_umkm_uji_kunci.csv"), index=False)
print(f"✓ kunci ditulis: {kunci.shape[0]} baris → data/kompetisi/kredit_umkm_uji_kunci.csv")

# 3. Angka acuan
rate = (kunci["status"] == "Macet").mean()
mode_acc = max(rate, 1 - rate)
print(f"→ porsi Macet: {rate:.1%} | tebakan-mayoritas: {mode_acc:.3f}")

from sklearn.linear_model import LogisticRegression  # noqa: E402

bersih = pd.read_csv(os.path.join(NB_DIR, "kredit_umkm_bersih.csv"))
bersih["rasio_pinjaman"] = bersih["pinjaman_diajukan_juta"] / bersih["omzet_bulanan_juta"]
feat = ["omzet_bulanan_juta", "lama_usaha_bulan", "pinjaman_diajukan_juta",
        "riwayat_telat_12m", "skor_kredit", "rasio_pinjaman"]
X = bersih[feat]
y = (bersih["status"] == "Macet").astype(int)
model = LogisticRegression(max_iter=400).fit(X, y)

uji2 = uji_full.copy()
uji2["rasio_pinjaman"] = uji2["pinjaman_diajukan_juta"] / uji2["omzet_bulanan_juta"]
pred = model.predict(uji2[feat])
acc_model = float((pred == (uji_full["status"] == "Macet").astype(int)).mean())
print(f"→ skor model contoh (logreg ala Playbook) di uji: {acc_model:.3f}")

print("SELESAI.")
