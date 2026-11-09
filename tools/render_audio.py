"""Render one chapter Markdown file to an m4a with section chapter markers.
Usage: python3 tools/render_audio.py <chapter.md> <out_dir> <model_dir> [voice]
Model files: kokoro-v1.0.onnx and voices-v1.0.bin in <model_dir>
(from https://github.com/thewh1teagle/kokoro-onnx/releases, model-files-v1.0).

Markdown: "# Part …" lines are announced before the next heading; "# X — Y" is spoken "X. Y";
"## 1.2 Title" is spoken "Section one point two. Title."; other "##" headings are spoken as they stand.
Spoken-text rules live in speakable(). Words that need other sound rules are listed in
tools/pronunciations.json plus an optional pronunciations.json next to the chapter: "de" (or "german")
for German; "la" for Classical Latin ({term: spelling with macrons}), read at "la_speed";
"ipa" for exact phonemes ({term: Kokoro IPA}); "respell" maps words to English respellings.
Needs the onnx package once, to make a copy of the model that accepts a speed per phoneme."""
import json, os, pathlib, re, subprocess, sys, time
import numpy as np, soundfile as sf, phonemizer, onnxruntime as ort
from kokoro_onnx import Kokoro
from kokoro_onnx.trim import trim as trim_audio

md_path, out_dir, model_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
voice = sys.argv[4] if len(sys.argv) > 4 else "bf_isabella"
SR, SKIP = 24000, re.compile(r"further reading|glossary", re.I)

# --- pronunciation lists: global, then the text's own ---
PRON = {"de": [], "la": {}, "ipa": {}, "respell": {}, "section_refs": True, "la_speed": 1.0}
for f in (pathlib.Path(__file__).parent / "pronunciations.json", md_path.parent / "pronunciations.json"):
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        PRON["de"] += d.get("de", []) + d.get("german", [])
        la = d.get("la", {})                    # list of terms, or {term: spelling with macrons}
        PRON["la"].update(la if isinstance(la, dict) else {w: w for w in la})
        PRON["ipa"].update(d.get("ipa", {}))
        PRON["respell"].update(d.get("respell", {}))
        for key in ("section_refs", "la_speed"):
            PRON[key] = d.get(key, PRON[key])
LANG = {w: "de" for w in PRON["de"]} | {w: "la" for w in PRON["la"]} | {w: "ipa" for w in PRON["ipa"]}
SPELL = dict(PRON["la"])                        # what the Latin rules actually read: vowel lengths fix stress
SPEED = {"la": PRON["la_speed"]}                # per-language speaking rate (1.0 = normal; lower is slower)
FOREIGN = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(LANG, key=len, reverse=True))) + r")(['’]s)?(?![\w-])") if LANG else None

# --- numbers ---
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
ORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
       11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth", 16: "sixteenth", 17: "seventeenth",
       18: "eighteenth", 19: "nineteenth", 20: "twentieth"}
DECADE = {0: "hundreds", 10: "tens", 20: "twenties", 30: "thirties", 40: "forties", 50: "fifties", 60: "sixties", 70: "seventies",
          80: "eighties", 90: "nineties"}


def words(n):                                   # 0-99
    return ONES[n] if n < 20 else TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")


def ordinal(n):
    return ORD[n] if n in ORD else TENS[n // 10] + "-" + ORD[n % 10] if n % 10 else TENS[n // 10][:-1] + "ieth"


def roman(s):
    v = {"I": 1, "V": 5, "X": 10, "L": 50}
    return sum(-v[c] if i + 1 < len(s) and v[c] < v[s[i + 1]] else v[c] for i, c in enumerate(s))


def year(n):                                    # 1000-2099 as spoken years
    hi, lo = divmod(n, 100)
    if 2000 <= n < 2010 or n == 1000:
        return None                             # "two thousand and five", "one thousand": the engine says these well
    if lo == 0:
        return f"{words(hi)} hundred"
    return f"{words(hi)} {'oh ' + ONES[lo] if lo < 10 else words(lo)}"


NUM = ONES[:10]
CARD_BEFORE = r"(?:Parts?|Vatican|Books?|Doctrine|Annex|War|Phase|Volume|Chapters?)"
I_NAMES = {"Theodosius", "Gregory", "Nicholas", "Constantine", "Innocent", "Celestine", "Leo", "Clovis", "Niketas", "Athenagoras",
           "Alexius", "Richard", "João", "Afonso", "Charles", "Henry", "Edward", "Elizabeth", "Mary", "James", "Francis", "Frederick"}
RN = r"(?:XX|X)?(?:IX|IV|V?I{1,3}|V|X)"
BOOKS = r"(Corinthians|Peter|John|Timothy|Thessalonians|Kings|Samuel|Chronicles|Maccabees|Enoch|Clement)"


def regnal(m):
    name, num = m[1], m[2]
    if num == "I" and name not in I_NAMES:
        return m[0]
    return f"{name} the {ordinal(roman(num)).capitalize()}"


def speakable(s):
    s = re.sub(r"\*+|_(?=\w)|(?<=\w)_", "", s)                         # emphasis markers
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)                     # links
    if PRON["section_refs"]:
        s = re.sub(r"\b([1-9])\.(\d{1,2})\b", lambda m: f"section {NUM[int(m[1])]} point {words(int(m[2]))}", s)
    s = re.sub(r"\b(\d+):(\d+)[–-](\d+):(\d+)\b", r"chapter \1, verse \2, to chapter \3, verse \4", s)   # John 7:53–8:11
    s = re.sub(r"\b(\d+):(\d+)[–-](\d+)\b", r"chapter \1, verses \2 to \3", s)
    s = re.sub(r"\b(\d+):(\d+)\b", r"chapter \1, verse \2", s)
    s = re.sub(rf"\b([123]) {BOOKS}\b", lambda m: f"{ORD[int(m[1])].capitalize()} {m[2]}", s)
    s = re.sub(r"\((\d{4})\)", r", \1,", s)                             # (1845) -> , 1845,
    s = re.sub(r"\bc\. ?(?=\d)", "circa ", s)
    s = re.sub(r"(\d)\s?[–—-]\s?(\d)", r"\1 to \2", s)                  # ranges: 1936–38, 93–94, 354–430
    s = re.sub(r"\b(1\d|20)(\d)0s\b", lambda m: "two thousands" if m[1] + m[2] == "200" else
               f"{words(int(m[1]))} {DECADE[int(m[2]) * 10]}", s)
    s = re.sub(r"(?<![\d,.£$])\b(1\d{3}|20\d\d)\b(?!\d|,\d)", lambda m: year(int(m[1])) or m[1], s)
    s = re.sub(rf"\b({CARD_BEFORE}) ({RN})(\s?[–-]\s?| to | through | and | or )({RN})\b",          # Parts V–VI, Books II through IV
               lambda m: f"{m[1]} {words(roman(m[2]))} {'to' if '–' in m[3] or '-' in m[3] else m[3].strip()} {words(roman(m[4]))}", s)
    s = re.sub(rf"\b({CARD_BEFORE}) ({RN})\b(?=['’]s\b|[^\w'’]|$)", lambda m: f"{m[1]} {words(roman(m[2]))}", s)
    s = re.sub(rf"\b([A-Z][a-zà-ÿ]+) ({RN})\b(?=['’]s\b|[^\w'’-]|$)", regnal, s)
    s = re.sub(r"\bBCE\b", "B C E", s)
    s = re.sub(r"\bCE\b", "C E", s)
    s = re.sub(r"\bAD\b", "A D", s)
    s = s.replace(" / ", ", ")
    for word, respell in PRON["respell"].items():
        s = re.sub(rf"\b{re.escape(word)}\b", respell, s)
    return s.replace("’", "'").replace("“", '"').replace("”", '"').strip()


k = Kokoro(f"{model_dir}/kokoro-v1.0.onnx", f"{model_dir}/voices-v1.0.bin")
VAR = pathlib.Path(model_dir) / "kokoro-v1.0-varspeed.onnx"
if not VAR.exists():                            # same model, but its speed input takes one value per phoneme
    import onnx
    m = onnx.load(f"{model_dir}/kokoro-v1.0.onnx")
    next(i for i in m.graph.input if i.name == "speed").type.tensor_type.shape.dim[0].dim_param = "n_speed"
    onnx.save(m, str(VAR))
sess = ort.InferenceSession(str(VAR), providers=["CPUExecutionProvider"])
STYLE = k.get_voice_style(voice)
VOCAB = k.tokenizer.vocab
FIX = {"de": {"ʏ": "y"}}                        # sounds the voice lacks: short ü would otherwise be dropped


def phon(text, lang):
    if lang == "ipa":
        return "".join(c for c in text if c in VOCAB)
    p = phonemizer.phonemize(text, lang, preserve_punctuation=True, with_stress=True)
    for a, b in FIX.get(lang, {}).items():
        p = p.replace(a, b)
    return "".join(c for c in p if c in VOCAB).strip()


def infer(ph, sp):
    """One model pass over phonemes ph with a speaking rate per phoneme sp; silence trimmed as Kokoro does."""
    tok = [VOCAB[c] for c in ph]
    audio = sess.run(None, {"tokens": np.array([[0, *tok, 0]], dtype=np.int64),
                            "style": STYLE[min(len(tok), len(STYLE)) - 1].astype(np.float32),
                            "speed": np.array([1.0, *sp, 1.0], dtype=np.float32)})[0].ravel()
    return trim_audio(audio)[0]


def synth(text):
    """Render one sentence. Listed words get German, Latin or exact phonemes, the rest British English,
    joined at phoneme level so the sentence keeps one intonation line; Latin can be spoken more slowly."""
    segs, pos = [], 0
    for m in (FOREIGN.finditer(text) if FOREIGN else []):
        if text[pos:m.start()].strip():
            segs.append((phon(text[pos:m.start()], "en-gb"), 1.0))
        lang = LANG[m[1]]
        segs.append((phon(SPELL.get(m[1], m[1]), lang) + ("s" if m[2] else ""), SPEED.get(lang, 1.0)))
        pos = m.end()
    if text[pos:].strip():
        segs.append((phon(text[pos:], "en-gb"), 1.0))
    ph, sp = "", []
    for s, rate in segs:
        if ph:
            ph += " "; sp.append(1.0)
        ph += s; sp += [rate] * len(s)
    parts = []
    while len(ph) > 510:                        # the model's limit: split at the last pause mark, else the last space
        cut = max((ph.rfind(c, 0, 510) for c in ",;:—"), default=-1)
        cut = cut + 1 if cut > 100 else ph.rfind(" ", 0, 510) + 1 or 510
        parts.append(infer(ph[:cut].rstrip(), sp[:len(ph[:cut].rstrip())]))
        parts.append(np.zeros(int(0.1 * SR), np.float32))
        ph, sp = ph[cut:].lstrip(), sp[cut + (len(ph[cut:]) - len(ph[cut:].lstrip())):]
    parts.append(infer(ph, sp))
    return np.concatenate(parts), SR


def sentences(p):
    p = re.sub(r"\b(St|Dr|Mt|Mr|Fr)\. ", r"\1 ", p)
    p = p.replace("e.g. ", "for example, ").replace("i.e. ", "that is, ").replace("cf. ", "compare ")
    return [x for x in re.split(r"(?<=[.!?])(?<!\b[A-Z]\.)\s+(?=[A-Z“\"(])", p) if x.strip()]


# --- parse the chapter into (section title, spoken heading, [paragraphs]) ---
sections, cur, part = [], None, None
for line in md_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("# Part "):
        part = re.sub(r"\s*—\s*", ". ", line[2:].strip()) + "."
    elif line.startswith("# "):
        title = line[2:].strip()
        spoken = re.sub(r"^Chapter (\d+)\s*[—-]+\s*", r"Chapter \1. ", title)
        spoken = re.sub(r"\s+—\s+", ". ", spoken)
        title = re.sub(r"^Chapter (\d+)\s*[—-]+\s*", r"Chapter \1. ", title)
        sections.append({"title": title, "spoken": spoken, "pre": part, "paras": [], "skip": False}); cur = sections[-1]; part = None
    elif line.startswith("## "):
        t = line[3:].strip(); m = re.match(r"(\d+)\.(\d+)\s+(.*)", t)
        spoken = f"Section {NUM[int(m[1])]} point {words(int(m[2]))}. {m[3]}." if m else t
        sections.append({"title": t, "spoken": spoken, "pre": None, "paras": [], "skip": bool(SKIP.search(t))}); cur = sections[-1]
    elif line.strip() and cur is not None:
        text = re.sub(r"^\s*[-*]\s+|^>\s*", "", line).strip()
        if text:
            cur["paras"].append(text)

gap = lambda s: np.zeros(int(s * SR), np.float32)
chunks, t, timings, marks = [], 0.0, [], []
t0 = time.time()
for si, sec in enumerate(sections):
    if sec["skip"]:
        continue
    marks.append((sec["title"], t))
    todo = ([(sec["pre"], 1.0)] if sec["pre"] else []) + [(sec["spoken"], 1.0)] + [(p, 0.7) for p in sec["paras"]]
    n_head = len(todo) - len(sec["paras"])
    for ti, (text, pause_after) in enumerate(todo):
        for sj, sent in enumerate(sentences(text) if ti >= n_head else [text]):
            a, sr = synth(speakable(sent))
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
        title = title.replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
        f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(start * 1000)}\nEND={int(end * 1000)}\ntitle={title}\n")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-i", str(meta), "-map_metadata", "1",
                "-ac", "1", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(m4a)], check=True)
json.dump({"voice": voice, "duration": round(t, 2), "timings": timings}, open(out_dir / f"{stem}.timings.json", "w"))
wav.unlink(); meta.unlink()
print(f"{m4a.name}: {t / 60:.1f} min, {os.path.getsize(m4a) / 1e6:.1f} MB")
