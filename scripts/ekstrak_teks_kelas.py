#!/usr/bin/env python3
"""ekstrak_teks_kelas.py — dump semua teks materi bootcamp (PDF + ipynb + md) ke data/kelas_teks/.

Sumber (read-only):
  - ~/rakamin/Rakamin Data Science Bootcamp  (37 PDF, 10 modul)
  - ~/pacmann_robot/Pacmann                 (229 PDF + 7 ipynb, 4 kursus)

Output: ~/quantlab/data/kelas_teks/<track>/<rel>.txt + laporan _laporan.json
"""
import json
import subprocess
from pathlib import Path

ROOTS = [
    ("rakamin", Path("/home/yuan/rakamin/Rakamin Data Science Bootcamp")),
    ("pacmann", Path("/home/yuan/pacmann_robot/Pacmann")),
]
DST = Path("/home/yuan/quantlab/data/kelas_teks")
DST.mkdir(parents=True, exist_ok=True)

stats = {"pdf": 0, "ipynb": 0, "md": 0, "chars_total": 0, "kecil": [], "gagal": []}

for track, root in ROOTS:
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        suf = f.suffix.lower()
        if suf not in (".pdf", ".ipynb", ".md"):
            continue
        rel = f.relative_to(root)
        out = DST / track / rel.with_suffix(".txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        teks = ""
        try:
            if suf == ".pdf":
                subprocess.run(["pdftotext", "-q", str(f), str(out)], timeout=120)
                teks = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
                stats["pdf"] += 1
            elif suf == ".ipynb":
                nb = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                bagian = []
                for i, c in enumerate(nb.get("cells", [])):
                    src = c.get("source") or []
                    if isinstance(src, str):
                        src = [src]
                    isi = "".join(src).strip()
                    if not isi:
                        continue
                    tag = "KODE" if c.get("cell_type") == "code" else "MARKDOWN"
                    bagian.append(f"=== sel {i} [{tag}] ===\n{isi}")
                teks = "\n\n".join(bagian)
                out.write_text(teks, encoding="utf-8")
                stats["ipynb"] += 1
            else:
                teks = f.read_text(encoding="utf-8", errors="replace")
                out.write_text(teks, encoding="utf-8")
                stats["md"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["gagal"].append({"file": str(f), "err": str(exc)[:120]})
            continue
        n = len(teks.strip())
        stats["chars_total"] += n
        if n < 400:
            stats["kecil"].append({"file": str(rel), "track": track, "chars": n})

(DST / "_laporan.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"PDF: {stats['pdf']} · ipynb: {stats['ipynb']} · md: {stats['md']}")
print(f"total karakter teks: {stats['chars_total']:,} (~{stats['chars_total']//4:,} kata)")
print(f"file teks < 400 char (perlu OCR?): {len(stats['kecil'])}")
for k in stats["kecil"][:25]:
    print("  -", k["track"], k["file"], k["chars"])
if stats["gagal"]:
    print("GAGAL:", stats["gagal"][:10])
