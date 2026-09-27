#!/usr/bin/env python3
"""qa_kelas.py — QA cepat semua rangkuman: frontmatter, ukuran, seksi wajib, ringkasan katalog.

Jalankan: cd ~/quantlab && .venv/bin/python scripts/qa_kelas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kelas as K  # noqa: E402

ok = 0
bad = 0
print(f"{'file':58} {'kata':>6}  seksi")
for grup in K.GRUP:
    for it in K._items(grup):
        p = K.ROOT / (it["sub"] + ".md")
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        ws = len(t.split())
        tl = t.lower()
        seksi = [nm for nm, pola in (("🎯", "## 🎯"), ("glos", "glosarium"), ("latihan", "latihan mandiri"))
                 if pola in tl]
        data = K._baca(p)
        flag = ""
        if not data:
            flag += " FM-GAGAL"
        if ws < 500:
            flag += " KECIL"
        if len(seksi) < 3:
            flag += " SEKSI-KURANG"
        print(f"{it['sub']:58} {ws:6}  {' '.join(seksi)}{flag}")
        if flag:
            bad += 1
        else:
            ok += 1

print(f"--- {ok} ok · {bad} perlu cek ---")
print("katalog terbaca:", sum(g["n"] for g in K.katalog()), "rangkuman")
