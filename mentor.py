"""mentor.py — Mentor AI QuantLab: DeepSeek API + fallback hermes -z.

Pola sama seperti Coach Tracbit (validated): key dibaca dari env, lalu dari
file env Hermes (hidden dotfile, satu user). Tidak ada secret di file ini.
"""
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.deepseek.com/v1"
API_MODEL = os.environ.get("QL_AI_MODEL", "deepseek-v4-flash")
HERMES_ENV = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / ".env"

SYSTEM_CORE = """Kamu adalah **Mentor QuantLab** — pembimbing belajar trading kuantitatif yang sabar, untuk trader berpengalaman yang TIDAK ngoding (belajar Python lewat kasus pasar; main Bybit funding carry; akrab dengan TLKM/BBRI/BRPT/CUAN/TPIA/ALII/MPPA/IHSG).

Aturan menjawab:
1. Bahasa Indonesia santai, kalimat pendek (maks ~20 kata), tidak menggurui, tidak kekanak-kanakan.
2. Jawaban maksimal ~160 kata. Kalau perlu panjang, tawarkan lanjutan ("mau aku jabarin lebih dalam?").
3. Selalu utamakan ANGKA & hitungan konkret, bukan teori. Hindari mental math — tulis hitungannya.
4. Kalau relevan, tunjukkan logika Python singkat (3-6 baris) sebagai terjemahan keputusan — user belajar baca kode lewat contoh nyata.
5. User suka analogi sehari-hari dan contoh dari dunianya (funding Bybit, saham IDX).
6. Kalau user menanyakan skenario yang sedang dipelajari: BIMBING dulu dengan pertanyaan/angka pancingan (1 langkah). Kalau user tetap minta jawaban/konfirmasi, berikan jawaban + hitungan + alasan singkat — tujuan akhirnya user paham.
7. Jangan menyebut bahwa kamu AI/model; kamu mentor pribadinya.
8. Format: markdown ringan (bold, list, kode pendek). Jangan pakai heading besar.

Bila ada blok "KONTEKS BAB" atau "KONTEKS SKENARIO" di bawah, jawablah dalam kerangka itu. Blok "RIWAYAT PERCAKAPAN" hanya konteks — jangan ulangi. Balas langsung ke pertanyaan user terakhir."""


def _get_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    try:
        for line in HERMES_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _clean(content: str) -> str:
    if not content:
        return ""
    content = re.sub(r"Here's a thinking process:.*", "", content, flags=re.S)
    content = re.sub(r"<thinking>.*?</thinking>", "", content, flags=re.S)
    return content.strip()


def _call_api(system: str, history: list[dict], user_msg: str, timeout: int = 55) -> str | None:
    messages = [{"role": "system", "content": system}]
    messages += history[-8:]
    messages.append({"role": "user", "content": user_msg})
    body = json.dumps({
        "model": API_MODEL,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + _get_key(),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    reply = _clean(data["choices"][0]["message"].get("content") or "")
    return reply or None


def _call_hermes(system: str, user_msg: str) -> str | None:
    prompt = f"{system}\n\nPertanyaan user: {user_msg}".replace("\n", " ")[:1500]
    try:
        proc = subprocess.run(
            ["hermes", "-z", prompt],
            capture_output=True, text=True, timeout=90,
        )
        out = (proc.stdout or "").strip()
        return out or None
    except Exception:
        return None


def call_mentor(system: str, history: list[dict], user_msg: str) -> str | None:
    """DeepSeek dulu; kalau gagal/tidak ada key, fallback hermes -z."""
    if _get_key():
        try:
            reply = _call_api(system, history, user_msg)
            if reply:
                return reply
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, KeyError, json.JSONDecodeError):
            pass
    return _call_hermes(system, user_msg)


def build_context(bab: dict | None, scenario: dict | None, scenario_solved: bool) -> str:
    """Susun konteks dari kurikulum. Untuk skenario yang BELUM dikerjakan user,
    jangan bocorkan pilihan/jawaban — mentor membimbing, bukan memberi spoiler."""
    parts = []
    if bab:
        lines = [f"KONTEKS BAB {bab['bab']} — {bab['judul']} ({bab.get('emoji', '')})",
                 f"Deskripsi: {bab.get('deskripsi', '')}"]
        for pel in bab.get("pelajaran") or []:
            materi = (pel.get("materi") or "").strip()
            cap = materi[:1600]
            tag = "" if len(cap) == len(materi) else "\n(potongan materi — tanya kalau butuh bagian lengkap)"
            lines.append(f"\nPelajaran {pel['id']} — {pel.get('judul', '')}:\n{cap}{tag}")
        parts.append("\n".join(lines))
    if scenario:
        sc = scenario["data"] if isinstance(scenario, dict) and "data" in scenario else scenario
        lines = [f"\nKONTEKS SKENARIO {sc['id']} — {sc.get('emoji', '')} {sc.get('judul', '')}",
                 f"Cerita kasus:\n{(sc.get('cerita') or '').strip()[:1200]}"]
        if scenario_solved:
            pil = sc.get("pilihan") or []
            jwb = sc.get("jawaban")
            penjelasan = (sc.get("penjelasan") or "").strip()
            lines.append("\n(User SUDAH mengerjakan skenario ini, jadi aman dibahas:)")
            lines.append("Pilihan: " + " | ".join(str(p) for p in pil))
            if isinstance(jwb, int) and 0 <= jwb < len(pil):
                lines.append(f"Jawaban benar: indeks {jwb} — {pil[jwb]}")
            lines.append(f"Penjelasan:\n{penjelasan[:1200]}")
        else:
            lines.append("\n(User BELUM mengerjakan skenario ini — bimbing tanpa menyebut jawaban benar.)")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def build_system(bab: dict | None, scenario: dict | None, scenario_solved: bool) -> str:
    ctx = build_context(bab, scenario, scenario_solved)
    return SYSTEM_CORE + ("\n\n" + ctx if ctx else "")
