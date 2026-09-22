#!/usr/bin/env python3
"""Tes field `panduan` bab DS 28-33 — QuantLab.

Jalankan: cd ~/quantlab && .venv/bin/python scripts/test_panduan.py
Cakupan: tiap bab punya panduan lengkap (intro/teori/praktek/coba),
SEMUA tautan materi bootcamp resolve 200, dan panel tampil di halaman bab.
"""
import os
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as A  # noqa: E402
import curriculum  # noqa: E402

FAILS = []
CHECKS = 0


def check(name, cond, extra=""):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        FAILS.append(name)


def main():
    c = A.app.test_client()
    c.get("/logout")
    html = c.get("/register").get_data(as_text=True)
    import re
    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    u = f"matpanduan{int(time.time()) % 100000}"
    c.post("/register", data={"_csrf": m.group(1), "username": u, "password": "materi123"})

    for n in range(28, 34):
        bab = curriculum.get_bab(n)
        pd = bab.get("panduan") or {}
        check(f"bab{n}: punya panduan", bool(pd))
        check(f"bab{n}: intro+teori(≥3)+praktek(≥3)",
              bool(pd.get("intro")) and len(pd.get("teori") or []) >= 3 and len(pd.get("praktek") or []) >= 3,
              f"teori={len(pd.get('teori') or [])} praktek={len(pd.get('praktek') or [])}")
        check(f"bab{n}: coba ada", bool(pd.get("coba")))

        for it in (pd.get("materi") or []):
            url = f"/data-science/materi/{it['slug']}/{quote(it['path'])}"
            r = c.get(url)
            check(f"bab{n}: berkas '{it['path'][:52]}'", r.status_code == 200,
                  f"→ {r.status_code}")

        h = c.get(f"/bab/{n}").get_data(as_text=True)
        check(f"bab{n}: panel tampil di halaman",
              "Panduan Belajar" in h and "pgmateri" in h and "Praktek terpandu" in h)

    print(f"\n{'=' * 44}")
    if FAILS:
        print(f"❌ {CHECKS - len(FAILS)}/{CHECKS} lolos · FAIL: {FAILS}")
        return 1
    print(f"✅ SEMUA LOLOS: {CHECKS}/{CHECKS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
