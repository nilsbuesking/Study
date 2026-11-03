# Study

Personal study texts, read aloud. Currently a private audio feed (unlisted, not in any podcast directory) with one episode per chapter of *The Practical Historian*. A phone reading app is planned.

## Layout

| Path | What it is |
|---|---|
| `content/<text>/chNN.md` | The texts, one Markdown file per chapter (the master copy) |
| `tools/import_docx.py` | Word file to chapter Markdown (needs pandoc) |
| `tools/render_audio.py` | Chapter Markdown to m4a with section chapter markers, using Kokoro (British voice `bf_isabella`, German names via `tools/pronunciations.json`) |
| `tools/pronunciations.json` | Word-to-respelling fixes applied before speech, e.g. German names |
| `tools/build_feed.py` | Builds `podcast/feed.xml` and the landing page from `podcast/episodes.json` |
| `podcast/` | What GitHub Pages publishes: feed, cover, audio |

## Listening

Open `https://nilsbuesking.github.io/Study/podcast/` on the iPhone for the feed address, then Apple Podcasts: Library, the ⋯ menu, Follow a Show by URL.

## Adding a chapter

1. `python3 tools/render_audio.py content/practical-historian/ch02.md podcast/audio <model_dir>`
2. Add an entry to `podcast/episodes.json`
3. `python3 tools/build_feed.py`, then commit and push.

The site is public but unlisted. GitHub Pages limits a published site to about 1 GB; audio is about 12 MB per 35 minutes.
