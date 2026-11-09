# Study

Personal study texts, read aloud as private podcast feeds (unlisted, not in any podcast directory), one show per text. A phone reading app is planned.

| Show | Feed address |
|---|---|
| The Practical Historian | `https://nilsbuesking.github.io/Study/podcast/feed.xml` |
| A History of Christianity | `https://nilsbuesking.github.io/Study/podcast/christianity/feed.xml` |

Each show's landing page (the feed address without `feed.xml`) shows the address to copy. In Apple Podcasts: Library, the ⋯ menu, Follow a Show by URL.

## Layout

| Path | What it is |
|---|---|
| `content/<text>/*.md` | The texts, one Markdown file per chapter (the master copy) |
| `content/<text>/pronunciations.json` | Words read with German (`de`) or Classical Latin (`la`, with macron spellings) sound rules for that text |
| `tools/import_docx.py` | Word file with heading styles to chapter Markdown (needs pandoc) |
| `tools/import_overview.py` | Word file whose headings are bold lines (Parts, numbered chapters, annexes) to chapter Markdown |
| `tools/render_audio.py` | Chapter Markdown to m4a with section chapter markers, using Kokoro (British voice `bf_isabella`) |
| `tools/pronunciations.json` | Pronunciation lists that apply to every text |
| `tools/build_feed.py` | Builds a show's `feed.xml` and landing page from its `episodes.json` |
| `tools/make_cover.py` | Typographic cover in the house style |
| `podcast/` | The Practical Historian (feed, cover, audio); other shows in subfolders, e.g. `podcast/christianity/` |

## Adding an episode

1. `python3 tools/render_audio.py content/<text>/<chapter>.md <show_dir>/audio <model_dir>`
2. Make sure the episode is listed in `<show_dir>/episodes.json`
3. `python3 tools/build_feed.py <show_dir>`, then commit and push.

The site is public but unlisted. GitHub Pages limits a published site to about 1 GB; audio is about 0.38 MB per minute.
