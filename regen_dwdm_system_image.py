# -*- coding: utf-8 -*-
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out_path = Path(r"C:\Users\dimam\Desktop\diplom_V_nir\PROTO\doc_assets\fig_dwdm_system.png")

W, H = 2000, 700
img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img)

# Fonts (force a Cyrillic-capable font)
font_paths = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\times.ttf",
    r"C:\Windows\Fonts\DejaVuSans.ttf",
]

def load_font(size):
    for p in font_paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
    return ImageFont.load_default()

font_title = load_font(56)
font_box = load_font(34)

# Title
# Use normal hyphen to avoid special glyph issues
TITLE = "Типовая DWDM-система"

bbox = draw.textbbox((0, 0), TITLE, font=font_title)
text_w = bbox[2] - bbox[0]
draw.text(((W - text_w) // 2, 40), TITLE, fill="black", font=font_title)

# Box style
box_fill = (232, 242, 255)
box_outline = (75, 106, 136)

# Layout
box_h = 150
top_boxes = 260
widths = [280, 200, 520, 200, 280]
G = 70

total_w = sum(widths) + G * (len(widths) - 1)
start_x = (W - total_w) // 2

labels = [
    "TX\n(передатчик)",
    "MUX",
    "Линия + EDFA",
    "DEMUX",
    "RX\n(приемник)",
]

boxes = []
x = start_x
for w, label in zip(widths, labels):
    boxes.append((x, top_boxes, w, box_h, label))
    x += w + G

# Draw boxes and text
for x, y, w, h, label in boxes:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=box_fill, outline=box_outline, width=5)
    lines = label.split("\n")
    # center multiline text
    line_sizes = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font_box)
        line_sizes.append((bb[2]-bb[0], bb[3]-bb[1]))
    total_h = sum(hh for _, hh in line_sizes) + (len(lines)-1) * 6
    cy = y + (h - total_h)//2
    for (line, (lw, lh)) in zip(lines, line_sizes):
        cx = x + (w - lw)//2
        draw.text((cx, cy), line, fill="black", font=font_box)
        cy += lh + 6

# Arrows
for i in range(len(boxes) - 1):
    x1, y1, w1, h1, _ = boxes[i]
    x2, y2, w2, h2, _ = boxes[i + 1]
    start = (x1 + w1, y1 + h1 // 2)
    end = (x2, y2 + h2 // 2)
    draw.line([start, end], fill=box_outline, width=6)
    ah = 18
    draw.polygon([
        (end[0], end[1]),
        (end[0] - ah, end[1] - ah // 2),
        (end[0] - ah, end[1] + ah // 2),
    ], fill=box_outline)

out_path.parent.mkdir(parents=True, exist_ok=True)
img.save(out_path)
print(str(out_path))
