"""Build feed.xml and index.html for one show from its episodes.json and audio files.
Usage: python3 tools/build_feed.py [show_dir]      (default: podcast, i.e. The Practical Historian)
episodes.json: title, description, author, language, category, base_url, guid_prefix, optional subtitle,
optional pub_step_hours (default 24: one day apart; all dates must stay in the past),
and episodes: [{"file": "audio/x.m4a", "title", "description", optional "season", optional "type": "bonus"}].
Duration and size are read from the file; the publication date is fixed per position so order never changes."""
import datetime as dt, email.utils, json, os, pathlib, subprocess, sys
from xml.sax.saxutils import escape

repo = pathlib.Path(__file__).resolve().parent.parent
root = repo / (sys.argv[1] if len(sys.argv) > 1 else "podcast")
cfg = json.loads((root / "episodes.json").read_text(encoding="utf-8"))
BASE = cfg["base_url"].rstrip("/") + "/"
GUID = cfg.get("guid_prefix", "study")
start = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)  # well in the past: apps hide future-dated episodes

items = []
for n, ep in enumerate(cfg["episodes"], 1):
    f = root / ep["file"]
    if not f.exists():
        continue
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True, check=True).stdout)
    h, m, s = int(secs // 3600), int(secs % 3600 // 60), int(secs % 60)
    items.append({**ep, "n": n, "size": os.path.getsize(f), "dur": f"{h:02d}:{m:02d}:{s:02d}", "mins": round(secs / 60)})

x = lambda s: escape(s, {'"': "&quot;"})
rss = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">',
       "<channel>", f'<atom:link href="{BASE}feed.xml" rel="self" type="application/rss+xml"/>', f"<title>{x(cfg['title'])}</title>",
       f"<link>{BASE}</link>", f"<language>{cfg['language']}</language>",
       f"<description>{x(cfg['description'])}</description>", f"<itunes:author>{x(cfg['author'])}</itunes:author>",
       f"<itunes:summary>{x(cfg['description'])}</itunes:summary>", '<itunes:type>serial</itunes:type>',
       "<itunes:explicit>false</itunes:explicit>",
       f'<itunes:image href="{BASE}cover.jpg"/>', f'<itunes:category text="{x(cfg["category"])}"/>']
if cfg.get("subtitle"):
    rss.append(f"<itunes:subtitle>{x(cfg['subtitle'])}</itunes:subtitle>")
for ep in items:
    pub = email.utils.format_datetime(start + dt.timedelta(hours=ep["n"] * cfg.get("pub_step_hours", 24)))
    bonus = ep.get("type") == "bonus"
    rss += ["<item>", f"<title>{x(ep['title'])}</title>", f"<description>{x(ep['description'])}</description>",
            f'<enclosure url="{BASE}{ep["file"]}" length="{ep["size"]}" type="audio/x-m4a"/>',
            f'<guid isPermaLink="false">{GUID}-{pathlib.Path(ep["file"]).stem}</guid>', f"<pubDate>{pub}</pubDate>",
            f"<itunes:duration>{ep['dur']}</itunes:duration>"]
    if "season" in ep:
        rss.append(f"<itunes:season>{ep['season']}</itunes:season>")
    if not bonus:
        rss.append(f"<itunes:episode>{ep.get('number', ep['n'])}</itunes:episode>")
    rss += [f"<itunes:episodeType>{'bonus' if bonus else 'full'}</itunes:episodeType>", "<itunes:explicit>false</itunes:explicit>", "</item>"]
rss += ["</channel>", "</rss>"]
(root / "feed.xml").write_text("\n".join(rss) + "\n", encoding="utf-8")

rows = "".join(f"<li><b>{x(e['title'])}</b><span>{e['mins']} min · {e['size'] / 1e6:.1f} MB</span></li>" for e in items)
(root / "index.html").write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{x(cfg['title'])}</title><style>
body{{font:18px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:24px 18px;max-width:34rem;margin-inline:auto;background:#f7f8f6;color:#1b2230}}
@media(prefers-color-scheme:dark){{body{{background:#0e1116;color:#e4e7ec}}code{{background:#1c2a3a}}li{{border-color:#2a303a}}}}
h1{{font-size:26px;line-height:1.2}}code{{display:block;padding:12px;background:#e3ecf5;border-radius:10px;word-break:break-all;font-size:15px;user-select:all}}
ul{{list-style:none;padding:0}}li{{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid #dadde2}}li span{{color:#6b7482;white-space:nowrap}}
</style></head><body><h1>{x(cfg['title'])}</h1><p>Add this address in Apple Podcasts: Library, then the ⋯ menu, then Follow a Show by URL.</p>
<code>{BASE}feed.xml</code><ul>{rows}</ul></body></html>
""", encoding="utf-8")
print(f"{root.relative_to(repo)}: {len(items)} episode(s) in feed")
