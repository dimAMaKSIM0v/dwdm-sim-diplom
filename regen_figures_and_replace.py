# -*- coding: utf-8 -*-
from pathlib import Path
import hashlib
import zipfile
import io
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

base = Path(r"C:\Users\dimam\Desktop\diplom_V_nir\PROTO")
assets = base / "doc_assets"

# 1) Compute md5 of current (bad) images
bad_md5_to_name = {}
for name in ["fig_dwdm_system.png", "fig_itu_grid.png", "fig_architecture.png"]:
    p = assets / name
    if not p.exists():
        raise SystemExit(f"Missing {p}")
    data = p.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    bad_md5_to_name[md5] = name

# 2) Regenerate figures with Cyrillic-friendly font
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["font.size"] = 10

# Fig 1: DWDM system
fig, ax = plt.subplots(figsize=(10, 3.2), dpi=150)
ax.set_axis_off()
ax.set_xlim(0, 10)
ax.set_ylim(0, 3)
ax.text(5, 2.7, "Типовая DWDM‑система", ha="center", va="center", fontsize=12, weight="bold")

boxes = [
    (0.5, 1.1, 1.6, 0.8, "TX\n(передатчик)"),
    (2.5, 1.1, 1.2, 0.8, "MUX"),
    (4.2, 1.1, 3.0, 0.8, "Линия + EDFA"),
    (7.6, 1.1, 1.2, 0.8, "DEMUX"),
    (9.1, 1.1, 1.6, 0.8, "RX\n(приемник)"),
]
for x, y, w, h, label in boxes:
    ax.add_patch(Rectangle((x, y), w, h, facecolor="#E8F2FF", edgecolor="#4B6A88", linewidth=1.0))
    ax.text(x + w/2, y + h/2, label, ha="center", va="center")

# arrows
for (x1, y1, w1, h1, _), (x2, y2, _, _, _) in zip(boxes[:-1], boxes[1:]):
    ax.add_patch(FancyArrowPatch((x1 + w1, y1 + h1/2), (x2, y2 + h1/2), arrowstyle="->", mutation_scale=12, linewidth=1.0, color="#4B6A88"))

fig.tight_layout()
fig.savefig(assets / "fig_dwdm_system.png", bbox_inches="tight")
plt.close(fig)

# Fig 2: ITU grid
fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
ax.set_title("Сетка ITU‑T для DWDM (C‑band)")
ax.set_xlim(191.5, 196.5)
ax.set_ylim(0, 1)

# channels every 0.1 THz (100 GHz)
freqs = [191.6 + i*0.1 for i in range(int((196.4-191.6)/0.1)+1)]
for f in freqs:
    ax.plot([f, f], [0.2, 0.8], color="#2C6DB2", linewidth=1.0)

# reference 193.1 THz
ax.plot([193.1, 193.1], [0.1, 0.9], color="#D43F3A", linewidth=1.2)
ax.text(193.1, 0.92, "193.1 ТГц", color="#D43F3A", ha="center", va="bottom", fontsize=9)

ax.set_xlabel("Частота, ТГц")
ax.set_yticks([])
ax.text(194.5, 0.05, "шаг 100 ГГц", ha="center", va="bottom", fontsize=9)

fig.tight_layout()
fig.savefig(assets / "fig_itu_grid.png", bbox_inches="tight")
plt.close(fig)

# Fig 3: Architecture
fig, ax = plt.subplots(figsize=(8.5, 4.4), dpi=150)
ax.set_axis_off()
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.text(5, 5.6, "Архитектура приложения", ha="center", va="center", fontsize=12, weight="bold")

# Left GUI box
ax.add_patch(Rectangle((0.5, 3.7), 2.8, 1.2, facecolor="#E8F7E8", edgecolor="#5A7B5A", linewidth=1.0))
ax.text(1.9, 4.3, "GUI (PyQt5)\nMapWidget, MainWindow", ha="center", va="center", fontsize=9)

# Core box
ax.add_patch(Rectangle((3.8, 3.7), 5.6, 1.2, facecolor="#E8F2FF", edgecolor="#4B6A88", linewidth=1.0))
ax.text(6.6, 4.3, "Ядро", ha="center", va="center", fontsize=10)

# Models, Calculators, Managers, Utils
boxes2 = [
    (4.0, 2.2, 2.6, 1.0, "Модели\nNetwork/Node/Fiber/Channel"),
    (7.0, 2.2, 2.2, 1.0, "Калькуляторы\nLoss/EDFA/Plan"),
    (4.0, 0.8, 2.6, 1.0, "Менеджеры\nTopology/Simulation"),
    (7.0, 0.8, 2.2, 1.0, "Утилиты\nJSON/Export"),
]
for x, y, w, h, label in boxes2:
    ax.add_patch(Rectangle((x, y), w, h, facecolor="#FFFFFF", edgecolor="#4B6A88", linewidth=1.0))
    ax.text(x + w/2, y + h/2, label, ha="center", va="center", fontsize=8.5)

# arrows from Core
ax.add_patch(FancyArrowPatch((6.6, 3.7), (5.3, 3.2), arrowstyle="->", mutation_scale=10, linewidth=1.0, color="#4B6A88"))
ax.add_patch(FancyArrowPatch((6.6, 3.7), (8.1, 3.2), arrowstyle="->", mutation_scale=10, linewidth=1.0, color="#4B6A88"))
ax.add_patch(FancyArrowPatch((5.3, 2.2), (5.3, 1.8), arrowstyle="->", mutation_scale=10, linewidth=1.0, color="#4B6A88"))
ax.add_patch(FancyArrowPatch((8.1, 2.2), (8.1, 1.8), arrowstyle="->", mutation_scale=10, linewidth=1.0, color="#4B6A88"))

fig.tight_layout()
fig.savefig(assets / "fig_architecture.png", bbox_inches="tight")
plt.close(fig)

# 3) Replace images inside the DOCX by matching old md5
src_doc = Path(r"C:\Users\dimam\Desktop\NIR_updated_v5.docx")
out_doc = Path(r"C:\Users\dimam\Desktop\NIR_updated_v6.docx")

# New image bytes
new_bytes_by_name = {}
for name in ["fig_dwdm_system.png", "fig_itu_grid.png", "fig_architecture.png"]:
    new_bytes_by_name[name] = (assets / name).read_bytes()

with zipfile.ZipFile(src_doc, 'r') as zin:
    with zipfile.ZipFile(out_doc, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("word/media/"):
                md5 = hashlib.md5(data).hexdigest()
                if md5 in bad_md5_to_name:
                    name = bad_md5_to_name[md5]
                    data = new_bytes_by_name[name]
            zout.writestr(item, data)

print(str(out_doc))
