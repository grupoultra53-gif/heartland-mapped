"""
Heartland Mapped — 16:9 High-CTR YouTube Thumbnail Compositor (1280x720, < 2 MB)
Renders razor-sharp 2-4 word mobile & Smart-TV readable typography onto clean AI artwork bases.
"""
import argparse
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in [r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\segoeuib.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def build_thumb(base_path: Path, out_path: Path, lines: list[tuple[str, tuple[int, int, int]]], badge: str | None = None):
    im = Image.open(base_path).convert("RGBA").resize((1280, 720), Image.Resampling.LANCZOS)
    ov = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    # Extra subtle left gradient scrim for ultra-crisp 160px mobile readability
    for x in range(620):
        a = int(125 * (1.0 - x / 620.0) ** 1.35)
        d.line([(x, 0), (x, 720)], fill=(12, 10, 8, a))

    x_left = 54
    y_cur = 96 if not badge else 148

    if badge:
        fb = load_font(42)
        bb = d.textbbox((0, 0), badge, font=fb)
        bw = (bb[2] - bb[0]) + 34
        bh = (bb[3] - bb[1]) + 18
        d.rounded_rectangle([x_left, 64, x_left + bw, 64 + bh], radius=8, fill=(196, 32, 26, 255), outline=(255, 255, 255, 220), width=3)
        d.text((x_left + 17, 68), badge, font=fb, fill=(255, 248, 232, 255))

    for text, color in lines:
        sz = 158 if len(text) <= 6 else (136 if len(text) <= 8 else 116)
        f = load_font(sz)
        # Soft drop shadow + thick black stroke
        d.text((x_left + 7, y_cur + 9), text, font=f, fill=(0, 0, 0, 195), stroke_width=14, stroke_fill=(0, 0, 0, 195))
        d.text((x_left, y_cur), text, font=f, fill=color + (255,), stroke_width=12, stroke_fill=(16, 12, 10, 255))
        tb = d.textbbox((0, 0), text, font=f)
        y_cur += (tb[3] - tb[1]) + 28

    out = Image.alpha_composite(im, ov).convert("RGB")
    out.save(out_path, "JPEG", quality=92, optimize=True)
    kb = out_path.stat().st_size / 1024.0
    print(f"Saved thumbnail: {out_path} ({out.size[0]}x{out.size[1]}, {kb:.1f} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_dir")
    args = ap.parse_args()
    ep = Path(args.episode_dir).resolve()
    # Complementary 3-word high-CTR copy (completes title "5 Midwest Border Fights That Almost Started Real Wars")
    lines = [
        ("REAL US", (255, 252, 242)),
        ("BORDER", (255, 214, 42)),
        ("WARS?", (255, 252, 242)),
    ]
    if (ep / "thumb_a_base.jpg").exists():
        build_thumb(ep / "thumb_a_base.jpg", ep / "thumbnail_a_pegdoll.jpg", lines, badge="1783 - 1892")
    if (ep / "thumb_b_base.jpg").exists():
        build_thumb(ep / "thumb_b_base.jpg", ep / "thumbnail_b_pure.jpg", lines, badge="1783 - 1892")
