#!/usr/bin/env python3
"""Smoke test QuantLab — QA cepat setelah perubahan apa pun.

Jalankan: cd ~/quantlab && .venv/bin/python scripts/smoke_test.py
Cakupan: struktur kurikulum, sweep rute, alur skenario + pelajaran,
soal coding + playground (sandbox), pencarian, header keamanan, rate limit.
Butuh bubblewrap (judge) & DeepSeek key untuk tes mentor (SMOKE_AI=1).
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import curriculum  # noqa: E402
import app as A  # noqa: E402

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
    t0 = time.time()

    # 1. Kurikulum: parse & id unik
    ids = []
    for b in curriculum.get_babs() or []:
        ids += [s["id"] for s in b.get("skenario", [])]
        ids += [q["id"] for q in b.get("soal", [])]
        ids += [l["id"] for l in b.get("pelajaran", [])]
    check("kurikulum 33 bab", len(curriculum.get_babs() or []) == 33)
    check("id unik", len(ids) == len(set(ids)), f"({len(ids)} vs {len(set(ids))})")

    # 2. User baru
    c.get("/logout")
    html = c.get("/register").get_data(as_text=True)
    tok = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html).group(1)
    u = f"smoke{int(time.time()) % 100000}"
    r = c.post("/register", data={"_csrf": tok, "username": u, "password": "smoke123"})
    check("register", r.status_code in (200, 302))

    # 3. Sweep rute utama
    paths = ["/", "/peta", "/mentor", "/playground", "/lab", "/jurnal", "/ulas",
             "/analitik", "/leaderboard", "/badges", "/profil", "/cari?q=funding",
             "/notebook", "/notebook/datasets",
             "/bab/1", "/bab/11", "/bab/27", "/skenario/s11-1",
             "/skenario/s11-1/hasil", "/soal/p25-1", "/ujian/math", "/sertifikat/math"]
    bad = []
    for p in paths:
        rr = c.get(p)
        if rr.status_code >= 500:
            bad.append((p, rr.status_code))
    check("sweep rute", not bad, str(bad))

    # 4. Pencarian menemukan hasil
    html = c.get("/cari?q=funding").get_data(as_text=True)
    check("cari funding ada hasil", "Funding Rate Carry" in html or "hasil untuk" in html)

    # 5. Alur skenario: jawab + hasil + pelajaran
    html = c.get("/skenario/s11-2").get_data(as_text=True)
    tok = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    check("skenario s11-2 form", tok is not None)
    if tok:
        r = c.post("/skenario/s11-2", data={"_csrf": tok.group(1), "choice": "0"})
        check("jawab skenario redirect", r.status_code in (200, 302))
        html = c.get("/skenario/s11-2/hasil").get_data(as_text=True)
        check("hasil skenario", "Keputusan" in html)
    lid = curriculum.get_babs()[10]["pelajaran"][0]["id"]
    r = c.post(f"/api/lesson/{lid}/done", data={"_csrf": tok.group(1) if tok else ""},
               headers={"X-CSRF-Token": tok.group(1) if tok else ""})
    check("pelajaran +XP", r.status_code == 200 and b'"ok":true' in r.data)

    # 6. Soal coding (sandbox) + rate limit
    q = curriculum.get_soal("p4-1")
    html = c.get("/soal/p4-1").get_data(as_text=True)
    tok = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    code = "print(1+1)"
    ok429 = False
    if tok:
        for i in range(8):  # 8x cepat -> salah satunya harus 429 (6/menit)
            r = c.post("/soal/p4-1", data={"_csrf": tok.group(1), "code": code})
            if r.status_code == 429:
                ok429 = True
                break
    check("rate limit soal (429)", ok429)

    # 7. Playground run
    html = c.get("/playground").get_data(as_text=True)
    tok = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    if tok:
        r = c.post("/playground", data={"_csrf": tok.group(1), "mode": "run",
                                        "code": "print(21*2)", "stdin": ""})
        check("playground run", r.status_code == 200 and "42" in r.get_data(as_text=True))
    else:
        check("playground run", False, "csrf tidak ada")

    # 8. Header keamanan
    hdrs = c.get("/login").headers
    check("security headers", hdrs.get("X-Content-Type-Options") == "nosniff"
          and hdrs.get("X-Frame-Options") == "DENY")

    # 9. Mentor (hanya jika SMOKE_AI=1 — butuh API eksternal)
    if os.environ.get("SMOKE_AI") == "1":
        html = c.get("/mentor").get_data(as_text=True)
        tok = re.search(r'id="csrf" value="([^"]+)"', html)
        if tok:
            r = c.post("/mentor/send", data={"_csrf": tok.group(1), "msg": "Balas: ok",
                                             "bab": "", "sid": ""})
            check("mentor send", r.status_code == 200 and b'"reply"' in r.data,
                  f"({r.status_code})")

    # Bersihkan user smoke
    import db  # noqa: E402
    conn = db.get_conn()
    row = conn.execute("SELECT id FROM users WHERE username=?", (u,)).fetchone()
    if row:
        uid = row["id"]
        for t in ("solves", "lesson_done", "soal_solved", "journal_entries",
                  "exam_pass", "review_schedule", "mentor_messages", "notebooks"):
            conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()

    print(f"\n{CHECKS - len(FAILS)}/{CHECKS} lolos dalam {time.time()-t0:.1f}s")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
