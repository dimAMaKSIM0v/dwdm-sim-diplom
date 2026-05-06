# -*- coding: utf-8 -*-
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out_path = Path(r"C:\Users\dimam\Desktop\diplom_V_nir\PROTO\doc_assets\fig_architecture.png")

W, H = 2000, 900
img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img)

# Fonts (Cyrillic-capable)
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

font_title = load_font(52)
font_box = load_font(30)
font_small = load_font(24)

# Title
TITLE = "Архитектура приложения и взаимодействие модулей"
bbox = draw.textbbox((0,0), TITLE, font=font_title)
text_w = bbox[2]-bbox[0]
draw.text(((W - text_w)//2, 40), TITLE, fill="black", font=font_title)

# Colors
box_fill_gui = (232, 247, 232)
box_fill_core = (232, 242, 255)
box_fill = (255, 255, 255)
outline = (75, 106, 136)

# Helper to draw box with centered multiline text

def draw_box(x, y, w, h, text, fill):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=10, fill=fill, outline=outline, width=4)
    lines = text.split("\n")
    line_sizes = []
    for line in lines:
        bb = draw.textbbox((0,0), line, font=font_box)
        line_sizes.append((bb[2]-bb[0], bb[3]-bb[1]))
    total_h = sum(hh for _, hh in line_sizes) + (len(lines)-1)*6
    cy = y + (h - total_h)//2
    for (line, (lw, lh)) in zip(lines, line_sizes):
        cx = x + (w - lw)//2
        draw.text((cx, cy), line, fill="black", font=font_box)
        cy += lh + 6

# Layout
# Top row
gui = (120, 170, 520, 150)
core = (760, 170, 1120, 150)

# Middle row
models = (220, 420, 520, 140)
managers = (760, 400, 480, 180)
calculators = (1340, 420, 520, 140)

# Bottom row
utils = (1340, 620, 520, 140)

# Draw boxes
 draw_box(*gui, "GUI (PyQt5)\nMapWidget, MainWindow", box_fill_gui)
 draw_box(*core, "Ядро", box_fill_core)
 draw_box(*models, "Модели\nNetwork/Node/Fiber/Channel", box_fill)
 draw_box(*managers, "Менеджеры\nTopology/Simulation", box_fill)
 draw_box(*calculators, "Калькуляторы\nLoss/EDFA/Plan", box_fill)
 draw_box(*utils, "Утилиты\nJSON/Export", box_fill)

# Arrow helper

def arrow(start, end, both=False):
    draw.line([start, end], fill=outline, width=4)
    # arrow head at end
    def head(pt, direction):
        x, y = pt
        dx, dy = direction
        length = (dx*dx + dy*dy) ** 0.5
        if length == 0:
            return
        ux, uy = dx/length, dy/length
        ah = 16
        perp = (-uy, ux)
        p1 = (x, y)
        p2 = (x - ux*ah + perp[0]*ah*0.6, y - uy*ah + perp[1]*ah*0.6)
        p3 = (x - ux*ah - perp[0]*ah*0.6, y - uy*ah - perp[1]*ah*0.6)
        draw.polygon([p1, p2, p3], fill=outline)
    head(end, (end[0]-start[0], end[1]-start[1]))
    if both:
        head(start, (start[0]-end[0], start[1]-end[1]))

# Connections
# GUI -> Core
arrow((gui[0]+gui[2], gui[1]+gui[3]//2), (core[0], core[1]+core[3]//2))
# Core -> Managers
arrow((core[0]+core[2]//2, core[1]+core[3]), (managers[0]+managers[2]//2, managers[1]))
# Managers <-> Models
arrow((managers[0], managers[1]+managers[3]//2), (models[0]+models[2], models[1]+models[3]//2), both=True)
# Managers <-> Calculators
arrow((managers[0]+managers[2], managers[1]+managers[3]//2), (calculators[0], calculators[1]+calculators[3]//2), both=True)
# Managers <-> Utils
arrow((managers[0]+managers[2]//2, managers[1]+managers[3]), (utils[0]+utils[2]//2, utils[1]), both=True)

# Labels near arrows
# GUI->Core label
draw.text((430, 250), "команды / события", fill=outline, font=font_small)
# Core->Managers
draw.text((1040, 330), "оркестрация", fill=outline, font=font_small)
# Managers<->Models
draw.text((540, 470), "данные", fill=outline, font=font_small)
# Managers<->Calculators
draw.text((1180, 470), "расчёты", fill=outline, font=font_small)
# Managers<->Utils
draw.text((1120, 680), "загрузка / экспорт", fill=outline, font=font_small)

out_path.parent.mkdir(parents=True, exist_ok=True)
img.save(out_path)
print(str(out_path))
