#!/usr/bin/env python3
"""Tes fitur Materi Bootcamp (/data-science/materi) — QA mandiri.

Jalankan: cd ~/quantlab && .venv/bin/python scripts/test_materi.py
Cakupan: katalog 200 + konten, kartu di hub, unduh PDF (magic bytes),
Range video (206), traversal & slug palsu (404), wajib login (302).
"""
import os
import re
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as A  # noqa: E402
import materi  # noqa: E402

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

    # 1. Daftar + login user sementara
    html = c.get("/register").get_data(as_text=True)
    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    check("halaman register punya csrf", m is not None)
    u = f"matmateri{int(time.time()) % 100000}"
    if m:
        r = c.post("/register", data={"_csrf": m.group(1), "username": u, "password": "materi123"})
        check("register", r.status_code in (200, 302), str(r.status_code))
    html = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    if m:
        c.post("/login", data={"_csrf": m.group(1), "username": u, "password": "materi123"})

    # 2. Katalog
    r = c.get("/data-science/materi")
    check("GET /data-science/materi = 200", r.status_code == 200, str(r.status_code))
    h = r.get_data(as_text=True)
    check("ada bagian Rakamin", "Rakamin" in h)
    check("ada bagian Pacmann", "Pacmann" in h)
    check("ada berkas Rakamin (Business Fundamental.pdf)", "Business Fundamental.pdf" in h)
    check("ada video Pacmann (.mp4)", ".mp4" in h)

    h2 = c.get("/data-science").get_data(as_text=True)
    check("hub DS punya kartu Materi Bootcamp", "Materi Bootcamp" in h2)

    # 3. Unduh nyata: PDF + Range video
    root_r = materi.BOOTCAMP[0]["root"]
    root_p = materi.BOOTCAMP[1]["root"]
    pdf = next((p for p in root_r.rglob("*.pdf")), None)
    mp4 = next((p for p in root_p.rglob("*.mp4")), None)
    check("ada pdf contoh di disk", pdf is not None)
    check("ada mp4 contoh di disk", mp4 is not None)

    if pdf:
        rel = quote(pdf.relative_to(root_r).as_posix())
        r = c.get(f"/data-science/materi/rakamin/{rel}")
        check("unduh pdf 200", r.status_code == 200, str(r.status_code))
        check("pdf mimetype", r.mimetype == "application/pdf", r.mimetype)
        check("pdf magic bytes %PDF", r.data[:4] == b"%PDF")
    if mp4:
        rel = quote(mp4.relative_to(root_p).as_posix())
        r = c.get(f"/data-science/materi/pacmann/{rel}", headers={"Range": "bytes=0-99"})
        check("video Range → 206", r.status_code == 206, str(r.status_code))
        check("video 100 byte", len(r.data) == 100, str(len(r.data)))

    # 4. Keamanan: traversal + slug palsu
    r = c.get("/data-science/materi/rakamin/..%2F..%2Fetc%2Fpasswd")
    check("traversal %2F → 404/400", r.status_code in (400, 404), str(r.status_code))
    r = c.get("/data-science/materi/rakamin/%2e%2e/%2e%2e/etc/passwd")
    check("traversal %2e → 404/400", r.status_code in (400, 404), str(r.status_code))
    r = c.get("/data-science/materi/ngawur/x.pdf")
    check("slug palsu → 404", r.status_code == 404, str(r.status_code))
    r = c.get("/data-science/materi/rakamin/tidak-ada.pdf")
    check("berkas tak ada → 404", r.status_code == 404, str(r.status_code))

    # 5. Wajib login
    c2 = A.app.test_client()
    r = c2.get("/data-science/materi")
    check("tanpa login → redirect", r.status_code in (301, 302), str(r.status_code))

    print(f"\n{'=' * 42}")
    if FAILS:
        print(f"❌ {CHECKS - len(FAILS)}/{CHECKS} lolos · FAIL: {FAILS}")
        return 1
    print(f"✅ SEMUA LOLOS: {CHECKS}/{CHECKS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
