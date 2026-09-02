"""QuantLab — Belajar Quant Trading lewat Skenario.

Flask app: auth (CSRF + anti brute-force DB-backed), kurikulum YAML,
XP/streak/badges, leaderboard, playground (kalkulator + mini backtest MA).
"""
import math
import os
import random
import re
import secrets
import time
from datetime import datetime, timedelta

from flask import (
    Flask, abort, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash

import curriculum
import db
import judge
import market
import mentor

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", secrets.token_hex(32)
)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

db.init_db()

LESSON_XP = db.LESSON_XP
CHALLENGE_BONUS = 10

# ---------- Playground: data sintetis deterministik (seed tetap) ----------
_RNG = random.Random(7)
_SERIES = []
_price = 100.0
for _ in range(300):
    _price *= 1 + (0.0006 + _RNG.uniform(-0.018, 0.018))
    _SERIES.append(round(_price, 4))
TRADE_FEE = 0.001  # 0.1% per sisi


def ma_series(n, series):
    if len(series) < n:
        return []
    return [sum(series[i - n + 1:i + 1]) / n for i in range(n - 1, len(series))]


def backtest_ma(fast, slow, series):
    """Crossover MA: long saat MA_fast > MA_slow, flat sebaliknya. Net fee."""
    if fast >= slow or fast < 2:
        return None
    fast_ma = ma_series(fast, series)
    slow_ma = ma_series(slow, series)
    offset = slow - fast
    # indeks 0 di kedua array merujuk ke hari slow-1 di series
    n = len(slow_ma)
    equity, peak, maxdd = 100.0, 100.0, 0.0
    in_pos = False
    entry_i = 0
    trades, wins = 0, 0
    for i in range(1, n):
        signal = fast_ma[i + offset - 1] > slow_ma[i]  # MA_fast hari ini vs MA_slow
        if signal and not in_pos:
            in_pos = True
            entry_i = i
            equity *= (1 - TRADE_FEE)
        elif not signal and in_pos:
            in_pos = False
            trades += 1
            ret = (series[i + slow - 1] / series[entry_i + slow - 1]) - 1
            equity *= (1 + ret) * (1 - TRADE_FEE)
            if ret > 0:
                wins += 1
            peak = max(peak, equity)
            maxdd = max(maxdd, (peak - equity) / peak)
    if in_pos:
        trades += 1
        ret = (series[-1] / series[entry_i + slow - 1]) - 1
        equity *= (1 + ret) * (1 - TRADE_FEE)
        if ret > 0:
            wins += 1
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak)
    return {
        "fast": fast, "slow": slow,
        "ret": round((equity - 100) / 100 * 100, 2),
        "maxdd": round(maxdd * 100, 2),
        "trades": trades,
        "win": round(wins / trades * 100) if trades else 0,
        "spark": _sparkline(equity_history(series, fast, slow)),
    }


def equity_history(series, fast, slow):
    fast_ma = ma_series(fast, series)
    slow_ma = ma_series(slow, series)
    offset = slow - fast
    n = len(slow_ma)
    eq, in_pos, entry_i = 100.0, False, 0
    out = [100.0]
    for i in range(1, n):
        signal = fast_ma[i + offset - 1] > slow_ma[i]
        if signal and not in_pos:
            in_pos = True
            entry_i = i
            eq *= (1 - TRADE_FEE)
        elif not signal and in_pos:
            in_pos = False
            eq *= (series[i + slow - 1] / series[entry_i + slow - 1]) * (1 - TRADE_FEE)
        out.append(round(eq, 4))
    return out


def _sparkline(hist):
    lo, hi = min(hist), max(hist)
    rng = (hi - lo) or 1.0
    w, h = 240, 48
    pts = []
    for i, v in enumerate(hist):
        x = i / (len(hist) - 1) * w
        y = h - 4 - (v - lo) / rng * (h - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#22c55e" if hist[-1] >= hist[0] else "#ef4444"
    return (f"<svg viewBox='0 0 {w} {h}' class='spark'><polyline points='"
            + " ".join(pts) + f"' fill='none' stroke='{color}' stroke-width='1.5'/></svg>")


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
                           tracks=tracks, nxt=nxt, review_n=review_n)


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


@app.route("/soal/<qid>", methods=["GET", "POST"])
@login_required
def soal_page(qid):
    entry = curriculum.get_soal(qid)
    if not entry:
        abort(404)
    user = _user()
    soal_solved_set = db.get_soal_solved(user["id"])
    q = entry["data"]
    done = qid in soal_solved_set
    result = None
    code = ""
    if request.method == "POST":
        code = request.form.get("code", "")[:8000]
        if done:
            result = {"passed": q["xp"], "total": q["xp"], "already": True,
                      "results": []}
        else:
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
                           result=result, code=code,
                           render_md=curriculum.render_markdown)


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
    lessons = bab.get("pelajaran") or []
    lessons_done = db.get_lesson_done(user["id"])
    soals = bab.get("soal") or []
    soal_solved_set = db.get_soal_solved(user["id"])
    return render_template("bab.html", bab=bab, scens=scens,
                           lessons=lessons, lessons_done=lessons_done,
                           soals=soals, soal_solved=soal_solved_set,
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


# ---------- Playground ----------

@app.route("/playground", methods=["GET", "POST"])
@login_required
def playground():
    result = None
    if request.method == "POST":
        mode = request.form.get("mode")
        try:
            if mode == "funding":
                r = float(request.form.get("rate", 0)) / 100
                daily = r * 3
                annual = daily * 365
                result = {"mode": "funding", "rate": r,
                          "daily": daily * 100, "annual": annual * 100}
            elif mode == "size":
                eq = float(request.form.get("equity", 0))
                rp = float(request.form.get("risk", 0)) / 100
                sp = float(request.form.get("stop", 0)) / 100
                notional = eq * rp / sp if sp > 0 else 0
                result = {"mode": "size", "equity": eq, "risk": rp * 100,
                          "stop": sp * 100, "notional": notional}
            elif mode == "backtest":
                fast = int(request.form.get("fast", 5))
                slow = int(request.form.get("slow", 20))
                bt = backtest_ma(fast, slow, _SERIES)
                if bt:
                    result = {"mode": "backtest", **bt}
                else:
                    result = {"mode": "backtest", "error": "Fast harus < slow dan ≥ 2."}
            elif mode == "run":
                code = request.form.get("code", "")[:8000]
                r = judge.run_code(code, request.form.get("stdin", ""))
                result = {"mode": "run", "ok": r["ok"], "stdout": r["stdout"],
                          "stderr": r["stderr"]}
                if not r["ok"] and r["error_type"] not in ("timeout", "toolong"):
                    result["friendly"] = judge.friendly_error(r["stderr"])
            elif mode == "scan":
                fasts = [int(x) for x in request.form.get("fasts", "3,5,10,20").split(",")]
                slows = [int(x) for x in request.form.get("slows", "10,20,50,100").split(",")]
                rows = []
                for f in fasts:
                    for s in slows:
                        if f < s and f >= 2:
                            bt = backtest_ma(f, s, _SERIES)
                            if bt:
                                rows.append(bt)
                rows.sort(key=lambda r: r["ret"], reverse=True)
                result = {"mode": "scan", "rows": rows[:12], "total": len(rows)}
        except (ValueError, TypeError):
            result = {"mode": "error", "error": "Input tidak valid."}
    return render_template("playground.html", result=result)


@app.route("/manifest.json")
def manifest_route():
    """Manifest DINAMIS: start_url/icon menyesuaikan prefix funnel (/quant)."""
    import json
    base = request.script_root
    data = {
        "name": "QuantLab — Belajar Quant Trading",
        "short_name": "QuantLab",
        "start_url": base + "/",
        "scope": base + "/",
        "display": "standalone",
        "background_color": "#0b0f14",
        "theme_color": "#0b0f14",
        "icons": [{"src": base + "/static/icon.svg", "sizes": "any",
                   "type": "image/svg+xml", "purpose": "any"}],
    }
    return app.response_class(json.dumps(data), mimetype="application/manifest+json")


@app.route("/sw.js")
def sw_js():
    sw = """const CACHE = 'quantlab-v2';
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


# ---------- Analitik Belajar ----------

@app.route("/analitik")
@login_required
def analitik():
    user = _user()
    solves = db.get_solves(user["id"])
    soal_solved_set = db.get_soal_solved(user["id"])
    correct_n = sum(1 for s in solves.values() if s["correct"])
    solved_n = len(solves)
    # Akurasi per track & per kesulitan
    tracks = track_progress(set(solves.keys()), soal_solved_set)
    track_acc = []
    for t in tracks:
        t_ids = {s["id"] for b in t["babs"] for s in (b.get("skenario") or [])}
        done = [s for sid, s in solves.items() if sid in t_ids]
        if done:
            acc = round(sum(1 for s in done if s["correct"]) / len(done) * 100)
        else:
            acc = None
        track_acc.append({"code": t["code"], "name": t["name"], "emoji": t["emoji"],
                          "done": len(done), "acc": acc})
    diff_acc = []
    for diff in ("mudah", "sedang", "sulit"):
        ids_diff = {s["id"] for b in curriculum.get_babs() for s in (b.get("skenario") or []) if s.get("sulit") == diff}
        done = [s for sid, s in solves.items() if sid in ids_diff]
        if done:
            acc = round(sum(1 for s in done if s["correct"]) / len(done) * 100)
        else:
            acc = None
        diff_acc.append({"name": diff, "done": len(done), "acc": acc})
    # XP per hari (14 hari terakhir) — dari solves ber-created_at
    act = db.activity_dates(user["id"], days=14)
    today = datetime.now(db.WIB).date()
    days = []
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        days.append({"date": d, "n": act.get(d, 0), "max": max(act.values()) if act else 0})
    # Best streak dari 30 hari aktivitas
    act30 = db.activity_dates(user["id"], days=60)
    best = cur = 0
    d = today
    for i in range(60):
        key = (d - timedelta(days=i)).isoformat()
        if act30.get(key):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    lessons_n = len(db.get_lesson_done(user["id"]))
    exam_n = db.exam_count(user["id"])
    return render_template("analitik.html", solved_n=solved_n, correct_n=correct_n,
                           acc=round(correct_n / solved_n * 100) if solved_n else 0,
                           soal_n=len(soal_solved_set), lessons_n=lessons_n,
                           exam_n=exam_n,
                           tracks=track_acc, diffs=diff_acc, days=days,
                           best_streak=best, journal_n=db.journal_stats(user["id"])["n"])


# ---------- Backtest Lab (data pasar NYATA) ----------

LAB_DEFAULTS = {"asset": "TLKM", "strategy": "ma", "fast": 10, "slow": 30,
                "period": 14, "buy": 30, "sell": 70, "k": 2, "window": 20,
                "fee": 0.15}


@app.route("/lab", methods=["GET", "POST"])
@login_required
def lab():
    result = None
    form = dict(LAB_DEFAULTS)
    if request.method == "POST":
        try:
            fee = float(request.form.get("fee", 0.15)) / 100
            if not (0 <= fee <= 0.05):
                raise ValueError
            params = {
                "fast": int(request.form.get("fast", 10)),
                "slow": int(request.form.get("slow", 30)),
                "period": int(request.form.get("period", 14)),
                "buy": float(request.form.get("buy", 30)),
                "sell": float(request.form.get("sell", 70)),
                "k": float(request.form.get("k", 2)),
                "window": int(request.form.get("window", 20)),
            }
            r = market.run_lab(request.form.get("asset", "TLKM"),
                               request.form.get("strategy", "ma"), params, fee)
            if "error" in r:
                result = r
            else:
                result = {**r, "fee_pct": fee * 100}
            for k, v in request.form.items():
                if k in form:
                    form[k] = v
        except (ValueError, TypeError):
            result = {"error": "Parameter tidak valid."}
    assets = market.available()
    return render_template("lab.html", assets=assets, result=result,
                           strategies=market.STRATEGIES, form=form)


@app.route("/lab/export")
@login_required
def lab_export():
    import csv
    import io
    try:
        fee = float(request.args.get("fee", 0.15)) / 100
        params = {
            "fast": int(request.args.get("fast", 10)),
            "slow": int(request.args.get("slow", 30)),
            "period": int(request.args.get("period", 14)),
            "buy": float(request.args.get("buy", 30)),
            "sell": float(request.args.get("sell", 70)),
            "k": float(request.args.get("k", 2)),
            "window": int(request.args.get("window", 20)),
        }
        r = market.run_lab(request.args.get("asset", "TLKM"),
                           request.args.get("strategy", "ma"), params, fee)
        if "error" in r:
            abort(400)
    except (ValueError, TypeError):
        abort(400)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["entry_date", "exit_date", "entry_price", "exit_price", "return_pct"])
    for t in r["trades"]:
        w.writerow([t["entry"], t["exit"], t["entry_px"], t["exit_px"], t["ret"]])
    resp = app.response_class(buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=lab-{r['sym']}-{r['strategy']}.csv"
    return resp


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Halaman tidak ditemukan."), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, msg=str(e)), 400


# ---------- Mentor AI ----------

_mentor_rl: dict[int, list[float]] = {}


def _mentor_rl_ok(uid: int) -> bool:
    """Rate limit per user (in-memory, per worker): 8/menit, 40/jam."""
    now = time.time()
    ts = _mentor_rl.setdefault(uid, [])
    ts[:] = [x for x in ts if now - x < 3600]
    if len([x for x in ts if now - x < 60]) >= 8 or len(ts) >= 40:
        return False
    ts.append(now)
    return True


def _ctx_from_args():
    """Parse ?bab=N&sid=sX-Y dari GET/POST. Return (bab_n, sid, bab, scen, scen_solved)."""
    bab_n = 0
    sid = None
    try:
        bab_n = int(request.args.get("bab") or request.form.get("bab") or 0)
    except (TypeError, ValueError):
        bab_n = 0
    sid = request.args.get("sid") or request.form.get("sid") or None
    bab = curriculum.get_bab(bab_n) if bab_n else None
    scen = curriculum.get_scenario(sid) if sid else None
    scen_solved = False
    if scen and bab_n:
        uid = _user()["id"]
        scen_solved = sid in db.solved_ids(uid)
    return bab_n, sid, bab, scen, scen_solved


@app.route("/mentor")
@login_required
def mentor_page():
    bab_n, sid, bab, scen, _ = _ctx_from_args()
    ctx_name = None
    if scen:
        ctx_name = f"Bab {bab_n}: {scen['data']['judul']}"
    elif bab:
        ctx_name = f"{bab.get('emoji', '')} Bab {bab_n}: {bab.get('judul', '')}"
    history = db.mentor_history(_user()["id"], 40)
    return render_template("mentor.html", ctx_bab=bab_n, ctx_sid=sid,
                           ctx_name=ctx_name, history=history)


@app.route("/mentor/send", methods=["POST"])
@login_required
def mentor_send():
    user = _user()
    uid = user["id"]
    if not _mentor_rl_ok(uid):
        return {"error": "Santai dulu — maksimal 8 pesan per menit."}, 429
    msg = (request.form.get("msg") or "").strip()
    if not msg:
        return {"error": "Tulis pesan dulu."}, 400
    if len(msg) > 500:
        return {"error": "Pesan maksimal 500 karakter."}, 400

    bab_n, sid, bab, scen, scen_solved = _ctx_from_args()
    if sid and not scen:
        return {"error": "Skenario tidak ditemukan."}, 400

    db.mentor_add(uid, "user", msg, bab_n or None)
    rows = db.mentor_history(uid, 12)
    history = [
        {"role": "assistant" if r["role"] == "mentor" else "user", "content": r["content"]}
        for r in rows
    ]
    system = mentor.build_system(bab, scen, scen_solved)
    reply = mentor.call_mentor(system, history, msg)
    if not reply:
        return {"error": "Mentor sedang sibuk — coba lagi sebentar lagi."}, 503
    db.mentor_add(uid, "mentor", reply, bab_n or None)
    return {"reply": reply}


@app.route("/mentor/clear", methods=["POST"])
@login_required
def mentor_clear():
    db.mentor_clear(_user()["id"])
    return {"ok": True}


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

        content_type = [None]

        def start_response_wrapper(status, headers, exc_info=None):
            for k, v in headers:
                if k.lower() == "content-type" and content_type[0] is None:
                    content_type[0] = v
            if via_funnel:
                headers = [
                    (k, self.prefix + v)
                    if (k.lower() == "location" and v.startswith("/") and not v.startswith(self.prefix))
                    else (k, v)
                    for k, v in headers
                ]
            return start_response(status, headers, exc_info)

        app_iter = self.app(environ, start_response_wrapper)
        if via_funnel and content_type[0] and "text/html" in content_type[0]:
            # Buffer + rewrite path absolut hardcoded (fetch, href, src, action)
            body = b"".join(app_iter)
            text = body.decode("utf-8", "replace")
            text = re.sub(r"""(fetch\(\s*['"])/""", r"\g<1>" + self.prefix + "/", text)
            text = re.sub(r"""(href|src|action)="/(?!quant/|pykode/|buku-kas/)""",
                          r"\g<1>=\"" + self.prefix + "/", text)
            return [text.encode("utf-8")]
        return app_iter


app.wsgi_app = SubPathMiddleware(app.wsgi_app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5200, debug=True)
