"""Split a handbook .docx into one Markdown file per chapter.
Usage: python3 tools/import_docx.py <file.docx> <out_dir>
Needs pandoc. Chapters are the level-1 headings; text before Chapter 1 becomes preface.md."""
import re, subprocess, sys, pathlib

src, out = sys.argv[1], pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
md = subprocess.run(["pandoc", src, "-t", "markdown-smart", "--wrap=none"], capture_output=True, text=True, check=True).stdout
md = md.replace("\\'", "'").replace('\\"', '"').replace("\\>", ">")
md = re.sub(r"^> ", "> ", md, flags=re.M)

parts = re.split(r"\n(?=# )", md)
for i, part in enumerate(parts):
    m = re.match(r"# Chapter (\d+)\b", part)
    name = f"ch{int(m.group(1)):02d}.md" if m else ("title.md" if i == 0 else f"part{i}.md")
    if i == 0:
        name = "preface.md"
    (out / name).write_text(part.strip() + "\n", encoding="utf-8")
    print(name, len(part.split()), "words")
