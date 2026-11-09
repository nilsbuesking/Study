"""Typographic 1600x1600 podcast cover in the house style (framed, serif, gold rule).
Usage: python3 tools/make_cover.py <out.jpg> <background hex> "<line>|<line>..." "<subtitle>" [small first line: 1]"""
import sys
from PIL import Image, ImageDraw, ImageFont

out, bg, lines, sub = sys.argv[1], sys.argv[2], sys.argv[3].split("|"), sys.argv[4]
small_first = len(sys.argv) > 5 and sys.argv[5] == "1"
W, GOLD, CREAM = 1600, "#d6b97a", "#f3efe4"
SERIF_B, SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
img = Image.new("RGB", (W, W), bg)
d = ImageDraw.Draw(img)
d.rectangle([150, 150, W - 150, W - 150], outline=GOLD, width=6)

fonts = []
for i, line in enumerate(lines):
    size = 150
    if small_first and i == 0:
        size = 90
    while ImageDraw.Draw(img).textlength(line, font=ImageFont.truetype(SERIF_B, size)) > W - 420:
        size -= 4
    fonts.append(ImageFont.truetype(SERIF_B, size))
heights = [f.getbbox("Hg")[3] + 40 for f in fonts]
y = (W - sum(heights)) // 2 - 80
for line, f, h in zip(lines, fonts, heights):
    d.text((W / 2, y), line, font=f, fill=CREAM, anchor="mt"); y += h
y += 40
d.line([W / 2 - 240, y, W / 2 + 240, y], fill=GOLD, width=5)
sf = ImageFont.truetype(SERIF, 54)
while d.textlength(sub, font=sf) > W - 420:
    sf = ImageFont.truetype(SERIF, sf.size - 2)
d.text((W / 2, y + 60), sub, font=sf, fill=GOLD, anchor="mt")
img.save(out, quality=90)
