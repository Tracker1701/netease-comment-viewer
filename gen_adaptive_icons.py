#!/usr/bin/env python3
"""Generate density-specific adaptive icon layers for netease_kivy."""
import os
from PIL import Image, ImageDraw

PROJECT = r"D:\0user\PyWorkSpace\area\wyy\netease_kivy"
DRAW = os.path.join(PROJECT, "android", "res", "drawable")
MIPMAP = os.path.join(PROJECT, "android", "res")

# Adaptive icon layer sizes: 108dp x density
DENSITIES = {
    "mipmap-mdpi":       108,    # 108 * 1
    "mipmap-hdpi":       162,    # 108 * 1.5
    "mipmap-xhdpi":      216,    # 108 * 2
    "mipmap-xxhdpi":     324,    # 108 * 3
    "mipmap-xxxhdpi":    432,    # 108 * 4
}

def make_gradient_bg(size, corner_pct=0.18):
    """Create a pink-to-deep-red gradient rounded-square PNG."""
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    r = int(size * corner_pct)
    top_c = (255, 100, 119, 255)   # #FF6477
    bot_c = (232,  42,  76, 255)   # #E82A4C
    for y in range(size):
        t = y / size
        cr = int(top_c[0] + (bot_c[0] - top_c[0]) * t)
        cg = int(top_c[1] + (bot_c[1] - top_c[1]) * t)
        cb = int(top_c[2] + (bot_c[2] - top_c[2]) * t)
        draw.line([(0, y), (size - 1, y)], fill=(cr, cg, cb, 255))
    # rounded mask
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=r, fill=255
    )
    bg.putalpha(mask)
    return bg


src_fg = Image.open(os.path.join(DRAW, "ic_launcher_fg.png")).convert("RGBA")
src_bg = make_gradient_bg(1024)   # high-res source

for folder, px in DENSITIES.items():
    out_dir = os.path.join(MIPMAP, folder)
    os.makedirs(out_dir, exist_ok=True)
    fg = src_fg.resize((px, px), Image.Resampling.LANCZOS)
    bg = src_bg.resize((px, px), Image.Resampling.LANCZOS)
    fg.save(os.path.join(out_dir, "ic_launcher_fg.png"), "PNG")
    bg.save(os.path.join(out_dir, "ic_launcher_bg.png"), "PNG")
    print(f"  {folder}/ic_launcher_fg.png  ({px}x{px})")
    print(f"  {folder}/ic_launcher_bg.png  ({px}x{px})")

print("Done – adaptive icon layers generated for all densities.")
