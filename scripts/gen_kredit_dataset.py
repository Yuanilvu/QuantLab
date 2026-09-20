#!/usr/bin/env python3
"""Generator dataset latihan Data Science QuantLab: kredit UMKM (sintetis, realistis).

Output (tulis ke data/notebook_datasets/ DAN data/soal/):
  - kredit_umkm.csv          → dataset KOTOR (untuk latihan cleaning & EDA)
  - kredit_umkm_bersih.csv   → versi bersih (siap ML)
  - kredit_umkm_uji.csv      → 150 baris tanpa label (latihan prediksi/submission)

Deterministik (seed tetap). Data SINTETIS untuk latihan, bukan data nyata.
Karakteristik (terverifikasi): status "Macet" ± 24-26% dari baris,
model logistik CV-5 ≈ 0.82 vs baseline ± 0.76 — sinyal ada tapi tidak sempurna
(realistis untuk mengajarkan evaluasi model).
"""
import os

import numpy as np
import pandas as pd

REPO = "/home/yuan/quantlab"
DST_NB = os.path.join(REPO, "data", "notebook_datasets")
DST_SOAL = os.path.join(REPO, "data", "soal")
os.makedirs(DST_NB, exist_ok=True)


def base_frame(seed, n):
    rng = np.random.default_rng(seed)
    omzet = rng.lognormal(3.3, .55, n)                 # ~27 juta rupiah
    lama = rng.integers(6, 180, n).astype(float)       # bulan
    karyawan = rng.integers(1, 9, n).astype(float)
    pinjaman = omzet * rng.uniform(0.25, 1.05, n)
    telat = rng.integers(0, 5, n).astype(float)
    telat += rng.random(n) < 0.2                        # sebagian lebih tinggi
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
    return df, rng


# ---------- 1. Data asli (bersih) ----------
df, rng = base_frame(20260920, 620)
clean = df.copy()
clean["tanggal_pengajuan"] = clean["tanggal_pengajuan"].dt.strftime("%Y-%m-%d")

# ---------- 2. Versi kotor ----------
dirty = clean.copy()
n = len(dirty)

d = pd.to_datetime(dirty["tanggal_pengajuan"])
pick = rng.random(n) < 0.30
dirty.loc[pick, "tanggal_pengajuan"] = d[pick].dt.strftime("%d/%m/%Y")
pick2 = rng.random(n) < 0.15
dirty.loc[pick2, "tanggal_pengajuan"] = d[pick2].dt.strftime("%b %d, %Y")


def mess_text(series, mapping, rng, p=0.45):
    s = series.astype(object).copy()
    for i in range(len(s)):
        if rng.random() < p:
            s.iloc[i] = mapping[s.iloc[i]][int(rng.integers(0, len(mapping[s.iloc[i]])))]
    return s


kota_map = {"Jakarta": ["jakarta", "JKT", " Jakarta ", "jkt"],
            "Bandung": ["bandung", "BDG "],
            "Surabaya": ["surabaya", "SBY"],
            "Medan": ["medan ", "MDN"],
            "Makassar": ["makassar", "MKS"],
            "Yogyakarta": ["yogyakarta", "Jogja", "YOG "]}
sektor_map = {"Kuliner": ["kuliner", "KULINER"], "Fashion": ["fashion", "fashion "],
              "Jasa": ["jasa", "JASA"], "Retail": ["retail ", "Retail"],
              "Pertanian": ["pertanian", "PERTANIAN"], "Kerajinan": ["kerajinan ", "kerajinan"]}
npwp_map = {"Ya": ["ya", "Y", "1", "y"], "Tidak": ["tidak", "T", "0", "n", "N"]}
dirty["kota"] = mess_text(dirty["kota"], kota_map, rng)
dirty["sektor"] = mess_text(dirty["sektor"], sektor_map, rng)
dirty["punya_npwp"] = mess_text(dirty["punya_npwp"], npwp_map, rng, p=0.4)

for col, p in [("omzet_bulanan_juta", .08), ("lama_usaha_bulan", .06),
               ("jumlah_karyawan", .05), ("riwayat_telat_12m", .06),
               ("skor_kredit", .09), ("punya_npwp", .04),
               ("sektor", .05), ("kota", .05)]:
    dirty.loc[rng.random(n) < p, col] = np.nan

dirty.loc[5, "omzet_bulanan_juta"] = 9000.0
dirty.loc[17, "omzet_bulanan_juta"] = -50.0
dirty.loc[42, "lama_usaha_bulan"] = 999.0
dirty.loc[88, "riwayat_telat_12m"] = 99.0
dirty.loc[133, "pinjaman_diajukan_juta"] = -120.0
dirty.loc[210, "jumlah_karyawan"] = 250.0

dups = dirty.sample(16, random_state=7)
dirty = pd.concat([dirty, dups]).sort_values("id_pengajuan").reset_index(drop=True)

# ---------- 3. Uji (tanpa label) ----------
uji, _ = base_frame(777, 150)
uji = uji.drop(columns=["status"])
uji["tanggal_pengajuan"] = uji["tanggal_pengajuan"].dt.strftime("%Y-%m-%d")

# ---------- Tulis ----------
paths = {
    "kredit_umkm.csv": dirty,
    "kredit_umkm_bersih.csv": clean,
    "kredit_umkm_uji.csv": uji,
}
for name, frame in paths.items():
    for dstdir in (DST_NB, DST_SOAL):
        frame.to_csv(os.path.join(dstdir, name), index=False)
    print(f"{name}: {frame.shape[0]} baris x {frame.shape[1]} kolom")

# ---------- Verifikasi + angka acuan ----------
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import cross_val_score, train_test_split  # noqa: E402

d1 = pd.read_csv(os.path.join(DST_NB, "kredit_umkm.csv"))
d2 = pd.read_csv(os.path.join(DST_NB, "kredit_umkm_bersih.csv"))
d3 = pd.read_csv(os.path.join(DST_NB, "kredit_umkm_uji.csv"))
assert d1.shape[0] == 636 and d2.shape[0] == 620 and d3.shape[0] == 150
assert d2.isna().sum().sum() == 0 and d3.isna().sum().sum() == 0
assert "status" not in d3.columns

X = d2[["omzet_bulanan_juta", "lama_usaha_bulan", "pinjaman_diajukan_juta",
        "riwayat_telat_12m", "skor_kredit"]]
y = (d2["status"] == "Macet").astype(int)
cv_acc = cross_val_score(LogisticRegression(max_iter=400), X, y, cv=5).mean()
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.25, random_state=1)
test_acc = LogisticRegression(max_iter=400).fit(Xtr, ytr).score(Xte, yte)
rate = y.mean()
base = max(rate, 1 - rate)

print(f"missing di kotor: {int(d1.isna().sum().sum())} sel · "
      f"duplikat: {int(d1.duplicated().sum())} baris")
print(f"ANGKA ACUAN → macet {rate:.1%} | baseline {base:.3f} | "
      f"logreg CV-5 {cv_acc:.3f} | logreg test(25%) {test_acc:.3f}")
assert 0.20 <= rate <= 0.30, f"rate aneh: {rate}"
assert cv_acc >= base + 0.03, f"model tidak informatif: {cv_acc} vs {base}"
print("OK — dataset konsisten & informatif")
