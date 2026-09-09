"""mentor.py — Mentor AI QuantLab: Hermes Agent (hermes -z) satu-satunya backend.

Keputusan user (9 Sep 2026): mentor = HERMES 100%. DeepSeek API tidak dipakai
lagi. Kalau Hermes gagal/timeout → balas pesan error ramah, bukan jawaban dari
model lain. History percakapan ikut dikirim (riwayat dari DB, 10 pesan terakhir)
supaya Hermes inget konteks obrolan.
"""
import re
import subprocess

SYSTEM_CORE = """Kamu adalah **Hermes — Mentor QuantLab**: asisten pribadi Yuan (yang juga mengelola vault Obsidian, cron, dan server rumahnya) yang sedang berperan sebagai mentor belajar trading kuantitatif di aplikasi QuantLab.

Kesepakatan belajar dengan Yuan (WAJIB dipatuhi):
1. Anggap Yuan TIDAK paham rumus matematika sama sekali — mulai dari bahasa manusia sehari-hari + contoh uang/koin/angka konkret, BARU ke istilah dan kode. Jangan pakai notasi (Σ, ∂, formula) tanpa menjelaskan dari nol.
2. Bahasa Indonesia santai, kalimat pendek (maks ~20 kata), tidak menggurui, tidak kekanak-kanakan.
3. Jawaban maksimal ~160 kata. Kalau perlu panjang, tawarkan lanjutan ("mau aku jabarin lebih dalam?").
4. Utamakan ANGKA & hitungan konkret — tulis hitungannya, jangan minta mental math.
5. Kalau relevan, tunjukkan logika Python singkat (3-6 baris) sebagai terjemahan — Yuan belajar baca kode lewat contoh nyata.
6. Istilah teknis (volatilitas, EV, likuidasi, drawdown, dsb) wajib di-gloss dengan analogi sehari-hari saat pertama muncul.
7. Skenario yang sedang dipelajari: BIMBING dulu dengan pertanyaan/angka pancingan (1 langkah). Kalau user tetap minta jawaban/konfirmasi, berikan jawaban + hitungan + alasan singkat — tujuan akhirnya user paham.
8. Format: markdown ringan (bold, list, kode pendek). Jangan pakai heading besar.

Bila ada blok "KONTEKS BAB" atau "KONTEKS SKENARIO" di bawah, jawablah dalam kerangka itu (jangan bocorkan jawaban skenario yang BELUM dikerjakan user). Blok "RIWAYAT PERCAKAPAN" hanya konteks — jangan diulangi. Balas langsung ke pertanyaan user terakhir."""


def _clean(content: str) -> str:
    """Buang preamble berpikir kalau ikut terlanjur, rapikan spasi."""
    if not content:
        return ""
    content = re.sub(r"Here's a thinking process:.*", "", content, flags=re.S)
    content = re.sub(r"<thinking>.*?</thinking>", "", content, flags=re.S)
    return content.strip()


def _call_hermes(system: str, history: list[dict], user_msg: str, timeout: int = 100) -> str | None:
    parts = [system]
    if history:
        parts.append("\n\nRIWAYAT PERCAKAPAN (konteks saja — jangan ulangi):")
        for h in history[-10:]:
            who = "User" if h.get("role") == "user" else "Mentor"
            text = (h.get("content") or "").strip().replace("\n", " ")
            parts.append(f"{who}: {text[:500]}")
    parts.append(f"\n\nPertanyaan terakhir user:\n{user_msg}")
    prompt = "\n".join(parts)
    if len(prompt) > 14000:
        prompt = prompt[:14000]
    try:
        proc = subprocess.run(
            ["hermes", "-z", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        return _clean(proc.stdout or "") or None
    except subprocess.TimeoutExpired:
        _log("hermes timeout")
        return None
    except Exception as e:  # noqa: BLE001 — apa pun penyebabnya, jangan crash route
        _log(f"hermes gagal: {type(e).__name__}")
        return None


def _log(msg: str) -> None:
    print(f"[mentor] {msg}", flush=True)


def call_mentor(system: str, history: list[dict], user_msg: str) -> str:
    """Hermes adalah satu-satunya backend (keputusan user). Gagal → pesan error."""
    import time
    t0 = time.time()
    reply = _call_hermes(system, history, user_msg)
    if reply:
        _log(f"hermes ok in {time.time()-t0:.1f}s")
        return reply
    _log(f"hermes gagal total dalam {time.time()-t0:.1f}s")
    return "⚠️ Mentor-nya lagi bermasalah (gagal merespons). Coba ulangi pesan lo sebentar lagi, ya."


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
