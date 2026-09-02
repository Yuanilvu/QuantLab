"""QuantLab — Database: users, solves, streak, XP, anti brute-force login."""
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "quantlab.db")
WIB = timezone(timedelta(hours=7))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_active TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS solves (
    user_id INTEGER NOT NULL,
    scenario_id TEXT NOT NULL,
    choice INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, scenario_id)
);
CREATE TABLE IF NOT EXISTS login_failures (
    ip TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0,
    first_ts TEXT
);
CREATE TABLE IF NOT EXISTS lesson_done (
    user_id INTEGER NOT NULL,
    lesson_id TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS soal_solved (
    user_id INTEGER NOT NULL,
    soal_id TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, soal_id)
);
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tanggal TEXT NOT NULL,
    aset TEXT NOT NULL,
    arah TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    size REAL NOT NULL DEFAULT 1,
    hasil REAL NOT NULL,
    emosi TEXT DEFAULT '',
    catatan TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS exam_pass (
    user_id INTEGER NOT NULL,
    track TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    passed_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, track)
);
CREATE TABLE IF NOT EXISTS review_schedule (
    user_id INTEGER NOT NULL,
    scenario_id TEXT NOT NULL,
    stage INTEGER NOT NULL DEFAULT 1,
    due_date TEXT NOT NULL,
    last_correct INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, scenario_id)
);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def today_wib():
    return datetime.now(WIB).date().isoformat()


# ---------- Auth ----------

def register_user(username, password):
    from werkzeug.security import generate_password_hash
    username = username.strip()
    if not re.match(r"^[A-Za-z0-9_]{3,20}$", username):
        return None, "Username 3-20 karakter (huruf/angka/underscore)."
    if len(password) < 6:
        return None, "Password minimal 6 karakter."
    try:
        with get_conn() as conn:
            dup = conn.execute(
                "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?)", (username,)
            ).fetchone()
            if dup:
                return None, "Username sudah dipakai."
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
        return True, "ok"
    except sqlite3.IntegrityError:
        return None, "Username sudah dipakai."


def verify_login(username, password):
    from werkzeug.security import check_password_hash
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),)
        ).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return row
    return None


def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_name(username):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
        ).fetchone()


def update_xp(user_id, xp):
    with get_conn() as conn:
        conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?", (xp, user_id))


# ---------- Anti brute-force (DB-backed, GLOBAL antar worker) ----------

LOCK_LIMIT = 5
LOCK_WINDOW = 300  # detik

def login_failures_check(ip):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count, first_ts FROM login_failures WHERE ip = ?", (ip,)
        ).fetchone()
    if not row:
        return 0
    try:
        first = datetime.strptime(row["first_ts"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0
    if (datetime.utcnow() - first).total_seconds() > LOCK_WINDOW:
        return 0
    return row["count"]


def login_failures_incr(ip):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO login_failures (ip, count, first_ts) VALUES (?, 1, ?)
               ON CONFLICT(ip) DO UPDATE SET count = count + 1""",
            (ip, now),
        )
        row = conn.execute("SELECT count FROM login_failures WHERE ip = ?", (ip,)).fetchone()
    return row["count"]


def login_failures_reset(ip):
    with get_conn() as conn:
        conn.execute("DELETE FROM login_failures WHERE ip = ?", (ip,))


# ---------- Progress / XP / Streak ----------

def add_solve(user_id, scenario_id, choice, correct, xp):
    """Simpan jawaban (first-solve only via PK). Update XP + streak. Return (inserted, new_streak)."""
    today = today_wib()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO solves (user_id, scenario_id, choice, correct, xp) VALUES (?, ?, ?, ?, ?)",
            (user_id, scenario_id, choice, 1 if correct else 0, xp),
        )
        inserted = cur.rowcount > 0
        if inserted:
            row = conn.execute(
                "SELECT streak, last_active FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            last = row["last_active"]
            if last == today:
                streak = row["streak"]
            elif last == (datetime.now(WIB).date() - timedelta(days=1)).isoformat():
                streak = row["streak"] + 1
            else:
                streak = 1
            # XP HANYA untuk jawaban benar; streak tetap dihitung utk aktivitas
            if correct:
                conn.execute(
                    "UPDATE users SET xp = xp + ?, streak = ?, last_active = ? WHERE id = ?",
                    (xp, streak, today, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET streak = ?, last_active = ? WHERE id = ?",
                    (streak, today, user_id),
                )
        else:
            streak = conn.execute(
                "SELECT streak FROM users WHERE id = ?", (user_id,)
            ).fetchone()["streak"]
    return inserted, streak


def get_solves(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM solves WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r["scenario_id"]: r for r in rows}


def solved_ids(user_id):
    return set(get_solves(user_id).keys())


def leaderboard(limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, xp, streak FROM users ORDER BY xp DESC, streak DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return rows


def user_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def total_solves():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM solves").fetchone()["c"]


# ---------- Pelajaran (XP "Saya Paham") ----------

LESSON_XP = 5

def lesson_done_add(user_id, lesson_id):
    """Tandai pelajaran selesai (sekali saja). Return (inserted, xp)."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO lesson_done (user_id, lesson_id, xp) VALUES (?, ?, ?)",
            (user_id, lesson_id, LESSON_XP),
        )
        if cur.rowcount:
            conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?", (LESSON_XP, user_id))
            return True, LESSON_XP
        return False, 0


def get_lesson_done(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT lesson_id FROM lesson_done WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r["lesson_id"] for r in rows}


# ---------- Profil ----------

def change_password(user_id, old_pass, new_pass):
    from werkzeug.security import check_password_hash, generate_password_hash
    user = get_user(user_id)
    if not user or not check_password_hash(user["password_hash"], old_pass):
        return False, "Password lama salah."
    if len(new_pass) < 6:
        return False, "Password baru minimal 6 karakter."
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_pass), user_id),
        )
    return True, "ok"


def activity_dates(user_id, days=30):
    """Heatmap: WIB date -> jumlah solve (30 hari terakhir)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT created_at FROM solves WHERE user_id = ?", (user_id,)
        ).fetchall()
    out = {}
    today = datetime.now(WIB).date()
    for r in rows:
        try:
            ts = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
            ts = ts.replace(tzinfo=timezone.utc).astimezone(WIB)
        except ValueError:
            continue
        d = ts.date()
        if (today - d).days < days:
            out[d.isoformat()] = out.get(d.isoformat(), 0) + 1
    return out


# ---------- Soal coding ----------

def soal_solved_add(user_id, soal_id, xp):
    """Tandai soal coding lolos (first-AC only). Return (inserted, xp)."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO soal_solved (user_id, soal_id, xp) VALUES (?, ?, ?)",
            (user_id, soal_id, xp),
        )
        if cur.rowcount:
            conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?", (xp, user_id))
            return True, xp
        return False, 0


def get_soal_solved(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT soal_id FROM soal_solved WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r["soal_id"] for r in rows}


# ---------- Jurnal Trading ----------

def journal_add(user_id, data):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO journal_entries
               (user_id, tanggal, aset, arah, entry_price, exit_price, size, hasil, emosi, catatan)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, data["tanggal"], data["aset"], data["arah"],
             data["entry_price"], data["exit_price"], data["size"], data["hasil"],
             data["emosi"], data["catatan"]),
        )
        return cur.lastrowid


def journal_list(user_id, limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM journal_entries WHERE user_id = ?
               ORDER BY tanggal DESC, id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def journal_delete(user_id, entry_id):
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM journal_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )
        return cur.rowcount > 0


def journal_stats(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM journal_entries WHERE user_id = ?", (user_id,)
        ).fetchall()
    n = len(rows)
    if n == 0:
        return {"n": 0, "win": 0, "win_rate": 0, "total_pnl": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "best": 0.0, "worst": 0.0}
    wins = [r["hasil"] for r in rows if r["hasil"] > 0]
    losses = [r["hasil"] for r in rows if r["hasil"] < 0]
    return {
        "n": n,
        "win": len(wins),
        "win_rate": round(len(wins) / n * 100),
        "total_pnl": round(sum(r["hasil"] for r in rows), 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "best": round(max(r["hasil"] for r in rows), 2),
        "worst": round(min(r["hasil"] for r in rows), 2),
    }


# ---------- Mode Ujian ----------

EXAM_PASS_BONUS = 50

def exam_passed(user_id, track):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM exam_pass WHERE user_id = ? AND track = ?",
            (user_id, track),
        ).fetchone()


def exam_record(user_id, track, score, total):
    """Catat kelulusan ujian (sekali per track). Return (inserted, bonus)."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO exam_pass (user_id, track, score, total) VALUES (?, ?, ?, ?)",
            (user_id, track, score, total),
        )
        if cur.rowcount:
            conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?",
                         (EXAM_PASS_BONUS, user_id))
            return True, EXAM_PASS_BONUS
        return False, 0


def exam_count(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) c FROM exam_pass WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]


# ---------- Ulasan Cerdas (spaced repetition 1/3/7 hari) ----------

REVIEW_INTERVALS = [1, 3, 7]   # hari antar tahap

def review_schedule_add(user_id, scenario_id):
    """Jadwalkan ulasan pertama (hari+1) saat skenario pertama kali diselesaikan."""
    due = (datetime.now(WIB).date() + timedelta(days=1)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO review_schedule (user_id, scenario_id, stage, due_date) VALUES (?, ?, 1, ?)",
            (user_id, scenario_id, due),
        )


def review_due(user_id):
    """Daftar ulasan yang jatuh tempo hari ini."""
    today = datetime.now(WIB).date().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT scenario_id, stage FROM review_schedule WHERE user_id = ? AND due_date <= ? ORDER BY due_date",
            (user_id, today),
        ).fetchall()
    return [{"scenario_id": r["scenario_id"], "stage": r["stage"]} for r in rows]


def review_count_due(user_id):
    return len(review_due(user_id))


def review_answer(user_id, scenario_id, correct):
    """Proses jawaban ulasan. Return (graduated, stage_baru)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT stage FROM review_schedule WHERE user_id = ? AND scenario_id = ?",
            (user_id, scenario_id),
        ).fetchone()
        if not row:
            return False, 0
        stage = row["stage"]
        today = datetime.now(WIB).date()
        if correct:
            if stage >= len(REVIEW_INTERVALS):
                conn.execute("DELETE FROM review_schedule WHERE user_id = ? AND scenario_id = ?",
                             (user_id, scenario_id))
                return True, 0
            due = (today + timedelta(days=REVIEW_INTERVALS[stage])).isoformat()
            conn.execute(
                "UPDATE review_schedule SET stage = ?, due_date = ?, last_correct = 1 WHERE user_id = ? AND scenario_id = ?",
                (stage + 1, due, user_id, scenario_id),
            )
            return False, stage + 1
        due = (today + timedelta(days=1)).isoformat()
        conn.execute(
            "UPDATE review_schedule SET stage = 1, due_date = ?, last_correct = 0 WHERE user_id = ? AND scenario_id = ?",
            (due, user_id, scenario_id),
        )
        return False, 1
