#!/usr/bin/env python3
"""Tes fitur Rangkuman Kelas (/data-science/kelas) — QA mandiri.

Jalankan: cd ~/quantlab && .venv/bin/python scripts/test_kelas.py
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as A  # noqa: E402
import kelas as K  # noqa: E402

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
    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    check("halaman register punya csrf", m is not None)
    u = f"matkelas{int(time.time()) % 100000}"
    if m:
        r = c.post("/register", data={"_csrf": m.group(1), "username": u, "password": "kelas123"})
        check("register user uji", r.status_code in (200, 302), str(r.status_code))
    html = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    if m:
        c.post("/login", data={"_csrf": m.group(1), "username": u, "password": "kelas123"})

    r = c.get("/data-science/kelas")
    check("GET /data-science/kelas = 200", r.status_code == 200, str(r.status_code))
    katalog = K.katalog()
    n_docs = sum(g["n"] for g in katalog)
    print(f"       rangkuman terdaftar saat ini: {n_docs}")
    h = r.get_data(as_text=True)
    check("halaman indeks memuat judul", "Rangkuman Kelas" in h)
    if n_docs:
        sub = None
        for g in katalog:
            for k in g["kursus"]:
                if k["lessons"]:
                    sub = k["lessons"][0]["sub"]
                    break
            if sub:
                break
        r = c.get(f"/data-science/kelas/{sub}")
        check("halaman rangkuman pertama = 200", r.status_code == 200, str(r.status_code))
        h2 = r.get_data(as_text=True)
        item = K.muat(sub)
        check("konten dirender (ada heading)", "<h2" in h2 or "<h3" in h2)
        check("nav prev/next ada", "kelasnav" in h2)
        if item and item.get("sumber"):
            check("link sumber asli ada", "/data-science/materi/" in h2)
            check("nama kursus tampil", item["kursus"][:12] in h2)

    r = c.get("/data-science/kelas/rakamin/tidak-ada-ini")
    check("rangkuman tidak ada -> 404", r.status_code == 404, str(r.status_code))
    r = c.get("/data-science/kelas/..%2f..%2fapp.py")
    check("traversal ditolak (404/400)", r.status_code in (400, 404), str(r.status_code))

    h3 = c.get("/data-science").get_data(as_text=True)
    check("hub DS punya kartu Rangkuman Kelas", "Rangkuman Kelas" in h3)
    h4 = c.get("/data-science/materi").get_data(as_text=True)
    check("materi.html punya tautan ke kelas", "/data-science/kelas" in h4)

    ok = CHECKS - len(FAILS)
    print(f"--- {ok}/{CHECKS} cek lolos ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
