"""Split an overview .docx whose headings are bold lines (not Word heading styles) into chapter Markdown.
Usage: python3 tools/import_overview.py <file.docx> <out_dir>
Recognised bold lines: "Part IV — Title" (announced at the start of its first chapter), "12. Title" (a chapter),
"Annex A: Title" (an annex), any other bold line (a section). Volume headers "<Book>, Part I–II: ..." are dropped.
Annexes listed in SKIP_ANNEX are left out; Annex C is split in two at its "The Fixed Feasts" section."""
import re, subprocess, sys, pathlib

SKIP_ANNEX = {"B"}                      # Further Reading
SPLIT_AT = {"C": "The Fixed Feasts"}    # annex letter -> section title that starts part two

src, out = sys.argv[1], pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
md = subprocess.run(["pandoc", src, "-t", "markdown-smart", "--wrap=none"], capture_output=True, text=True, check=True).stdout
md = md.replace("\\'", "'").replace('\\"', '"').replace("\\>", ">").replace("\\*", "")
lines = md.splitlines()
body = next(i for i, l in enumerate(lines) if re.match(r"^\*\*[^*]+, Part [IVX]+[–-][IVX]+: ", l))

files, cur, part, skipping = {}, None, None, False
for l in lines[body:]:
    b = re.fullmatch(r"\*\*(.+?)\*\*", l.strip())
    if b and "**" not in b[1]:
        h = b[1].strip()
        if re.match(r"^[^,]+, Part [IVX]+[–-][IVX]+: ", h):
            continue
        if m := re.match(r"^Part ([IVX]+) — (.+)$", h):
            part = f"# Part {m[1]} — {m[2]}"; continue
        if m := re.match(r"^(\d+)\. (.+)$", h):
            cur = f"ch{int(m[1]):02d}"; skipping = False
            files[cur] = ([part] if part else []) + [f"# Chapter {m[1]} — {m[2]}"]; part = None; continue
        if m := re.match(r"^Annex ([A-Z]): (.+)$", h):
            skipping = m[1] in SKIP_ANNEX
            if not skipping:
                cur = f"annex-{m[1].lower()}"; files[cur] = [f"# Annex {m[1]} — {m[2]}"]
            continue
        if skipping:
            continue
        letter = cur[-1].upper() if cur and cur.startswith("annex") else None
        if letter in SPLIT_AT and h.startswith(SPLIT_AT[letter]):
            title = files[cur][0].split(" — ", 1)[1]
            files[cur + "2"] = [f"# Annex {letter}, part two — {title}"]
            files[cur + "1"] = files.pop(cur); files[cur + "1"][0] = f"# Annex {letter}, part one — {title}"
            cur += "2"
        files[cur].append(f"## {h}")
    elif l.strip() and cur and not skipping:
        files[cur].append(l.strip())

for name, ls in files.items():
    text = "\n\n".join(ls) + "\n"
    (out / f"{name}.md").write_text(text, encoding="utf-8")
    print(f"{name}.md  {len(text.split()):6d} words")
