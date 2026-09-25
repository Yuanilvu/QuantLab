"""QuantLab — Belajar Quant Trading lewat Skenario.

Flask app: auth (CSRF + anti brute-force DB-backed), kurikulum YAML,
XP/streak/badges, leaderboard, notebook ala Kaggle, fitur Data Science.
"""
import csv
import gzip
import json
import math
import os
import random
import re
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import (
    Flask, abort, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash

import curriculum
import db
import chartgen
import judge
import materi as matlib
import notebook as nblib

# ── Output contoh kode pelajaran (dihitung sekali per proses, sandbox) ─────
_KODE_OUT_CACHE = {}


def lesson_kode_output(kode: str) -> str | None:
    """Output blok `kode:` pelajaran via judge sandbox (bubblewrap).

    None kalau blok tidak bisa dijalankan bersih (input(), demo error,
    timeout) atau stdout kosong — panel Output tidak ditampilkan. Hasil
    di-cache per proses (kunci = isi kode); miss = None juga di-cache agar
    blok bermasalah tidak dicoba-coba tiap render halaman.
    """
    if not kode:
        return None
    if kode in _KODE_OUT_CACHE:
        return _KODE_OUT_CACHE[kode]
    if re.search(r"\binput\s*\(", kode):  # blok interaktif → skip
        _KODE_OUT_CACHE[kode] = None
        return None
    try:
        r = judge.run_code(kode, stdin="")
    except Exception:
        _KODE_OUT_CACHE[kode] = None
        return None
    out = None
    if r.get("ok"):
        out = (r.get("stdout") or "").rstrip("\n")
        if not out:
            out = None
    _KODE_OUT_CACHE[kode] = out
    return out

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", secrets.token_hex(32)
)
app.config["MAX_FORM_MEMORY_SIZE"] = 2_000_000  # sel notebook + output bisa besar
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # notebook + upload CSV (maks 5 MB)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_NAME"] = "ql_session"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=395)  # login awet — jangan login mulu

# gzip: halaman materi/kurikulum besar → ±6x lebih kecil (penting lewat funnel).
from flask_compress import Compress  # noqa: E402
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400  # static: cukup sekali unduh
app.config["COMPRESS_MIMETYPES"] = [
    "text/html", "text/css", "text/plain", "text/xml", "application/json",
    "application/javascript", "application/xml", "image/svg+xml",
]
app.config["COMPRESS_ALGORITHM_STREAMING"] = ["gzip", "deflate"]  # static (stream) ikut gzip
Compress(app)

db.init_db()

LESSON_XP = db.LESSON_XP
CHALLENGE_BONUS = 10


# ---------- Tantangan Harian (deterministik per tanggal WIB) ----------

def daily_challenge_id():
    all_ids = [s["id"] for b in curriculum.get_babs() for s in (b.get("skenario") or [])]
    rng = random.Random(datetime.now(db.WIB).date().toordinal())
    return rng.choice(all_ids)


def challenge_scenario():
    cid = daily_challenge_id()
    entry = curriculum.get_scenario(cid)
    return entry, cid


# ---------- Peta Kemampuan (radar) ----------

def track_progress(solved, soal_solved_set):
    """Progress per track: {code, name, emoji, desc, babs, total, done, pct}."""
    out = []
    for t in curriculum.get_tracks():
        total = done = 0
        for b in t["babs"]:
            ids = [s["id"] for s in (b.get("skenario") or [])]
            qids = [q["id"] for q in (b.get("soal") or [])]
            total += len(ids) + len(qids)
            done += sum(1 for i in ids if i in solved)
            done += sum(1 for i in qids if i in soal_solved_set)
        out.append({**t, "total": total, "done": done,
                    "pct": round(done / total * 100) if total else 0})
    return out


def next_unsolved(solved, soal_solved_set):
    """Skenario/soal pertama yang belum dikerjakan, urutan kurikulum."""
    for t in curriculum.get_tracks():
        for b in t["babs"]:
            for s in (b.get("skenario") or []):
                if s["id"] not in solved:
                    return {"kind": "scenario", "id": s["id"],
                            "judul": s["judul"], "emoji": s["emoji"],
                            "bab": b["bab"], "track": t["name"]}
            for q in (b.get("soal") or []):
                if q["id"] not in soal_solved_set:
                    return {"kind": "soal", "id": q["id"],
                            "judul": q["judul"], "emoji": q["emoji"],
                            "bab": b["bab"], "track": t["name"]}
    return None

SKILL_GROUPS = [
    ("Carry & Risk", [11, 12]),
    ("Baca Market", [13, 18]),
    ("Evaluasi", [14, 16]),
    ("Volatilitas", [17]),
    ("Portofolio", [19]),
    ("Eksekusi", [15, 20]),
    ("Data & Bot", [22, 23, 24, 25, 26, 27]),
]


def skill_map(solved):
    """Persentase per kelompok kemampuan -> 6 sumbu radar."""
    out = []
    for name, babs in SKILL_GROUPS:
        total = done = 0
        for n in babs:
            b = curriculum.get_bab(n)
            if not b:
                continue
            ids = [s["id"] for s in (b.get("skenario") or [])]
            total += len(ids)
            done += sum(1 for i in ids if i in solved)
        out.append({"name": name, "pct": round(done / total * 100) if total else 0})
    return out


def radar_svg(skills):
    """Radar 6 sumbu sebagai SVG. skills: [{name, pct}]."""
    n = len(skills)
    cx, cy, R = 110, 100, 72
    pts = []
    for i, s in enumerate(skills):
        ang = -90 + i * (360 / n)
        x = cx + R * s["pct"] / 100 * math.cos(math.radians(ang))
        y = cy + R * s["pct"] / 100 * math.sin(math.radians(ang))
        pts.append(f"{x:.1f},{y:.1f}")
    grid = ""
    labels = ""
    for i, s in enumerate(skills):
        ang = -90 + i * (360 / n)
        gx = cx + R * math.cos(math.radians(ang))
        gy = cy + R * math.sin(math.radians(ang))
        grid += f"<line x1='{cx}' y1='{cy}' x2='{gx:.1f}' y2='{gy:.1f}' stroke='#26313d' stroke-width='1'/>"
        lx = cx + (R + 16) * math.cos(math.radians(ang))
        ly = cy + (R + 16) * math.sin(math.radians(ang))
        anchor = "middle"
        if abs(math.cos(math.radians(ang))) < 0.3:
            anchor = "middle"
        elif math.cos(math.radians(ang)) > 0:
            anchor = "start"
        else:
            anchor = "end"
        labels += (f"<text x='{lx:.1f}' y='{ly:.1f}' text-anchor='{anchor}' "
                   f"fill='#8b98a8' font-size='8.5'>{s['name']} {s['pct']}%</text>")
    rings = ""
    for rp in (25, 50, 75, 100):
        rpts = []
        for i in range(n):
            ang = -90 + i * (360 / n)
            rpts.append(f"{cx + R * rp / 100 * math.cos(math.radians(ang)):.1f},{cy + R * rp / 100 * math.sin(math.radians(ang)):.1f}")
        rings += f"<polygon points='{' '.join(rpts)}' fill='none' stroke='#1a232e' stroke-width='1'/>"
    poly = f"<polygon points='{' '.join(pts)}' fill='rgba(34,197,94,0.25)' stroke='#22c55e' stroke-width='2'/>"
    return (f"<svg viewBox='0 0 220 200' class='radar'>{rings}{grid}{poly}{labels}</svg>")


# ---------- Helpers ----------

def _csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def _user():
    uid = session.get("uid")
    if not uid:
        return None
    return db.get_user(uid)


@app.context_processor
def inject_globals():
    user = _user()
    solved = db.solved_ids(user["id"]) if user else set()
    soal_solved = db.get_soal_solved(user["id"]) if user else set()
    if user:
        user = dict(user)  # sqlite3.Row tidak bisa di-assign item
        user["_review_due"] = db.review_count_due(user["id"])
    return {
        "csrf_token": _csrf_token,
        "user": user,
        "solved": solved,
        "soal_solved": soal_solved,
        "stats": curriculum.stats(),
    }


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf")
        sent = request.form.get("_csrf")
        if not token or sent != token:
            abort(400, "CSRF token tidak valid. Muat ulang halaman.")


def login_required(fn):
    def wrap(*args, **kwargs):
        if not session.get("uid"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    wrap.__name__ = fn.__name__
    return wrap


# ---------- Auth ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("uid"):
        return redirect(url_for("index"))
    err = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        # Key lockout = IP + username (funnel memakai IP bersama — jangan
        # biarkan 1 user gagal mengunci semua orang)
        ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
              or request.remote_addr or "?")
        key = f"{ip}|{username}"
        fails = db.login_failures_check(key)
        if fails >= db.LOCK_LIMIT:
            err = "Terlalu banyak percobaan gagal. Coba lagi 5 menit lagi."
        else:
            user = db.verify_login(username,
                                   request.form.get("password", ""))
            if user:
                db.login_failures_reset(key)
                session.clear()  # anti session-fixation
                session.permanent = True
                session["_csrf"] = secrets.token_hex(16)
                session["uid"] = user["id"]
                return redirect(request.args.get("next") or url_for("index"))
            err = "Username atau password salah."
            db.login_failures_incr(key)
    return render_template("login.html", err=err)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("uid"):
        return redirect(url_for("index"))
    err = None
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        ok, msg = db.register_user(u, p)
        if ok:
            session.clear()  # anti session-fixation
            session.permanent = True
            session["_csrf"] = secrets.token_hex(16)
            session["uid"] = db.get_user_by_name(u.strip())["id"]
            return redirect(url_for("index"))
        err = msg
    return render_template("register.html", err=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Halaman utama ----------

@app.route("/")
@login_required
def index():
    user = _user()
    babs = curriculum.get_babs()
    solved = db.solved_ids(user["id"])
    bab_cards = []
    for b in babs:
        scens = b.get("skenario") or []
        done = sum(1 for s in scens if s["id"] in solved)
        bab_cards.append({
            "bab": b["bab"], "judul": b["judul"], "emoji": b["emoji"],
            "deskripsi": b["deskripsi"], "n": len(scens), "done": done,
            "complete": done == len(scens) and len(scens) > 0,
        })
    total = curriculum.total_scenarios()
    skills = skill_map(solved)
    soal_solved_set = db.get_soal_solved(user["id"])
    tracks = track_progress(solved, soal_solved_set)
    ds_t = next((t for t in tracks if t["code"] == "ds"), None)
    ds_lv = ds_level(ds_t["done"], ds_t["total"]) if ds_t else None
    nxt = next_unsolved(solved, soal_solved_set)
    review_n = db.review_count_due(user["id"])
    # Tantangan harian
    centry, cid = challenge_scenario()
    challenge = None
    if cid not in solved:
        challenge = {
            "id": cid,
            "judul": centry["data"]["judul"],
            "emoji": centry["data"]["emoji"],
            "sulit": centry["data"]["sulit"],
            "xp": curriculum.xp_for_scenario(centry["data"]) + CHALLENGE_BONUS,
        }
    return render_template("index.html", bab_cards=bab_cards,
                           total=total, solved_count=len(solved),
                           soal_count=len(soal_solved_set),
                           leader=db.leaderboard(1),
                           radar=radar_svg(skills), challenge=challenge,
                           tracks=tracks, nxt=nxt, review_n=review_n, ds_t=ds_t, ds_lv=ds_lv,
                           notebook_n=db.notebook_count(user["id"]))


@app.route("/peta")
@login_required
def peta():
    user = _user()
    solved = db.solved_ids(user["id"])
    soal_solved_set = db.get_soal_solved(user["id"])
    tracks = track_progress(solved, soal_solved_set)
    return render_template("peta.html", tracks=tracks,
                           solved=solved, soal_solved=soal_solved_set)


@app.route("/sertifikat/<track>")
@login_required
def sertifikat(track):
    user = _user()
    solved = db.solved_ids(user["id"])
    soal_solved_set = db.get_soal_solved(user["id"])
    tracks = track_progress(solved, soal_solved_set)
    t = next((x for x in tracks if x["code"] == track), None)
    if not t:
        abort(404)
    complete = t["total"] > 0 and t["done"] == t["total"]
    return render_template("sertifikat.html", t=t, complete=complete,
                           user=user, tanggal=datetime.now(db.WIB).strftime("%d %B %Y"))


# ---------- Soal coding (HackerRank-style) ----------

SOAL_XP = {"mudah": 25, "sedang": 40, "sulit": 55}

_JUDGE_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "soal")
_SOALDATA_RE = re.compile(r"/soaldata/([\w.\-]+)")
_SOALDATA_INFO = {}  # (nama, mtime) -> {rows, cols, kb}


def _soal_data_files(q):
    """File /soaldata/... yang disinggung soal (cerita/tugas/tes/contoh) + info baris/kolom.

    Dipakai kotak "📂 Data untuk soal ini" di halaman soal supaya user tahu
    PERSIS path yang bisa dibaca dari kodenya.
    """
    teks = json.dumps(q, ensure_ascii=False, default=str)
    nama_unik = []
    for nama in _SOALDATA_RE.findall(teks):
        if nama not in nama_unik:
            nama_unik.append(nama)
    hasil = []
    for nama in nama_unik[:8]:
        info = {"name": nama, "path": f"/soaldata/{nama}", "rows": None, "cols": None}
        path = os.path.join(_JUDGE_DATA, nama)
        if os.path.isfile(path):
            st = os.stat(path)
            kunci = (nama, st.st_mtime)
            if kunci not in _SOALDATA_INFO:
                try:
                    with open(path, newline="", encoding="utf-8") as f:
                        reader = csv.reader(f)
                        header = next(reader, [])
                        baris = sum(1 for _ in reader)
                    _SOALDATA_INFO[kunci] = {"rows": baris, "cols": len(header),
                                             "kb": max(1, st.st_size // 1024)}
                except OSError:
                    _SOALDATA_INFO[kunci] = {}
            info.update(_SOALDATA_INFO.get(kunci, {}))
        hasil.append(info)
    return hasil


@app.route("/soal/<qid>", methods=["GET", "POST"])
@login_required
def soal_page(qid):
    entry = curriculum.get_soal(qid)
    if not entry:
        abort(404)
    user = _user()
    soal_solved_set = db.get_soal_solved(user["id"])
    q = entry["data"]
    data_files = _soal_data_files(q)
    done = qid in soal_solved_set
    result = None
    code = ""
    if request.method == "POST":
        code = request.form.get("code", "")[:8000]
        if done:
            result = {"passed": q["xp"], "total": q["xp"], "already": True,
                      "results": []}
        else:
            if not _heavy_ok(f"soal:{user['id']}"):
                abort(429)
            r = judge.run_tests(code, q["tes"])
            if r["passed"] == r["total"] and r["total"] > 0:
                xp = SOAL_XP.get(q.get("tingkat"), 25)
                inserted, xp_got = db.soal_solved_add(user["id"], qid, xp)
                result = {**r, "ac": True, "xp": xp_got, "already": not inserted}
            else:
                result = {**r, "ac": False}
            if not r["results"] or any(x["error"] for x in r["results"]):
                first_err = next((x["error"] for x in r["results"] if x["error"]), "")
                result["friendly"] = judge.friendly_error(first_err) if first_err else None
    return render_template("soal.html", bab=entry["bab"], q=q, done=done,
                           result=result, code=code, data_files=data_files,
                           render_md=curriculum.render_markdown)


def _panduan_render(pd):
    """Field `panduan` bab DS (materi bootcamp) → siap tampil di bab.html."""
    def _md(items):
        hasil = []
        for it in (items or []):
            h = curriculum.render_markdown(str(it))
            if h.startswith("<p>") and h.endswith("</p>") and h.count("<p>") == 1:
                h = h[3:-4]
            hasil.append(h)
        return hasil
    return {
        "intro": pd.get("intro", ""),
        "materi": pd.get("materi") or [],
        "teori": _md(pd.get("teori")),
        "praktek": _md(pd.get("praktek")),
        "coba": pd.get("coba", ""),
    }


@app.route("/bab/<int:n>")
@login_required
def bab_page(n):
    bab = curriculum.get_bab(n)
    if not bab:
        abort(404)
    user = _user()
    solved = db.solved_ids(user["id"])
    scens = []
    for s in bab.get("skenario") or []:
        scens.append({"data": s, "done": s["id"] in solved})
    lessons = []
    for l in (bab.get("pelajaran") or []):
        l = dict(l)
        l["out"] = lesson_kode_output(l.get("kode"))
        lessons.append(l)
    lessons_done = db.get_lesson_done(user["id"])
    soals = bab.get("soal") or []
    soal_solved_set = db.get_soal_solved(user["id"])
    panduan = _panduan_render(bab.get("panduan")) if bab.get("panduan") else None
    return render_template("bab.html", bab=bab, scens=scens,
                           lessons=lessons, lessons_done=lessons_done,
                           soals=soals, soal_solved=soal_solved_set,
                           nb_ready=nblib.bab_template_key(n) is not None,
                           panduan=panduan,
                           render_md=curriculum.render_markdown)


@app.route("/api/lesson/<lid>/done", methods=["POST"])
@login_required
def lesson_done(lid):
    entry = curriculum.get_lesson_by_id(lid)
    if not entry:
        abort(404)
    inserted, xp = db.lesson_done_add(_user()["id"], lid)
    return {"ok": True, "inserted": inserted, "xp": xp}


# ---------- Skenario ----------

@app.route("/skenario/<sid>")
@login_required
def scenario_page(sid):
    entry = curriculum.get_scenario(sid)
    if not entry:
        abort(404)
    solved = db.solved_ids(_user()["id"])
    if sid in solved:
        return redirect(url_for("scenario_result", sid=sid))
    return render_template("scenario.html", bab=entry["bab"], scen=entry["data"],
                           is_challenge=(sid == daily_challenge_id()),
                           bonus=CHALLENGE_BONUS)


@app.route("/skenario/<sid>", methods=["POST"])
@login_required
def scenario_submit(sid):
    entry = curriculum.get_scenario(sid)
    if not entry:
        abort(404)
    user = _user()
    if sid in db.solved_ids(user["id"]):
        return redirect(url_for("scenario_result", sid=sid))
    try:
        choice = int(request.form.get("choice", -1))
    except ValueError:
        choice = -1
    scen = entry["data"]
    if choice < 0 or choice >= len(scen["pilihan"]):
        return redirect(url_for("scenario_page", sid=sid))
    correct = choice == int(scen["jawaban"])
    xp = curriculum.xp_for_scenario(scen)
    inserted, streak = db.add_solve(user["id"], sid, choice, correct, xp)
    if not inserted:
        return redirect(url_for("scenario_result", sid=sid))
    # Jadwalkan ulasan cerdas (1/3/7 hari) — sekali per skenario
    db.review_schedule_add(user["id"], sid)
    # Bonus tantangan harian: +10 XP kalau benar & skenario ini tantangan hari ini
    bonus = 0
    if correct and sid == daily_challenge_id():
        bonus = CHALLENGE_BONUS
        db.update_xp(user["id"], bonus)
    session["last_xp"] = xp if correct else 0
    session["last_bonus"] = bonus
    return redirect(url_for("scenario_result", sid=sid))


@app.route("/skenario/<sid>/hasil")
@login_required
def scenario_result(sid):
    entry = curriculum.get_scenario(sid)
    if not entry:
        abort(404)
    user = _user()
    solves = db.get_solves(user["id"])
    if sid not in solves:
        return redirect(url_for("scenario_page", sid=sid))
    solve = solves[sid]
    scen = entry["data"]
    outcomes = scen.get("hasil") or []
    # kalau outcomes ada, tandai pilihan user vs optimal
    marked = []
    for i, o in enumerate(outcomes):
        marked.append({**o, "index": i,
                       "is_user": i == solve["choice"],
                       "is_best": i == int(scen["jawaban"])})
    # skenario berikutnya (belum dikerjakan) untuk navigasi lanjut
    bab = entry["bab"]
    next_s = None
    all_ids = [s["id"] for s in (bab.get("skenario") or [])]
    if sid in all_ids:
        for nid in all_ids[all_ids.index(sid) + 1:]:
            if nid not in solves:
                next_s = {"id": nid, "judul": next(
                    (s["judul"] for s in bab["skenario"] if s["id"] == nid), "")}
                break
        if not next_s:
            babs = curriculum.get_babs()
            for b in babs[babs.index(bab) + 1:]:
                for s in (b.get("skenario") or []):
                    if s["id"] not in solves:
                        next_s = {"id": s["id"], "judul": s["judul"]}
                        break
                if next_s:
                    break
    return render_template("result.html", bab=bab, scen=scen, solve=solve,
                           outcomes=marked, has_outcomes=bool(outcomes),
                           next_s=next_s, render_md=curriculum.render_markdown,
                           got_xp=session.pop("last_xp", 0) if solve["correct"] else 0,
                           got_bonus=session.pop("last_bonus", 0) if solve["correct"] else 0,
                           challenge_id=daily_challenge_id())


# ---------- Chart Drill (latihan baca grafik) ----------

CHART_EXAM_N = 10
CHART_EXAM_MENIT = 15
CHART_EXAM_XP = 100


def _chart_rank(selesai, total, lulus):
    """Label jenjang Lab Teknikal."""
    if lulus and selesai >= total:
        return "🏆 Teknisi Tersertifikasi", "khatam semua drill + lulus ujian"
    if lulus:
        return "🎓 Lulus Ujian Teknikal", "terus khatamkan drill-nya"
    if selesai >= 30:
        return "🥇 Mahir", "sedikit lagi khatam"
    if selesai >= 20:
        return "🥈 Senior", "terus jalan"
    if selesai >= 10:
        return "🥉 Menengah", "baru mulai panas"
    if selesai >= 4:
        return "🌱 Pemula+", "awal yang bagus"
    return "🐣 Pemula", "mulai dari modul pertama"


def _chart_exam_habis():
    mulai = session.get("cx_start")
    if not mulai:
        return False
    try:
        lewat = (datetime.now() - datetime.fromisoformat(mulai)).total_seconds()
    except ValueError:
        return False
    return lewat > CHART_EXAM_MENIT * 60


@app.route("/chart")
@login_required
def chart_list():
    user = _user()
    solves = db.get_chart_solves(user["id"])
    semua = []
    for d in curriculum.get_charts():
        s = solves.get(d["id"])
        semua.append({**d, "xp": curriculum.xp_for_chart(d),
                      "selesai": s is not None, "benar": bool(s and s["correct"])})
    groups = curriculum.charts_by_modul(semua)
    for g in groups:
        g["total"] = len(g["drills"])
        g["selesai"] = sum(1 for d in g["drills"] if d["selesai"])
        g["benar"] = sum(1 for d in g["drills"] if d["benar"])
    total = len(semua)
    selesai = sum(1 for d in semua if d["selesai"])
    benar = sum(1 for d in semua if d["benar"])
    hasil_exam = db.get_chart_exam(user["id"])
    rank, rank_desc = _chart_rank(selesai, total, bool(hasil_exam))
    return render_template("charts.html", groups=groups, total=total,
                           selesai=selesai, benar=benar, rank=rank,
                           rank_desc=rank_desc, hasil_exam=hasil_exam,
                           exam_n=CHART_EXAM_N, exam_menit=CHART_EXAM_MENIT,
                           exam_xp=CHART_EXAM_XP)


@app.route("/chart/ujian")
@login_required
def chart_ujian_start():
    user = _user()
    hasil = db.get_chart_exam(user["id"])
    pool_n = sum(1 for d in curriculum.get_charts() if d.get("jenis") != "praktik")
    return render_template("chart_exam_start.html", hasil=hasil,
                           n=CHART_EXAM_N, menit=CHART_EXAM_MENIT,
                           xp=CHART_EXAM_XP, pool_n=pool_n)


@app.route("/chart/ujian/mulai", methods=["POST"])
@login_required
def chart_ujian_mulai():
    pool = [d for d in curriculum.get_charts() if d.get("jenis") != "praktik"]
    ids = [d["id"] for d in random.sample(pool, min(CHART_EXAM_N, len(pool)))]
    session["cx_ids"] = ids
    session["cx_ans"] = {}
    session["cx_start"] = datetime.now().isoformat(timespec="seconds")
    return redirect(url_for("chart_ujian_soal", n=1))


@app.route("/chart/ujian/hasil")
@login_required
def chart_ujian_hasil():
    user = _user()
    ids = session.get("cx_ids") or []
    if not ids:
        return redirect(url_for("chart_ujian_start"))
    ans = session.get("cx_ans") or {}
    review = []
    benar = 0
    for qid in ids:
        d = curriculum.get_chart(qid)
        if not d:
            continue
        c = ans.get(qid, -1)
        ok = c == int(d["jawaban"])
        benar += 1 if ok else 0
        review.append({
            "id": qid, "judul": d["judul"], "emoji": d.get("emoji", ""),
            "benar": ok,
            "pilihanmu": d["pilihan"][c] if 0 <= c < len(d["pilihan"]) else None,
            "kunci": d["pilihan"][int(d["jawaban"])],
        })
    total = len(ids)
    lulus = benar >= max(1, round(total * 0.7))
    xp_got = 0
    sebelumnya = db.get_chart_exam(user["id"])
    hasil = sebelumnya
    if lulus:
        hasil = db.chart_exam_save(user["id"], benar, total)
        if not sebelumnya:
            db.update_xp(user["id"], CHART_EXAM_XP)
            xp_got = CHART_EXAM_XP
    for k in ("cx_ids", "cx_ans", "cx_start"):
        session.pop(k, None)
    return render_template("chart_exam_result.html", review=review, benar=benar,
                           total=total, lulus=lulus, xp=xp_got, hasil=hasil,
                           menit=CHART_EXAM_MENIT)


@app.route("/chart/ujian/<int:n>", methods=["GET", "POST"])
@login_required
def chart_ujian_soal(n):
    ids = session.get("cx_ids") or []
    if not ids:
        return redirect(url_for("chart_ujian_start"))
    total = len(ids)
    if n < 1 or n > total:
        return redirect(url_for("chart_ujian_soal", n=total))
    habis = _chart_exam_habis()
    if request.method == "POST" and not habis:
        ans = session.get("cx_ans") or {}
        try:
            c = int(request.form.get("choice", -1))
        except ValueError:
            c = -1
        if 0 <= c <= 3:
            ans[ids[n - 1]] = c
            session["cx_ans"] = ans
        if n >= total:
            return redirect(url_for("chart_ujian_hasil"))
        return redirect(url_for("chart_ujian_soal", n=n + 1))
    if habis:
        return redirect(url_for("chart_ujian_hasil"))
    drill = curriculum.get_chart(ids[n - 1])
    jawaban_lama = (session.get("cx_ans") or {}).get(ids[n - 1])
    try:
        svg = chartgen.render_drill(drill)
    except (OSError, ValueError):
        svg = None
    return render_template("chart_exam.html", drill=drill, svg=svg, n=n,
                           total=total, mulai=session.get("cx_start"),
                           menit=CHART_EXAM_MENIT, jawaban_lama=jawaban_lama)


@app.route("/chart/<cid>", methods=["GET", "POST"])
@login_required
def chart_page(cid):
    drill = curriculum.get_chart(cid)
    if not drill:
        abort(404)
    user = _user()
    solves = db.get_chart_solves(user["id"])
    praktik = drill.get("jenis") == "praktik"
    hasil = None
    if request.method == "POST" and cid not in solves:
        if praktik:
            try:
                jawab_harga = float(request.form.get("jawab_harga", ""))
            except ValueError:
                jawab_harga = None
            if jawab_harga is not None and jawab_harga > 0:
                kunci = float(drill["kunci"])
                tol = float(drill.get("toleransi_pct", 1.5)) / 100
                benar = abs(jawab_harga - kunci) <= kunci * tol
                xp = curriculum.xp_for_chart(drill)
                inserted, _streak = db.chart_add_solve(
                    user["id"], cid, int(round(jawab_harga)), benar, xp if benar else 0)
                if inserted:
                    hasil = {"benar": benar, "xp": xp if benar else 0,
                             "pilihanmu": int(round(jawab_harga))}
                    solves = db.get_chart_solves(user["id"])
        else:
            try:
                choice = int(request.form.get("choice", -1))
            except ValueError:
                choice = -1
            if 0 <= choice < len(drill["pilihan"]):
                benar = choice == int(drill["jawaban"])
                xp = curriculum.xp_for_chart(drill)
                inserted, _streak = db.chart_add_solve(user["id"], cid, choice, benar,
                                                       xp if benar else 0)
                if inserted:
                    hasil = {"benar": benar, "xp": xp if benar else 0, "pilihanmu": choice}
                    solves = db.get_chart_solves(user["id"])
    jawab = solves.get(cid)
    try:
        svg = chartgen.render_drill(
            drill,
            interaktif=praktik and jawab is None,
            garis_extra=[float(drill["kunci"])] if (praktik and jawab is not None) else None,
            garis_user=float(jawab["choice"]) if (praktik and jawab is not None) else None,
        )
    except (OSError, ValueError):
        svg = None
    # drill berikutnya yang belum selesai (navigasi lanjut)
    semua = curriculum.get_charts()
    urutan = [d["id"] for d in semua]
    next_d = None
    for d in semua[urutan.index(cid) + 1:] + semua[:urutan.index(cid)]:
        if d["id"] not in solves:
            next_d = d
            break
    return render_template("chart.html", drill=drill, svg=svg, jawab=jawab,
                           hasil=hasil, next_d=next_d, praktik=praktik,
                           xp_drill=curriculum.xp_for_chart(drill))


@app.route("/chart/<cid>/svg")
@login_required
def chart_svg(cid):
    """SVG utuh (tab baru) — biar bisa dizoom besar di HP."""
    drill = curriculum.get_chart(cid)
    if not drill:
        abort(404)
    try:
        svg = chartgen.render_drill(drill)
    except (OSError, ValueError):
        abort(404)
    return app.response_class(svg, mimetype="image/svg+xml")


# ---------- Leaderboard & Badges ----------

@app.route("/leaderboard")
@login_required
def leaderboard_page():
    rows = db.leaderboard()
    me = _user()
    return render_template("leaderboard.html", rows=rows, me_id=me["id"])


@app.route("/badges")
@login_required
def badges_page():
    user = _user()
    solves = db.get_solves(user["id"])
    solved_n = len(solves)
    correct_n = sum(1 for s in solves.values() if s["correct"])
    streak = user["streak"]
    total = curriculum.total_scenarios()
    babs = curriculum.get_babs()
    bab_clear = 0
    for b in babs:
        ids = [s["id"] for s in (b.get("skenario") or [])]
        if ids and all(i in solves for i in ids):
            bab_clear += 1
    earned = []
    def add(code, icon, name, desc, cond):
        if cond:
            earned.append({"icon": icon, "name": name, "desc": desc})
    add("first", "🔰", "Pertama Kali", "Selesaikan 1 skenario", solved_n >= 1)
    add("junior", "📊", "Analis Junior", "Selesaikan 5 skenario", solved_n >= 5)
    add("senior", "📈", "Analis Senior", "Selesaikan 15 skenario", solved_n >= 15)
    add("master", "👑", "Quant Master", "Selesaikan semua skenario", solved_n >= total)
    add("streak3", "🔥", "On Fire", "Streak 3 hari", streak >= 3)
    add("streak7", "⚙️", "Mesin Trading", "Streak 7 hari", streak >= 7)
    add("streak30", "🏆", "Legenda", "Streak 30 hari", streak >= 30)
    add("perfect", "🎯", "Tanpa Cela", "≥10 skenario dan semua benar", correct_n >= 10 and correct_n == solved_n)
    add("babclear", "✅", "Bab Clear", "Tuntaskan semua bab", bab_clear == len(babs))
    # Badges per track
    solved_all = set(solves.keys())
    soal_solved_set = db.get_soal_solved(user["id"])
    tp = track_progress(solved_all, soal_solved_set)
    for t in tp:
        if t["total"] > 0 and t["done"] == t["total"]:
            icons = {"math": "🧮", "python": "🐍", "finance": "💰", "quant": "👑"}
            names = {"math": "Matematikawan", "python": "Programmer", "finance": "Finansial", "quant": "Quant Master"}
            add(f"track_{t['code']}", icons.get(t["code"], "🎖️"), names.get(t["code"], t["name"]),
                f"Tuntaskan track {t['name']}", True)
    all_badges = [
        ("first", "🔰", "Pertama Kali", "Selesaikan 1 skenario"),
        ("junior", "📊", "Analis Junior", "Selesaikan 5 skenario"),
        ("senior", "📈", "Analis Senior", "Selesaikan 15 skenario"),
        ("master", "👑", "Quant Master", "Selesaikan semua skenario"),
        ("streak3", "🔥", "On Fire", "Streak 3 hari"),
        ("streak7", "⚙️", "Mesin Trading", "Streak 7 hari"),
        ("streak30", "🏆", "Legenda", "Streak 30 hari"),
        ("perfect", "🎯", "Tanpa Cela", "≥10 skenario dan semua benar"),
        ("babclear", "✅", "Bab Clear", "Tuntaskan semua bab"),
        ("track_math", "🧮", "Matematikawan", "Tuntaskan track Fondasi Matematika"),
        ("track_python", "🐍", "Programmer", "Tuntaskan track Python dari Nol"),
        ("track_finance", "💰", "Finansial", "Tuntaskan track Finance Dasar"),
        ("track_quant", "👑", "Quant Master", "Tuntaskan track Quant Integrasi"),
    ]
    earned_ids = {e["icon"] for e in earned}
    return render_template("badges.html", earned=earned,
                           locked=[b for b in all_badges if b[1] not in earned_ids],
                           solved_n=solved_n, correct_n=correct_n,
                           total=total, streak=streak, bab_clear=bab_clear)


@app.route("/manifest.json")
def manifest_route():
    """Manifest DINAMIS: start_url/icon menyesuaikan prefix funnel (/quant)."""
    import json
    base = request.script_root
    data = {
        "name": "QuantLab — Akademi Trading Kuantitatif",
        "short_name": "QuantLab",
        "description": "Belajar trading kuantitatif lewat skenario keputusan nyata: kasus pasar, keputusan, terjemahan Python, dan hasilnya.",
        "start_url": base + "/",
        "scope": base + "/",
        "display": "standalone",
        "background_color": "#070b10",
        "theme_color": "#070b10",
        "categories": ["education", "finance"],
        "lang": "id",
        "icons": [
            {"src": base + "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": base + "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": base + "/static/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
        ],
        "shortcuts": [
            {"name": "Dashboard", "short_name": "Beranda", "url": base + "/"},
            {"name": "Lab Teknikal", "short_name": "Teknikal", "url": base + "/chart"},
            {"name": "Notebook", "short_name": "Notebook", "url": base + "/notebook"},
            {"name": "Data Science", "short_name": "Data", "url": base + "/data-science"},
        ],
    }
    return app.response_class(json.dumps(data), mimetype="application/manifest+json")


@app.route("/sw.js")
def sw_js():
    sw = """const CACHE = 'quantlab-v23';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks =>
  Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.startsWith('/skenario/')) return;
  e.respondWith(caches.open(CACHE).then(async c => {
    try {
      const live = await fetch(e.request);
      if (live.ok && url.origin === location.origin) c.put(e.request, live.clone());
      return live;
    } catch {
      const cached = await c.match(e.request);
      return cached || Response.error();
    }
  }));
});"""
    return app.response_class(sw, mimetype="application/javascript")


@app.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    user = _user()
    msg = None
    err = None
    if request.method == "POST":
        ok, res = db.change_password(user["id"],
                                     request.form.get("oldpass", ""),
                                     request.form.get("newpass", ""))
        if ok:
            msg = "Password berhasil diganti."
            user = _user()  # refresh
        else:
            err = res
    solves = db.get_solves(user["id"])
    act = db.activity_dates(user["id"], days=30)
    today = datetime.now(db.WIB).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    heat = [{"date": d, "n": act.get(d, 0)} for d in days]
    correct = sum(1 for s in solves.values() if s["correct"])
    return render_template("profile.html", user=user, err=err, msg=msg,
                           solved_n=len(solves), correct_n=correct,
                           heat=heat)


# ---------- Jurnal Trading ----------

ARAH_LIST = ["BELI", "JUAL"]
EMOSI_LIST = ["tenang", "netral", "ragu", "FOMO", "panik", "serakah", "kesal"]


@app.route("/jurnal", methods=["GET", "POST"])
@login_required
def jurnal():
    user = _user()
    err = None
    if request.method == "POST":
        if request.form.get("action") == "delete":
            eid = request.form.get("id", "")
            if eid.isdigit() and db.journal_delete(user["id"], int(eid)):
                return redirect(url_for("jurnal"))
            err = "Gagal menghapus entri."
        else:
            try:
                entry = float(request.form.get("entry", ""))
                exit_p = float(request.form.get("exit", ""))
                arah = request.form.get("arah", "BELI")
                if arah not in ARAH_LIST:
                    raise ValueError
                if entry <= 0 or exit_p <= 0:
                    raise ValueError
                if arah == "BELI":
                    hasil = (exit_p - entry) / entry * 100
                else:
                    hasil = (entry - exit_p) / entry * 100
                data = {
                    "tanggal": request.form.get("tanggal", "") or datetime.now(db.WIB).date().isoformat(),
                    "aset": (request.form.get("aset", "") or "").strip()[:20],
                    "arah": arah,
                    "entry_price": entry,
                    "exit_price": exit_p,
                    "size": float(request.form.get("size", 1) or 1),
                    "hasil": hasil,
                    "emosi": request.form.get("emosi", "")[:20],
                    "catatan": (request.form.get("catatan", "") or "").strip()[:1000],
                }
                if not data["aset"]:
                    raise ValueError
                db.journal_add(user["id"], data)
                return redirect(url_for("jurnal"))
            except ValueError:
                err = "Data tidak valid — cek harga entry/exit (angka positif) dan aset."
    entries = db.journal_list(user["id"])
    stats = db.journal_stats(user["id"])
    return render_template("jurnal.html", entries=entries, stats=stats,
                           err=err, arah_list=ARAH_LIST, emosi_list=EMOSI_LIST,
                           today=datetime.now(db.WIB).date().isoformat())


# ---------- Mode Ujian per Track ----------

EXAM_QUESTIONS = 8
EXAM_MINUTES = 12


def _exam_build(track, seed=None):
    """8 soal acak dari skenario track, deterministik dari seed.
    Session HANYA menyimpan seed + jawaban (cookie Flask ~4KB, soal penuh tidak muat)."""
    pool = []
    for t in curriculum.get_tracks():
        if t["code"] != track:
            continue
        for b in t["babs"]:
            for s in (b.get("skenario") or []):
                pool.append(s)
    if len(pool) < EXAM_QUESTIONS:
        return None
    qs = random.Random(seed).sample(pool, EXAM_QUESTIONS) if seed is not None else random.sample(pool, EXAM_QUESTIONS)
    return [{"id": s["id"], "judul": s["judul"], "pilihan": s["pilihan"],
             "jawaban": int(s["jawaban"])} for s in qs]


def _exam_state(track):
    st = session.get("exam")
    if not st or st.get("track") != track:
        return None
    return st


def _exam_questions(st):
    return _exam_build(st["track"], st.get("seed")) or []


@app.route("/ujian/<track>", methods=["GET", "POST"])
@login_required
def ujian(track):
    valid = {t["code"] for t in curriculum.get_tracks()}
    if track not in valid:
        abort(404)
    st = _exam_state(track)
    if st is None:
        seed = secrets.randbits(30)
        qs = _exam_build(track, seed)
        if qs is None:
            return render_template("exam_start.html", track=track, not_enough=True)
        st = {
            "track": track,
            "seed": seed,
            "answers": {},
            "deadline": (datetime.now(db.WIB) + timedelta(minutes=EXAM_MINUTES)).timestamp(),
        }
        session["exam"] = st
    if request.method == "POST":
        qid = request.form.get("qid", "")
        choice = request.form.get("choice")
        if choice is not None and choice.isdigit():
            st["answers"][qid] = int(choice)
            session["exam"] = st
        # tombol selesai / soal terakhir
        if request.form.get("finish") or len(st["answers"]) >= EXAM_QUESTIONS:
            return redirect(url_for("ujian_hasil", track=track))
    qs = _exam_questions(st)
    answered = st["answers"]
    n = len(answered)
    if n >= len(qs):
        return redirect(url_for("ujian_hasil", track=track))
    q = qs[n]
    sisa = max(0, st["deadline"] - datetime.now(db.WIB).timestamp())
    if sisa <= 0:
        return redirect(url_for("ujian_hasil", track=track))
    return render_template("exam.html", track=track, q=q, no=n + 1,
                           total=len(qs), sisa=int(sisa))


@app.route("/ujian/<track>/hasil")
@login_required
def ujian_hasil(track):
    st = _exam_state(track)
    if st is None:
        return redirect(url_for("ujian", track=track))
    qs = _exam_questions(st)
    answers = st["answers"]
    rows = []
    correct = 0
    for q in qs:
        a = answers.get(q["id"])
        ok = a == q["jawaban"]
        correct += 1 if ok else 0
        rows.append({"judul": q["judul"], "pilihan": q["pilihan"],
                     "user": a, "jawaban": q["jawaban"], "ok": ok})
    total = len(qs)
    pct = round(correct / total * 100) if total else 0
    passed = pct >= 70
    bonus = 0
    if passed:
        inserted, bonus = db.exam_record(_user()["id"], track, correct, total)
        if not inserted:
            bonus = 0  # sudah pernah lulus
    session.pop("exam", None)
    return render_template("exam_result.html", track=track, rows=rows,
                           correct=correct, total=total, pct=pct,
                           passed=passed, bonus=bonus)


@app.route("/jurnal/export")
@login_required
def jurnal_export():
    import csv
    import io
    user = _user()
    entries = db.journal_list(user["id"], limit=10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["tanggal", "aset", "arah", "entry", "exit", "size", "hasil_persen", "emosi", "catatan"])
    for e in entries:
        w.writerow([e["tanggal"], e["aset"], e["arah"], e["entry_price"],
                    e["exit_price"], e["size"], e["hasil"], e["emosi"], e["catatan"]])
    data = buf.getvalue()
    resp = app.response_class(data, mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=quantlab-jurnal.csv"
    return resp


# ---------- Ulasan Cerdas (spaced repetition) ----------

@app.route("/ulas")
@login_required
def ulas():
    user = _user()
    due = db.review_due(user["id"])
    items = []
    for d in due:
        entry = curriculum.get_scenario(d["scenario_id"])
        if not entry:
            continue
        items.append({
            "id": d["scenario_id"],
            "judul": entry["data"]["judul"],
            "emoji": entry["data"]["emoji"],
            "stage": d["stage"],
            "bab": entry["bab"]["bab"],
            "track": curriculum.track_of(entry["bab"]),
        })
    msg = request.args.get("res")
    return render_template("ulas.html", items=items, msg=msg)


@app.route("/ulas/<sid>", methods=["GET", "POST"])
@login_required
def ulas_soal(sid):
    entry = curriculum.get_scenario(sid)
    if not entry:
        abort(404)
    user = _user()
    due_ids = {d["scenario_id"] for d in db.review_due(user["id"])}
    if sid not in due_ids:
        return redirect(url_for("ulas"))
    if request.method == "POST":
        try:
            choice = int(request.form.get("choice", -1))
        except ValueError:
            choice = -1
        scen = entry["data"]
        if choice < 0 or choice >= len(scen["pilihan"]):
            return redirect(url_for("ulas_soal", sid=sid))
        correct = choice == int(scen["jawaban"])
        graduated, stage = db.review_answer(user["id"], sid, correct)
        if graduated:
            return redirect(url_for("ulas", res="graduated"))
        return redirect(url_for("ulas", res="ok" if correct else "wrong"))
    scen = entry["data"]
    solved = db.get_solves(user["id"])
    my_answer = solved[sid]["choice"] if sid in solved else None
    stage = next((d["stage"] for d in db.review_due(user["id"]) if d["scenario_id"] == sid), 1)
    return render_template("ulas_soal.html", bab=entry["bab"], scen=scen,
                           stage=stage, my_answer=my_answer)


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Halaman tidak ditemukan."), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, msg=str(e)), 400


@app.errorhandler(429)
def too_many(e):
    return render_template("error.html", code=429,
                           msg="Terlalu cepat — tunggu sebentar lalu coba lagi."), 429


@app.errorhandler(413)
def too_large(e):
    return render_template("error.html", code=413,
                           msg="File/permintaan terlalu besar — upload maksimal 5 MB."), 413


# ---------- Rate limit aksi berat (jalankan kode user) ----------

_heavy_rl: dict[str, list[float]] = {}


def _heavy_ok(key: str, per_min: int = 6) -> bool:
    """In-memory per worker: maks per_min request dalam 60 detik."""
    now = time.time()
    ts = _heavy_rl.setdefault(key, [])
    ts[:] = [x for x in ts if now - x < 3600]
    if len([x for x in ts if now - x < 60]) >= per_min:
        return False
    ts.append(now)
    return True


# ---------- Pencarian kurikulum (ala Khan Academy) ----------

@app.route("/cari")
@login_required
def cari():
    q = (request.args.get("q") or "").strip().lower()
    res = {"bab": [], "pelajaran": [], "skenario": [], "soal": []}
    if len(q) >= 2:
        for b in (curriculum.get_babs() or []):
            bab_key = f"{b.get('judul', '')} {b.get('deskripsi', '')}".lower()
            if q in bab_key:
                res["bab"].append(b)
            for pel in b.get("pelajaran") or []:
                if q in f"{pel.get('judul', '')} {pel.get('materi', '')}".lower():
                    res["pelajaran"].append((b, pel))
            for s in b.get("skenario") or []:
                if q in f"{s.get('judul', '')} {s.get('cerita', '')} {s.get('penjelasan', '')}".lower():
                    res["skenario"].append((b, s))
            for so in b.get("soal") or []:
                if q in f"{so.get('judul', '')} {so.get('cerita', '')}".lower():
                    res["soal"].append((b, so))
    for k in res:
        res[k] = res[k][:12]
    return render_template("cari.html", q=(request.args.get("q") or "").strip(),
                           res=res)


# ---------- Data Science (pusat latihan kompetisi) ----------

DS_LEVELS = [
    (100, "🏆", "Data Scientist Bersertifikat"),
    (90, "🧠", "Calon Data Scientist"),
    (75, "🎯", "Penilai Model"),
    (60, "🤖", "Pemodel Pemula"),
    (45, "🛠️", "Perakit Fitur"),
    (30, "🔍", "Penjelajah Data"),
    (15, "🧹", "Tukang Bersih Data"),
    (0, "🌱", "Baru Kenalan"),
]


def ds_level(done, total):
    """Level belajar Data Science dari progres aktivitas track ds (72 aktivitas)."""
    pct = round(done / total * 100) if total else 0
    cur = DS_LEVELS[-1]
    for t, emoji, nama in DS_LEVELS:
        if pct >= t:
            cur = (t, emoji, nama)
            break
    nxt = None
    for t, emoji, nama in DS_LEVELS:
        if t <= pct:
            break
        nxt = {"t": t, "emoji": emoji, "nama": nama}
    return {"pct": pct, "emoji": cur[1], "nama": cur[2], "next": nxt,
            "done": done, "total": total}


@app.route("/data-science")
@login_required
def data_science():
    """Hub fitur Data Science: roadmap 6 bab + notebook + dataset + ujian & level."""
    user = _user()
    solved = db.solved_ids(user["id"])
    soal_solved_set = db.get_soal_solved(user["id"])
    lessons_done = db.get_lesson_done(user["id"])
    nb_judul = [r["judul"] for r in db.notebook_list(user["id"])]
    tracks = track_progress(solved, soal_solved_set)
    ds = next((t for t in tracks if t["code"] == "ds"), None)
    cards = []
    for b in (ds["babs"] if ds else []):
        scens = b.get("skenario") or []
        qs = b.get("soal") or []
        ls = b.get("pelajaran") or []
        done_s = sum(1 for s in scens if s["id"] in solved)
        done_q = sum(1 for q in qs if q["id"] in soal_solved_set)
        done_l = sum(1 for l in ls if l["id"] in lessons_done)
        nb_done = any(j.startswith(f"Latihan Bab {b['bab']}") for j in nb_judul)
        cards.append({
            "bab": b["bab"], "judul": b["judul"], "emoji": b["emoji"],
            "deskripsi": b.get("deskripsi", ""),
            "done": done_s + done_q, "n": len(scens) + len(qs),
            "l_done": done_l, "l_n": len(ls),
            "q_done": done_q, "q_n": len(qs),
            "s_done": done_s, "s_n": len(scens),
            "nb": nb_done,
        })
    level = ds_level(ds["done"] if ds else 0, ds["total"] if ds else 0)
    _bk = db.submission_best(user["id"], "kredit_umkm")
    best_komp = dict(_bk) if _bk else None
    tpl_ds = {k: v for k, v in nblib.TEMPLATE_META.items() if v.get("group") == "ds"}
    return render_template(
        "data_science.html", cards=cards, ds=ds, level=level,
        exam=db.exam_passed(user["id"], "ds"),
        tpl_ds=tpl_ds, playbook=nblib.TEMPLATE_META.get("playbook"),
        datasets=nblib.list_datasets(),
        uploads_n=len(nblib.list_uploads(user["username"])),
        best_komp=best_komp,
        n_materi=matlib.ringkas(),
        nsub_komp=db.submission_count(user["id"], "kredit_umkm"))


# ---------- Materi Bootcamp (Pacmann + Rakamin) di hub Data Science ----------

@app.route("/data-science/materi")
@login_required
def data_science_materi():
    """Katalog materi bootcamp (Pacmann + Rakamin) — video & slide siap putar/baca."""
    return render_template("materi.html", katalog=matlib.katalog())


@app.route("/data-science/materi/<slug>/<path:rel>")
@login_required
def materi_berkas(slug, rel):
    """Penyaji berkas materi (inline; Range didukung untuk video)."""
    return matlib.ambil(slug, rel)


# ---------- Kompetisi Simulasi (nilai /work/submission.csv vs kunci) ----------

KOMPETISI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kompetisi")

KOMPETISI = {
    "kredit_umkm": {
        "nama": "Lomba Kredit UMKM",
        "emoji": "\U0001F3E6",
        "deskripsi": "Prediksi status 150 pengajuan kredit baru (Lancar / Macet) — dari data mentah sampai submission, ala lomba data science sungguhan.",
        "n": 150,
        "kolom": ("id_pengajuan", "status_prediksi"),
        "labels": ("Lancar", "Macet"),
        "kunci": os.path.join(KOMPETISI_DIR, "kredit_umkm_uji_kunci.csv"),
        "baseline_mode": 0.760,   # tebakan mayoritas (semua "Lancar")
        "contoh_model": 0.847,    # logreg ala Playbook, terukur di data uji
        "tier_gold": 0.87,
        "tier_silver": 0.84,
        "tier_bronze": 0.78,
    },
}


def _kompetisi_kunci(ev):
    kunci = {}
    with open(ev["kunci"], newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kunci[row["id_pengajuan"].strip()] = row["status"].strip()
    return kunci


def _kompetisi_nilai(username, ev):
    """Baca submission user, validasi, dan nilai vs kunci. return (hasil|None, pesan_error)."""
    spath = nblib.submission_path(username)
    if not os.path.isfile(spath):
        return None, "Belum ada berkas /work/submission.csv — jalankan dulu Notebook Playbook sampai sel terakhir."
    if os.path.getsize(spath) > 1_000_000:
        return None, "Berkas submission terlalu besar (maks 1 MB)."
    try:
        kunci = _kompetisi_kunci(ev)
    except OSError:
        return None, "Kunci penilaian belum tersedia di server — hubungi admin."
    rows = []
    with open(spath, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        for c in ev["kolom"]:
            if c not in cols:
                return None, f"Kolom '{c}' tidak ditemukan — header harus memuat: {', '.join(ev['kolom'])}."
        for x in reader:
            rows.append(((x.get("id_pengajuan") or "").strip(),
                         (x.get("status_prediksi") or "").strip()))
    if len(rows) != ev["n"]:
        return None, f"Jumlah baris {len(rows)} — harus {ev['n']} (satu prediksi per pengajuan)."
    ids = [rid for rid, _ in rows]
    if len(set(ids)) != len(ids):
        return None, "Ada id_pengajuan yang duplikat — pastikan satu prediksi per pengajuan."
    if set(ids) != set(kunci):
        return None, (f"Daftar id_pengajuan tidak cocok dengan data uji "
                      f"(kurang {len(set(kunci) - set(ids))}, asing {len(set(ids) - set(kunci))}) — "
                      f"pakai persis kolom id dari kredit_umkm_uji.csv.")
    norm = {lab.lower(): lab for lab in ev["labels"]}
    tp = tn = fp = fn = 0
    asing = []
    for rid, val in rows:
        pred = norm.get(val.lower())
        if pred is None:
            asing.append(val)
            continue
        true = kunci[rid]
        if true == "Macet":
            tp += pred == "Macet"
            fn += pred == "Lancar"
        else:
            tn += pred == "Lancar"
            fp += pred == "Macet"
    if asing:
        contoh = ", ".join(sorted(set(asing))[:3])
        return None, f"Isi status_prediksi harus 'Lancar' atau 'Macet' (ditemukan: {contoh})."
    n = tp + tn + fp + fn
    acc = (tp + tn) / n
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    if acc >= ev["tier_gold"]:
        medal = "\U0001F947"
    elif acc >= ev["tier_silver"]:
        medal = "\U0001F948"
    elif acc >= ev["tier_bronze"]:
        medal = "\U0001F949"
    elif acc >= ev["baseline_mode"]:
        medal = "\u2705"
    else:
        medal = "\u274C"
    return {"n": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "accuracy": round(acc, 4), "precision": round(prec, 4),
            "recall": round(rec, 4), "medal": medal}, None


@app.route("/kompetisi")
@login_required
def kompetisi():
    user = _user()
    ev = KOMPETISI["kredit_umkm"]
    hist = db.submission_list(user["id"], "kredit_umkm", 12)
    for h in hist:
        h["waktu"] = _nb_wib(h["created_at"])
    _bk = db.submission_best(user["id"], "kredit_umkm")
    best = dict(_bk) if _bk else None
    hasil = hasil_d = None
    try:
        sid = int(request.args.get("sid", ""))
    except ValueError:
        sid = 0
    if sid:
        row = db.submission_get(sid, user["id"])
        if row:
            hasil = dict(row)
            try:
                hasil_d = json.loads(hasil.get("detail") or "{}")
            except ValueError:
                hasil_d = {}
    return render_template("kompetisi.html", ev=ev, hist=hist, best=best,
                           nsub=db.submission_count(user["id"], "kredit_umkm"),
                           hasil=hasil, hasil_d=hasil_d,
                           ada_file=os.path.isfile(nblib.submission_path(user["username"])),
                           kunci_ada=os.path.isfile(ev["kunci"]))


@app.route("/kompetisi/cek", methods=["POST"])
@login_required
def kompetisi_cek():
    user = _user()
    ev = KOMPETISI["kredit_umkm"]
    hasil, err = _kompetisi_nilai(user["username"], ev)
    if err:
        return redirect(url_for("kompetisi") + "?err=" + quote(err))
    sid = db.submission_add(user["id"], "kredit_umkm", hasil["n"], hasil["accuracy"],
                            hasil["precision"], hasil["recall"], hasil["medal"],
                            json.dumps({k: hasil[k] for k in ("tp", "tn", "fp", "fn")}))
    return redirect(url_for("kompetisi") + f"?sid={sid}")


# ---------- Notebook (ala Kaggle) ----------

def _nb_wib(ts):
    """Timestamp UTC SQLite → 'dd/mm HH:MM' WIB untuk tampilan."""
    try:
        d = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + timedelta(hours=7)
        return d.strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return "-"


@app.route("/notebook")
@login_required
def notebook_list():
    user = _user()
    rows = db.notebook_list(user["id"])
    for r in rows:
        r["updated_wib"] = _nb_wib(r["updated_at"])
    tpl_umum = {k: v for k, v in nblib.TEMPLATE_META.items() if v.get("group") != "ds"}
    tpl_ds = {k: v for k, v in nblib.TEMPLATE_META.items() if v.get("group") == "ds"}
    return render_template(
        "notebooks.html",
        rows=rows,
        templates=tpl_umum,
        templates_ds=tpl_ds,
        total_cells=sum(r["n_cells"] for r in rows),
    )


@app.route("/notebook/baru", methods=["POST"])
@login_required
def notebook_baru():
    user = _user()
    tpl = request.form.get("template", "kosong")
    meta = nblib.TEMPLATE_META.get(tpl, nblib.TEMPLATE_META["kosong"])
    cells = nblib.template_cells(tpl)
    judul = (request.form.get("judul") or "").strip()[:80] or meta["judul"]
    nid = db.notebook_create(user["id"], judul,
                             nblib.cells_to_json(cells), emoji=meta["emoji"])
    return redirect(url_for("notebook_editor", nid=nid))


@app.route("/notebook/<int:nid>")
@login_required
def notebook_editor(nid):
    user = _user()
    row = db.notebook_get(nid, user["id"])
    if not row:
        abort(404)
    try:
        cells = json.loads(row["cells"] or "[]")
    except ValueError:
        cells = []
    return render_template(
        "notebook.html",
        nb=row,
        cells_json=nblib.cells_for_js(cells),
        datasets=nblib.list_datasets(),
        uploads=nblib.list_uploads(user["username"]),
        exec_timeout=int(nblib.EXEC_TIMEOUT_S),
        updated_wib=_nb_wib(row["updated_at"]),
    )


@app.route("/notebook/datasets")
@login_required
def notebook_datasets():
    user = _user()
    items = nblib.list_datasets()
    for it in items:
        it["preview"] = nblib.dataset_preview(it["name"], 5)
    uploads = nblib.list_uploads(user["username"])
    for up in uploads:
        up["preview"] = nblib.upload_preview(user["username"], up["name"])
    return render_template("notebook_datasets.html", items=items,
                           groups=nblib.group_datasets(items), uploads=uploads)


@app.route("/bab/<int:n>/notebook", methods=["POST"])
@login_required
def bab_notebook(n):
    """Buat (atau buka) starter notebook untuk bab yang punya template latihan."""
    user = _user()
    bab = curriculum.get_bab(n)
    key = nblib.bab_template_key(n)
    if not bab or not key:
        abort(404)
    cells = nblib.template_cells(key)
    judul = f"Latihan Bab {n} — {bab['judul']}"[:80]
    nid = db.notebook_create(user["id"], judul, nblib.cells_to_json(cells),
                             emoji=bab.get("emoji") or "📊")
    return redirect(url_for("notebook_editor", nid=nid))


@app.route("/api/notebook/<int:nid>/simpan", methods=["POST"])
@login_required
def notebook_simpan(nid):
    user = _user()
    if not db.notebook_get(nid, user["id"]):
        return {"ok": False, "error": "notebook tidak ditemukan"}, 404
    try:
        judul, cells_json = nblib.parse_payload(request.form.get("payload", ""))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}, 400
    db.notebook_update(nid, user["id"], judul, cells_json)
    return {"ok": True, "saved_wib": datetime.now().strftime("%H:%M:%S")}


@app.route("/api/notebook/<int:nid>/jalankan", methods=["POST"])
@login_required
def notebook_jalankan(nid):
    user = _user()
    if not db.notebook_get(nid, user["id"]):
        return {"ok": False, "error": "notebook tidak ditemukan"}, 404
    code = request.form.get("code", "")
    if len(code) > nblib.CODE_CAP:
        return {"status": "error", "error_type": "toolong",
                "error": f"Kode terlalu panjang (maks {nblib.CODE_CAP} karakter).",
                "stdout": "", "stderr": "", "result": None}
    cell = request.form.get("cell") or None
    result = nblib.run_cell(user["username"], code, cell=cell)
    result["ok"] = result.get("status") in ("ok", "error")
    return result


@app.route("/api/notebook/<int:nid>/restart", methods=["POST"])
@login_required
def notebook_restart(nid):
    user = _user()
    if not db.notebook_get(nid, user["id"]):
        return {"ok": False, "error": "notebook tidak ditemukan"}, 404
    return nblib.kernel_restart(user["username"])


@app.route("/api/notebook/<int:nid>/status")
@login_required
def notebook_status(nid):
    user = _user()
    if not db.notebook_get(nid, user["id"]):
        return {"ok": False, "error": "notebook tidak ditemukan"}, 404
    return nblib.kernel_status(user["username"])


@app.route("/api/notebook/<int:nid>/hapus", methods=["POST"])
@login_required
def notebook_hapus(nid):
    user = _user()
    n = db.notebook_delete(nid, user["id"])
    return {"ok": bool(n)}


# ---------- Upload CSV user (data latihan/lomba) ----------

def _nb_back(key, val):
    """Redirect balik ke halaman notebook (editor/dataset) dengan pesan singkat."""
    nxt = request.form.get("next") or ""
    if not nxt.startswith("/notebook"):
        nxt = url_for("notebook_datasets")
    sep = "&" if "?" in nxt else "?"
    return f"{nxt}{sep}{key}={quote(str(val))}"


@app.route("/notebook/upload", methods=["POST"])
@login_required
def notebook_upload():
    user = _user()
    f = request.files.get("file")
    if f is None or not (f.filename or "").strip():
        return redirect(_nb_back("uploaderr", "Pilih file dulu."))
    ok, res = nblib.save_upload(user["username"], f)
    return redirect(_nb_back("uploaded" if ok else "uploaderr", res))


@app.route("/notebook/upload/hapus", methods=["POST"])
@login_required
def notebook_upload_hapus():
    user = _user()
    ok, res = nblib.delete_upload(user["username"], request.form.get("name", ""))
    return redirect(_nb_back("uploadhapus" if ok else "uploaderr", res))


# ---------- Middleware subpath — akses via https://yan.tail51a905.ts.net/quant (Funnel 443) ----------
# Tailscale serve strip prefix-nya, jadi URL absolut (url_for, fetch, redirect) harus diprefix manual.
class SubPathMiddleware:
    def __init__(self, app, prefix="/quant", host_suffix="tail51a905.ts.net"):
        self.app = app
        self.prefix = prefix
        self.host_suffix = host_suffix

    def __call__(self, environ, start_response):
        host = environ.get("HTTP_HOST", "")
        via_funnel = host.endswith(self.host_suffix)
        if via_funnel:
            # Lewat funnel: path sudah distrip Tailscale — cukup set SCRIPT_NAME
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") + self.prefix).rstrip("/")
        else:
            # Akses langsung (localhost/LAN): strip prefix manual kalau ada
            path = environ.get("PATH_INFO", "")
            if path.startswith(self.prefix):
                environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") + self.prefix).rstrip("/")
                environ["PATH_INFO"] = path[len(self.prefix):] or "/"

        tangkap = {}

        def start_response_wrapper(status, headers, exc_info=None):
            # Tunda start_response asli — header masih bisa berubah (rewrite/gzip/Content-Length).
            tangkap["status"] = status
            tangkap["headers"] = list(headers)
            tangkap["exc_info"] = exc_info
            return lambda _b: None  # stub write() — Flask tidak memakainya

        app_iter = self.app(environ, start_response_wrapper)
        status = tangkap.get("status", "500 Internal Server Error")
        headers = tangkap.get("headers", [])
        ctype = next((v for k, v in headers if k.lower() == "content-type"), "") or ""
        cenc = next((v for k, v in headers if k.lower() == "content-encoding"), "") or ""

        if (via_funnel and "text/html" in ctype and cenc.lower() in ("", "gzip")
                and environ.get("REQUEST_METHOD", "GET") != "HEAD"):
            # Buffer + rewrite path absolut hardcoded (fetch, href, src, action).
            # NB: badan bisa datang ter-gzip (flask-compress) → buka dulu, bungkus ulang.
            body = b"".join(app_iter)
            if "gzip" in cenc.lower():
                try:
                    body = gzip.decompress(body)
                except Exception:
                    pass
            text = body.decode("utf-8", "replace")
            text = re.sub(r"""(fetch\(\s*['"])/""", r"\g<1>" + self.prefix + "/", text)
            text = re.sub(r"""(href|src|action)="/(?!quant/|pykode/|buku-kas/)""",
                          r"\g<1>=\"" + self.prefix + "/", text)
            body = text.encode("utf-8")
            headers = [(k, v) for k, v in headers if k.lower() != "content-length"]
            if "gzip" in cenc.lower():
                body = gzip.compress(body, 6)
                headers = [(k, v) for k, v in headers if k.lower() != "content-encoding"]
                headers.append(("Content-Encoding", "gzip"))
            headers.append(("Content-Length", str(len(body))))
            app_iter = [body]

        # ── Header bersama (semua respons; dulu di wrapper) ──
        if via_funnel:
            headers = [
                (k, self.prefix + v)
                if (k.lower() == "location" and v.startswith("/") and not v.startswith(self.prefix))
                else (k, v)
                for k, v in headers
            ]
        # Security headers (semua respons)
        has = {k.lower() for k, _ in headers}
        for name, val in (
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "strict-origin-when-cross-origin"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
        ):
            if name.lower() not in has:
                headers = headers + [(name, val)]
        # Cookie session hanya via HTTPS funnel diberi flag Secure
        if via_funnel:
            headers = [
                (k, v + "; Secure") if (k.lower() == "set-cookie" and "secure" not in v.lower()) else (k, v)
                for k, v in headers
            ]
        start_response(status, headers, tangkap.get("exc_info"))
        return app_iter


app.wsgi_app = SubPathMiddleware(app.wsgi_app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5200, debug=True)
