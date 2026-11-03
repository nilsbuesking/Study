"""Render one chapter Markdown file to an m4a with section chapter markers.
Usage: python3 tools/render_audio.py <chapter.md> <out_dir> <model_dir> [voice]
Model files: kokoro-v1.0.onnx and voices-v1.0.bin in <model_dir>
(from https://github.com/thewh1teagle/kokoro-onnx/releases, model-files-v1.0).
Spoken text rules live in speakable(); respellings in tools/pronunciations.json."""
import json, os, pathlib, re, subprocess, sys, time
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

md_path, out_dir, model_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
voice = sys.argv[4] if len(sys.argv) > 4 else "bf_isabella"
SR, SKIP = 24000, re.compile(r"further reading|glossary", re.I)
PRON = json.loads((pathlib.Path(__file__).parent / "pronunciations.json").read_text())
GERMAN = re.compile(r"\b(" + "|".join(map(re.escape, PRON["german"])) + r")('s|\u2019s)?\b")
NUM = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def num(n):
    return NUM[n] if n < 10 else str(n)


def speakable(s):
    s = re.sub(r"\*+|_(?=\w)|(?<=\w)_", "", s)                         # emphasis markers
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)                     # links
    s = re.sub(r"\b([1-9])\.(\d{1,2})\b",                               # section cross-references
              lambda m: f"section {NUM[int(m[1])]} point {num(int(m[2]))}", s)
    s = re.sub(r"\((\d{4})\)", r", \1,", s)                             # (1845) -> , 1845,
    s = re.sub(r"(\d{4})[–—-](\d{2})\b", r"\1 to \2", s)      # 1936-38
    s = re.sub(r"(\d{4})[–-](\d{4})", r"\1 to \2", s)
    for word, respell in PRON["respell"].items():
        s = re.sub(rf"\b{re.escape(word)}\b", respell, s)
    return s.replace("’", "'").replace("“", '"').replace("”", '"').strip()


def synth(k, text):
    """Render one sentence. Names listed under "german" get German sound rules, the rest British English,
    joined at phoneme level so the sentence keeps one intonation line."""
    if not GERMAN.search(text):
        return k.create(text, voice=voice, speed=1.0, lang="en-gb")
    ph, pos = [], 0
    for m in GERMAN.finditer(text):
        if text[pos:m.start()].strip():
            ph.append(k.tokenizer.phonemize(text[pos:m.start()], "en-gb"))
        ph.append(k.tokenizer.phonemize(m.group(1), "de") + ("s" if m.group(2) else ""))
        pos = m.end()
    if text[pos:].strip():
        ph.append(k.tokenizer.phonemize(text[pos:], "en-gb"))
    phonemes = " ".join(ph)
    if len(phonemes) > 500:                       # too long for one pass: fall back to plain English
        return k.create(text, voice=voice, speed=1.0, lang="en-gb")
    return k.create(phonemes, voice=voice, speed=1.0, lang="en-gb", is_phonemes=True)


def sentences(p):
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", p) if x.strip()]


# --- parse the chapter into (section title, [paragraphs]) ---
sections, cur = [], None
for line in md_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("# "):
        title = re.sub(r"^# Chapter (\d+)\s*[—-]+\s*", r"Chapter \1. ", line[2:]).strip()
        sections.append({"title": title, "spoken": title, "paras": [], "skip": False}); cur = sections[-1]
    elif line.startswith("## "):
        t = line[3:].strip(); m = re.match(r"(\d+)\.(\d+)\s+(.*)", t)
        spoken = f"Section {NUM[int(m[1])]} point {num(int(m[2]))}. {m[3]}." if m else t
        sections.append({"title": t, "spoken": spoken, "paras": [], "skip": bool(SKIP.search(t))}); cur = sections[-1]
    elif line.strip() and cur is not None:
        text = re.sub(r"^\s*[-*]\s+|^>\s*", "", line).strip()
        if text:
            cur["paras"].append(text)

k = Kokoro(f"{model_dir}/kokoro-v1.0.onnx", f"{model_dir}/voices-v1.0.bin")
gap = lambda s: np.zeros(int(s * SR), np.float32)
chunks, t, timings, marks = [], 0.0, [], []
t0 = time.time()
for si, sec in enumerate(sections):
    if sec["skip"]:
        continue
    marks.append((sec["title"], t))
    todo = [(sec["spoken"], 1.0)] + [(p, 0.7) for p in sec["paras"]]
    for ti, (text, pause_after) in enumerate(todo):
        for sj, sent in enumerate(sentences(text) if ti else [text]):
            a, sr = synth(k, speakable(sent))
            timings.append([si, ti, sj, round(t, 2), round(t + len(a) / SR, 2)])
            chunks.append(a.astype(np.float32)); t += len(a) / SR
            chunks.append(gap(0.25)); t += 0.25
        chunks.append(gap(pause_after)); t += pause_after
    print(f"{sec['title'][:50]:50s} {t / 60:5.1f} min  (render {time.time() - t0:.0f}s)", flush=True)

out_dir.mkdir(parents=True, exist_ok=True)
stem = md_path.stem
wav, meta, m4a = out_dir / f"{stem}.wav", out_dir / f"{stem}.ffmeta", out_dir / f"{stem}.m4a"
sf.write(wav, np.concatenate(chunks), SR)
ends = [m[1] for m in marks[1:]] + [t]
with open(meta, "w", encoding="utf-8") as f:
    f.write(";FFMETADATA1\n")
    for (title, start), end in zip(marks, ends):
        f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(start * 1000)}\nEND={int(end * 1000)}\ntitle={title}\n")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-i", str(meta), "-map_metadata", "1",
                "-ac", "1", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(m4a)], check=True)
json.dump({"voice": voice, "duration": round(t, 2), "timings": timings}, open(out_dir / f"{stem}.timings.json", "w"))
wav.unlink(); meta.unlink()
print(f"{m4a.name}: {t / 60:.1f} min, {os.path.getsize(m4a) / 1e6:.1f} MB")
