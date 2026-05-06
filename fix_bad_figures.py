# -*- coding: utf-8 -*-
from pathlib import Path
import zipfile
import io
from PIL import Image

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

base = Path(r"C:\Users\dimam\Desktop\diplom_V_nir\PROTO")
assets = base / "doc_assets"

# Regenerate figures at exact sizes to match doc embedded dimensions
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["font.size"] = 18

# fig_dwdm_system: 2000x700
fig, ax = plt.subplots(figsize=(10, 3.5), dpi=200)
ax.set_axis_off()
ax.set_xlim(0, 10)
ax.set_ylim(0, 3.5)
ax.text(5, 3.1, "Типовая DWDM‑система", ha="center", va="center", fontsize=22, weight="bold")

boxes = [
    (0.4, 1.2, 1.8, 0.9, "TX\n(передатчик)"),
    (2.6, 1.2, 1.3, 0.9, "MUX"),
    (4.3, 1.2, 3.1, 0.9, "Линия + EDFA"),
    (7.8, 1.2, 1.3, 0.9, "DEMUX"),
    (9.3, 1.2, 1.8, 0.9, "RX\n(приемник)"),
]
for x, y, w, h, label in boxes:
    ax.add_patch(Rectangle((x, y), w, h, facecolor="#E8F2FF", edgecolor="#4B6A88", linewidth=2.0))
    ax.text(x + w/2, y + h/2, label, ha="center", va="center", fontsize=16)

for (x1, y1, w1, h1, _), (x2, y2, _, _, _) in zip(boxes[:-1], boxes[1:]):
    ax.add_patch(FancyArrowPatch((x1 + w1, y1 + h1/2), (x2, y2 + h1/2), arrowstyle="->", mutation_scale=20, linewidth=2.0, color="#4B6A88"))

fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
fig.savefig(assets / "fig_dwdm_system.png")
plt.close(fig)

# fig_itu_grid: 1600x640
plt.rcParams["font.size"] = 14
fig, ax = plt.subplots(figsize=(8, 3.2), dpi=200)
ax.set_title("Сетка ITU‑T для DWDM (C‑band)", fontsize=18, pad=10)
ax.set_xlim(191.5, 196.5)
ax.set_ylim(0, 1)

freqs = [191.6 + i*0.1 for i in range(int((196.4-191.6)/0.1)+1)]
for f in freqs:
    ax.plot([f, f], [0.2, 0.8], color="#2C6DB2", linewidth=1.5)

ax.plot([193.1, 193.1], [0.1, 0.9], color="#D43F3A", linewidth=2.0)
ax.text(193.1, 0.92, "193.1 ТГц", color="#D43F3A", ha="center", va="bottom", fontsize=12)

ax.set_xlabel("Частота, ТГц", fontsize=14)
ax.set_yticks([])
ax.text(194.5, 0.05, "шаг 100 ГГц", ha="center", va="bottom", fontsize=12)

fig.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.2)
fig.savefig(assets / "fig_itu_grid.png")
plt.close(fig)

# fig_architecture: 2000x800
plt.rcParams["font.size"] = 14
fig, ax = plt.subplots(figsize=(10, 4), dpi=200)
ax.set_axis_off()
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.text(5, 5.6, "Архитектура приложения", ha="center", va="center", fontsize=20, weight="bold")

# GUI box
ax.add_patch(Rectangle((0.4, 3.7), 2.9, 1.2, facecolor="#E8F7E8", edgecolor="#5A7B5A", linewidth=2.0))
ax.text(1.85, 4.3, "GUI (PyQt5)\nMapWidget, MainWindow", ha="center", va="center", fontsize=12)

# Core box
ax.add_patch(Rectangle((3.6, 3.7), 6.0, 1.2, facecolor="#E8F2FF", edgecolor="#4B6A88", linewidth=2.0))
ax.text(6.6, 4.3, "Ядро", ha="center", va="center", fontsize=14)

# Sub boxes
sub_boxes = [
    (3.8, 2.2, 2.8, 1.0, "Модели\nNetwork/Node/Fiber/Channel"),
    (7.0, 2.2, 2.4, 1.0, "Калькуляторы\nLoss/EDFA/Plan"),
    (3.8, 0.8, 2.8, 1.0, "Менеджеры\nTopology/Simulation"),
    (7.0, 0.8, 2.4, 1.0, "Утилиты\nJSON/Export"),
]
for x, y, w, h, label in sub_boxes:
    ax.add_patch(Rectangle((x, y), w, h, facecolor="#FFFFFF", edgecolor="#4B6A88", linewidth=2.0))
    ax.text(x + w/2, y + h/2, label, ha="center", va="center", fontsize=11)

# arrows
ax.add_patch(FancyArrowPatch((6.6, 3.7), (5.2, 3.2), arrowstyle="->", mutation_scale=18, linewidth=2.0, color="#4B6A88"))
ax.add_patch(FancyArrowPatch((6.6, 3.7), (8.2, 3.2), arrowstyle="->", mutation_scale=18, linewidth=2.0, color="#4B6A88"))
ax.add_patch(FancyArrowPatch((5.2, 2.2), (5.2, 1.8), arrowstyle="->", mutation_scale=18, linewidth=2.0, color="#4B6A88"))
ax.add_patch(FancyArrowPatch((8.2, 2.2), (8.2, 1.8), arrowstyle="->", mutation_scale=18, linewidth=2.0, color="#4B6A88"))

fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
fig.savefig(assets / "fig_architecture.png")
plt.close(fig)

# Replace images inside NIR_updated_v2.docx based on exact image sizes
src_doc = Path(r"C:\Users\dimam\Desktop\NIR_updated_v2.docx")
out_doc = Path(r"C:\Users\dimam\Desktop\NIR_updated_v2_fixed_images.docx")

size_to_new = {
    (2000, 700): (assets / "fig_dwdm_system.png").read_bytes(),
    (1600, 640): (assets / "fig_itu_grid.png").read_bytes(),
    (2000, 800): (assets / "fig_architecture.png").read_bytes(),
}

with zipfile.ZipFile(src_doc, 'r') as zin:
    with zipfile.ZipFile(out_doc, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("word/media/") and item.filename.lower().endswith('.png'):
                im = Image.open(io.BytesIO(data))
                if im.size in size_to_new:
                    data = size_to_new[im.size]
            zout.writestr(item, data)

print(str(out_doc))
