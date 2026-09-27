#!/usr/bin/env python3
"""Uji console mini halaman skenario (QuantLab) — HTTP live, tanpa cetak kredensial user asli."""
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:5200"
ts = str(int(time.time()))[-7:]
user = f"qlwm{ts}"
pw = "MiniUji123!"

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(p):
    return op.open(BASE + p).read().decode()


def post(p, d):
    r = op.open(urllib.request.Request(BASE + p, data=urllib.parse.urlencode(d).encode()))
    return r, r.read().decode()


tok = re.search(r'name="_csrf" value="([^"]+)"', get("/register")).group(1)
r, _ = post("/register", {"_csrf": tok, "username": user, "password": pw})
print("register:", r.url)
assert "/login" not in r.url, r.url

html = get("/skenario/s28-1")
tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
checks = []
checks.append(("mini panel ada", 'id="mini"' in html))
checks.append(("prefill kode s28-1", "read_csv" in html and "isna" in html))
checks.append(("mini.js dimuat", "mini.js" in html))
checks.append(("data-csrf terisi", 'data-csrf="' in html and 'data-csrf=""' not in html))
checks.append(("form keputusan utuh", 'name="choice"' in html and "Lihat Hasil Keputusan" in html))
checks.append(("petunjuk utuh", 'id="hintbtn"' in html and 'id="hints"' in html))

kode = """import os
import pandas as pd
base = "/soaldata" if os.path.isdir("/soaldata") else "/home/yuan/quantlab/data/soal"
df = pd.read_csv(base + "/kredit_umkm.csv")
kosong = df.isna().sum().sort_values(ascending=False)
print(kosong.head(3))"""
r, body = post("/api/mini/jalankan", {"_csrf": tok, "code": kode})
res = json.loads(body)
out1 = res.get("stdout") or ""
print("RUN1 status:", res.get("status"), "| ms:", res.get("ms"))
print("stdout:", " | ".join(out1.strip().splitlines()))
checks.append(("hasil berisi omzet 53", "omzet_bulanan_juta" in out1 and "53" in out1))

st = json.loads(get("/api/mini/status"))
print("status kernel:", {k: st.get(k) for k in ("exists", "alive", "busy", "python")})
checks.append(("kernel hidup", bool(st.get("exists")) and bool(st.get("alive"))))

post("/api/mini/jalankan", {"_csrf": tok, "code": "x = 41"})
r, body = post("/api/mini/jalankan", {"_csrf": tok, "code": "print('x+1 =', x + 1)"})
res2 = json.loads(body)
checks.append(("state nyambung antar run", "x+1 = 42" in (res2.get("stdout") or "")))
r, body = post("/api/mini/jalankan", {"_csrf": tok, "code": "print('baris df =', len(df))"})
print("df kebaca:", (json.loads(body).get("stdout") or "").strip())

try:
    post("/api/mini/jalankan", {"code": "print(1)"})
    checks.append(("csrf wajib (400)", False))
except urllib.error.HTTPError as e:
    checks.append(("csrf wajib (400)", e.code == 400))

h2 = get("/skenario/s11-1")
checks.append(("s11-1 mini ada", 'id="mini"' in h2))

ok = sum(1 for _, v in checks if v)
print(f"--- {ok}/{len(checks)} cek ---")
for n, v in checks:
    print(("  ok  " if v else "  FAIL") + " " + n)
json.dump({"user": user}, open("/tmp/uji_mini_user.json", "w"))
sys.exit(0 if ok == len(checks) else 1)
