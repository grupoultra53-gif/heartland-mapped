"""
Heartland Mapped — Episode 02: The Day Chicago Reversed a River (1900)
2.5D Historical Map Animation Renderer (720x1280, 30 FPS)
Uses .agents/skills/historical-map-animation/scripts/{engine_25d.py, foley_mixer.py}
"""
import json
import math
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

EP_DIR = Path(__file__).resolve().parent
PROJ_DIR = EP_DIR.parent.parent
SKILL_SCRIPTS = PROJ_DIR / ".agents" / "skills" / "historical-map-animation" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import engine_25d as eng
import foley_mixer as fm

W, H, FPS = 720, 1280, 30
SR = fm.SR


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
            r"C:\Windows\Fonts\impact.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    )
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---------- Custom Procedural Situational Foley Accents (zero loops) ----------

def foley_gavel_slam() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.linspace(0, 0.45, n, endpoint=False)
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(160, 46, n)) / SR) * np.exp(-t * 14.0)
    wood_crack = fm.bandpass(np.random.normal(0, 1, n), 450, 2600) * np.exp(-t * 28.0) * 0.78
    return (thud * 0.95 + wood_crack) * 0.88


def foley_cold_wind(duration: float = 3.8) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    gust = fm.bandpass(noise, 240, 1350) * (0.45 + 0.55 * np.sin(2 * np.pi * 0.42 * t))
    whistle_f = 520 + 85 * np.sin(2 * np.pi * 0.60 * t)
    whistle = np.sin(2 * np.pi * np.cumsum(whistle_f) / SR) * 0.13
    env = np.sin(np.pi * (t / duration)) ** 0.75
    return (gust * 0.34 + whistle) * env


def foley_pickaxe_clink() -> np.ndarray:
    n = int(0.38 * SR)
    t = np.linspace(0, 0.38, n, endpoint=False)
    ring = (
        np.sin(2 * np.pi * 2450 * t) * 0.5
        + np.sin(2 * np.pi * 3910 * t) * 0.35
        + np.sin(2 * np.pi * 5320 * t) * 0.2
    ) * np.exp(-t * 11.0)
    impact = fm.bandpass(np.random.normal(0, 1, n), 800, 4800) * np.exp(-t * 32.0) * 0.55
    return (ring * 0.55 + impact) * 0.75


def foley_dynamite_blast(duration: float = 1.45) -> np.ndarray:
    """Deep muffled TNT blast + crumbling limestone/earth debris."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    sub_boom = np.sin(2 * np.pi * np.cumsum(np.linspace(135, 34, n)) / SR) * np.exp(-t * 4.5) * 0.95
    blast_body = fm.lowpass(np.random.normal(0, 1, n), 360) * np.exp(-t * 3.8) * 1.1
    debris = fm.bandpass(np.random.normal(0, 1, n), 600, 3800) * np.exp(-np.maximum(0, t - 0.12) * 5.2)
    debris[: int(0.08 * SR)] *= np.linspace(0.2, 1.0, int(0.08 * SR))
    out = sub_boom + blast_body * 0.75 + debris * 0.42
    peak = np.max(np.abs(out))
    return (out / max(1e-6, peak)) * 0.92


def foley_river_rush(duration: float = 3.2) -> np.ndarray:
    """Surging water current swoosh for the reversed river flow."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    low_surge = fm.bandpass(noise, 140, 820) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.55 * t))
    foam = fm.bandpass(np.random.normal(0, 1, n), 950, 3400) * (0.40 + 0.40 * np.sin(2 * np.pi * 1.1 * t))
    env = np.sin(np.pi * (t / duration)) ** 0.7
    return (low_surge * 0.45 + foam * 0.25) * env


def foley_water_splash() -> np.ndarray:
    """Short wooden barrel dump + splash accent."""
    n = int(0.65 * SR)
    t = np.linspace(0, 0.65, n, endpoint=False)
    plop = np.sin(2 * np.pi * np.cumsum(np.linspace(240, 520, n)) / SR) * np.exp(-t * 14.0) * 0.55
    splash = fm.bandpass(np.random.normal(0, 1, n), 550, 4200) * np.exp(-t * 6.5) * 0.65
    return (plop + splash) * 0.78


def foley_storm_thunder(duration: float = 3.6) -> np.ndarray:
    """Rain patter + distant rolling 1885 Midwest thunderstorm rumble."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    rain = fm.bandpass(np.random.normal(0, 1, n), 1400, 6200) * 0.16 * (np.sin(np.pi * t / duration) ** 0.5)
    thunder_raw = fm.lowpass(np.random.normal(0, 1, n), 170)
    thunder_env = np.exp(-((t - 0.85) ** 2) / 0.28) + 0.55 * np.exp(-((t - 1.75) ** 2) / 0.55)
    thunder = thunder_raw * thunder_env * 1.35
    out = rain + thunder
    peak = np.max(np.abs(out))
    return (out / max(1e-6, peak)) * 0.80


def foley_stadium_swell(duration: float = 3.4) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    crowd = fm.bandpass(np.random.normal(0, 1, n), 240, 1900)
    low_roar = fm.lowpass(np.random.normal(0, 1, n), 320) * 0.5
    env = np.sin(np.pi * (t / duration)) ** 1.15
    return (crowd * 0.34 + low_roar * 0.22) * env


# ---------- Subtitle Chunk Builder (2-4 words, 50+ readable, preserves ? / !) ----------

def restore_question_and_excl_punctuation(scene_text: str, words: list) -> list:
    raw_tokens = re.findall(r"[A-Za-z0-9'\-]+|[?!.]", scene_text)
    punct_after = {}
    w_idx = 0
    for tok in raw_tokens:
        if tok in ("?", "!", "."):
            if w_idx > 0 and (w_idx - 1) not in punct_after:
                punct_after[w_idx - 1] = tok
        else:
            w_idx += 1

    enriched = []
    pos = 0
    for w in words:
        sub_count = len(re.findall(r"[A-Za-z0-9'\-]+", w["text"]))
        end_pos = pos + max(1, sub_count) - 1
        p = punct_after.get(end_pos, "")
        txt = w["text"]
        if p in ("?", "!") and not txt.endswith(p):
            txt = txt + p
        enriched.append(
            {
                "text": txt,
                "start": w["start"],
                "end": w["end"],
                "break_after": p in ("?", "!", "."),
            }
        )
        pos += max(1, sub_count)
    return enriched


def build_subtitle_cards(scenes_meta: list) -> list:
    cards = []
    for sc in scenes_meta:
        raw_words = sc.get("words", [])
        if not raw_words:
            continue
        words = restore_question_and_excl_punctuation(sc.get("text", ""), raw_words)
        i = 0
        while i < len(words):
            chunk = []
            while i < len(words) and len(chunk) < 3:
                chunk.append(words[i])
                i += 1
                if chunk[-1]["break_after"]:
                    break
            if len(chunk) == 3 and not chunk[-1]["break_after"] and i < len(words):
                rem = 0
                for k in range(i, len(words)):
                    rem += 1
                    if words[k]["break_after"]:
                        break
                if rem == 1:
                    chunk.append(words[i])
                    i += 1

            text = " ".join(w["text"] for w in chunk).strip()
            start = chunk[0]["start"]
            end = chunk[-1]["end"] + 0.16
            cards.append({"start": start, "end": end, "text": text})
    if cards and scenes_meta:
        cards[-1]["end"] = max(cards[-1]["end"], scenes_meta[-1]["end_sec"] - 0.05)
    for idx in range(len(cards) - 1):
        if cards[idx]["end"] > cards[idx + 1]["start"]:
            cards[idx]["end"] = max(cards[idx]["start"] + 0.08, cards[idx + 1]["start"] - 0.02)
    return cards


def draw_subtitle_card(canvas_rgba: Image.Image, text: str, font: ImageFont.FreeTypeFont, y_ratio: float = 0.79):
    """High-contrast, large 50+-friendly lower-third caption safely above Reels/Shorts UI."""
    if not text:
        return
    draw = ImageDraw.Draw(canvas_rgba)
    upper_text = text.upper()

    cur_font = font
    bbox = draw.textbbox((0, 0), upper_text, font=cur_font, stroke_width=5)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    if tw > W - 110:
        cur_font = load_font(max(30, int(font.size * (W - 120) / tw)), bold=True)
        bbox = draw.textbbox((0, 0), upper_text, font=cur_font, stroke_width=5)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

    cx = W // 2
    cy = int(H * y_ratio)
    pad_x, pad_y = 22, 12
    x0 = cx - tw // 2 - pad_x
    y0 = cy - th // 2 - pad_y
    x1 = cx + tw // 2 + pad_x
    y1 = cy + th // 2 + pad_y

    pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pill)
    pdraw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=(14, 14, 18, 182))
    canvas_rgba.alpha_composite(pill)

    highlight_words = {
        "CHICAGO", "ILLINOIS", "MISSOURI", "LOUIS", "1900", "1885", "BACKWARDS",
        "REVERSE", "CANAL", "28-MILE", "PANAMA", "BLASTED", "DAM", "SUPREME",
        "COURT", "LOST", "GREEN", "GENIUS", "TRICK", "REWIND", "RIVALRY", "STORM"
    }
    clean_tokens = upper_text.split()
    has_kw = any(tok.strip(".,?!—:\"'") in highlight_words for tok in clean_tokens)
    fill_col = (255, 224, 72, 255) if has_kw and len(clean_tokens) <= 3 else (255, 255, 255, 255)

    draw = ImageDraw.Draw(canvas_rgba)
    tx = cx - tw // 2 - bbox[0]
    ty = cy - th // 2 - bbox[1]
    draw.text(
        (tx, ty),
        upper_text,
        font=cur_font,
        fill=fill_col,
        stroke_width=5,
        stroke_fill=(12, 12, 16, 255),
    )


def extract_sprite_clean(
    pil_img: Image.Image,
    bbox_norm: list,
    exclude_rects: list = None,
    width: int = W,
    height: int = H,
):
    """
    GrabCut + contour cleanup sprite extractor with optional `exclude_rects`
    to protect adjacent map text labels from being pulled into a sprite.
    """
    rgb = np.array(pil_img)
    x0 = max(0, int(bbox_norm[0] * width))
    y0 = max(0, int(bbox_norm[1] * height))
    x1 = min(width, int(bbox_norm[2] * width))
    y1 = min(height, int(bbox_norm[3] * height))
    patch = rgb[y0:y1, x0:x1].copy()
    ph, pw = patch.shape[:2]

    mask = np.full((ph, pw), cv2.GC_PR_FGD, dtype=np.uint8)
    m = max(4, min(8, min(ph, pw) // 18))
    mask[:m, :] = cv2.GC_BGD
    mask[-m:, :] = cv2.GC_BGD
    mask[:, :m] = cv2.GC_BGD
    mask[:, -m:] = cv2.GC_BGD

    if exclude_rects:
        for er in exclude_rects:
            ex0 = max(0, int(er[0] * width) - x0)
            ey0 = max(0, int(er[1] * height) - y0)
            ex1 = min(pw, int(er[2] * width) - x0)
            ey1 = min(ph, int(er[3] * height) - y0)
            if ex1 > ex0 and ey1 > ey0:
                mask[ey0:ey1, ex0:ex1] = cv2.GC_BGD

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    bgr_patch = cv2.cvtColor(patch, cv2.COLOR_RGB2BGR)
    cv2.grabCut(bgr_patch, mask, None, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_MASK)

    fg_bin = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if exclude_rects:
        for er in exclude_rects:
            ex0 = max(0, int(er[0] * width) - x0)
            ey0 = max(0, int(er[1] * height) - y0)
            ex1 = min(pw, int(er[2] * width) - x0)
            ey1 = min(ph, int(er[3] * height) - y0)
            if ex1 > ex0 and ey1 > ey0:
                fg_bin[ey0:ey1, ex0:ex1] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg_bin = cv2.morphologyEx(fg_bin, cv2.MORPH_OPEN, kernel, iterations=1)
    fg_bin = cv2.morphologyEx(fg_bin, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(fg_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(fg_bin)
    min_area = max(180, int(ph * pw * 0.015))
    for cnt in contours:
        if cv2.contourArea(cnt) >= min_area:
            cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)

    if np.count_nonzero(filled) < ph * pw * 0.04:
        return eng.extract_sprite_and_inpaint_bg(pil_img, bbox_norm, width=width, height=height)

    full_mask = np.zeros((height, width), dtype=np.uint8)
    dil_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    full_mask[y0:y1, x0:x1] = cv2.dilate(filled, dil_k, iterations=1)
    if exclude_rects:
        for er in exclude_rects:
            ex0 = max(0, int(er[0] * width))
            ey0 = max(0, int(er[1] * height))
            ex1 = min(width, int(er[2] * width))
            ey1 = min(height, int(er[3] * height))
            full_mask[ey0:ey1, ex0:ex1] = 0

    inpainted_rgb = cv2.inpaint(rgb, full_mask, 7, cv2.INPAINT_TELEA)
    alpha = cv2.GaussianBlur(filled, (3, 3), 0)
    sprite_rgba = np.dstack([patch, alpha])
    return Image.fromarray(inpainted_rgb), Image.fromarray(sprite_rgba), (x0, y0, pw, ph)


def draw_overhead_crisp(canvas_rgba, cx, cy, text, prog_in, font, style="cloud", width=W, height=H):
    """Crisp, pixel-centered overhead thought cloud or pill badge above characters."""
    if prog_in <= 0.02:
        return
    scale = (prog_in / 0.65 * 1.10) if prog_in < 0.65 else (1.10 - 0.10 * ((prog_in - 0.65) / 0.35))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y = 20, 13
    bw = int((tw + pad_x * 2) * scale)
    bh = int((th + pad_y * 2) * scale)
    x0 = int(np.clip(cx - bw // 2, 16, width - bw - 16))
    y0 = int(np.clip(cy - bh // 2, 16, height - bh - 16))
    x1, y1 = x0 + bw, y0 + bh

    if style == "cloud":
        draw.ellipse([cx - 6, y1 + 4, cx + 6, y1 + 15], fill=(255, 253, 245, 245), outline=(25, 25, 25, 245), width=2)
        draw.ellipse([cx - 4, y1 + 19, cx + 4, y1 + 26], fill=(255, 253, 245, 235), outline=(25, 25, 25, 235), width=2)

    draw.rounded_rectangle([x0 + 3, y0 + 5, x1 + 3, y1 + 5], radius=18, fill=(0, 0, 0, 115))
    bg_col = (255, 253, 245, 248) if style == "cloud" else (22, 48, 128, 246)
    fg_col = (20, 18, 16, 255) if style == "cloud" else (255, 255, 255, 255)
    border_col = (24, 22, 20, 255) if style == "cloud" else (255, 214, 58, 255)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=bg_col, outline=border_col, width=3)

    if scale > 0.72:
        tx = x0 + (bw - tw) // 2 - bbox[0]
        ty = y0 + (bh - th) // 2 - bbox[1]
        draw.multiline_text((tx, ty), text, font=font, fill=fg_col, align="center", spacing=4)

    canvas_rgba.alpha_composite(layer)


def apply_vhs_rewind(frame_rgba: Image.Image, progress: float, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Nostalgic VHS rewind scanlines, chromatic shift, and << REW 1900 -> 1885 overlay below scroll."""
    arr = np.array(frame_rgba).copy()
    arr[::4, :, :3] = (arr[::4, :, :3] * 0.72).astype(np.uint8)
    shift = max(2, int(5 + 3 * math.sin(progress * 28.0)))
    arr[:, shift:, 0] = arr[:, :-shift, 0]
    arr[:, :-shift, 2] = arr[:, shift:, 2]
    bar_y = int((1.0 - (progress * 1.8 % 1.0)) * (H - 40))
    noise = np.random.randint(-35, 35, (28, W, 3))
    arr[bar_y : bar_y + 28, :, :3] = np.clip(
        arr[bar_y : bar_y + 28, :, :3].astype(np.int16) + noise, 0, 255
    ).astype(np.uint8)

    out = Image.fromarray(arr, mode="RGBA")
    draw = ImageDraw.Draw(out)
    if int(progress * 10) % 2 == 0 or progress < 0.75:
        label = "<< REW  1900 -> 1885"
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        bx0 = (W - tw) // 2 - 22
        by0 = 248
        bx1 = bx0 + tw + 44
        by1 = by0 + th + 22
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=12, fill=(10, 12, 18, 208), outline=(255, 255, 255, 232), width=2)
        draw.text((bx0 + 22 - tb[0], by0 + 11 - tb[1]), label, font=font, fill=(255, 255, 255, 255))
    return out


# ---------- Scene Config Definition (12 Scenes) ----------

def build_scene_config(audio_meta: dict) -> dict:
    scenes_by_id = {s["id"]: s for s in audio_meta["scenes"]}

    specs = [
        {
            "id": "scene_01",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_01.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": 0.0, "pan_y": -0.01, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.18, "pan_x": 0.0, "pan_y": 0.02, "tilt_deg": 0.9},
            "sprites": [
                {
                    "bbox": [0.58, 0.17, 0.815, 0.355],
                    "exclude_rects": [[0.785, 0.275, 1.0, 0.315]],
                    "motion": "glare_bob",
                    "pop_delay": 0.14,
                },
                {
                    "bbox": [0.16, 0.42, 0.425, 0.595],
                    "motion": "shudder",
                    "pop_delay": 0.32,
                },
            ],
            "overhead": {"text": "RIVER BACKWARDS!", "cx": 250, "cy": 335, "trigger_rel": 4.65, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.55},
                {"rel": 0.16, "type": "pawn_bounce", "gain": 0.70},
                {"rel": 0.35, "type": "pawn_bounce", "gain": 0.70},
                {"rel": 4.65, "type": "cork_pop", "gain": 0.65},
                {"rel": 4.85, "type": "river_rush", "gain": 0.55},
                {"rel": -0.58, "type": "tape_rewind", "gain": 0.75},
            ],
        },
        {
            "id": "scene_02",
            "mode": "Mode A (VHS Rewind -> 1885)",
            "keyframe": "keyframes/scene_02.jpg",
            "vhs_rewind": True,
            "camera_start": {"zoom": 1.10, "pan_x": 0.0, "pan_y": -0.03, "tilt_deg": -0.7},
            "camera_end": {"zoom": 1.02, "pan_x": 0.0, "pan_y": 0.0, "tilt_deg": 0.0},
            "sprites": [],
            "overhead": None,
            "foley": [
                {"rel": 0.05, "type": "tape_rewind", "gain": 0.72},
                {"rel": 0.90, "type": "parchment_brush", "gain": 0.65},
            ],
        },
        {
            "id": "scene_03",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_03.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": -0.02, "pan_y": -0.01, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.19, "pan_x": 0.03, "pan_y": -0.02, "tilt_deg": 0.8},
            "sprites": [
                {
                    "bbox": [0.17, 0.39, 0.51, 0.59],
                    "exclude_rects": [[0.35, 0.515, 0.59, 0.555]],
                    "motion": "write_bob",
                    "pop_delay": 0.14,
                },
            ],
            "overhead": {"text": "INTO THE LAKE!", "cx": 265, "cy": 385, "trigger_rel": 2.65, "style": "cloud"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.18, "type": "pawn_bounce", "gain": 0.65},
                {"rel": 2.40, "type": "water_splash", "gain": 0.72},
                {"rel": 2.65, "type": "cork_pop", "gain": 0.58},
            ],
        },
        {
            "id": "scene_04",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_04.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": 0.01, "pan_y": -0.02, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.20, "pan_x": -0.02, "pan_y": 0.01, "tilt_deg": -0.9},
            "sprites": [
                {
                    "bbox": [0.19, 0.425, 0.455, 0.595],
                    "motion": "shiver",
                    "pop_delay": 0.12,
                },
            ],
            "overhead": {"text": "WE DRINK THAT?!", "cx": 245, "cy": 365, "trigger_rel": 2.95, "style": "cloud"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 0.16, "type": "pawn_bounce", "gain": 0.60},
                {"rel": 2.95, "type": "jaw_drop", "gain": 0.68},
                {"rel": 5.10, "type": "storm_thunder", "gain": 0.72},
                {"rel": 7.15, "type": "somber_bell", "gain": 0.45},
            ],
        },
        {
            "id": "scene_05",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_05.jpg",
            "camera_start": {"zoom": 1.03, "pan_x": 0.02, "pan_y": -0.01, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.18, "pan_x": -0.01, "pan_y": -0.03, "tilt_deg": 0.9},
            "sprites": [
                {
                    "bbox": [0.70, 0.41, 0.985, 0.595],
                    "motion": "write_bob",
                    "pop_delay": 0.15,
                },
            ],
            "overhead": {"text": "28-MILE CANAL!", "cx": 330, "cy": 250, "trigger_rel": 2.70, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.20, "type": "pawn_bounce", "gain": 0.68},
                {"rel": 1.35, "type": "parchment_brush", "gain": 0.72},
                {"rel": 2.70, "type": "cork_pop", "gain": 0.62},
            ],
        },
        {
            "id": "scene_06",
            "mode": "Mode B (2.5D Limestone Trench Diorama)",
            "keyframe": "keyframes/scene_06.jpg",
            "camera_start": {"zoom": 1.05, "pan_x": 0.0, "pan_y": 0.02, "tilt_deg": -0.5},
            "camera_end": {"zoom": 1.22, "pan_x": 0.0, "pan_y": 0.05, "tilt_deg": 0.8},
            "impact_shake_rel": 1.62,
            "sprites": [],
            "overhead": {"text": "8 YEARS DIGGING!", "cx": 360, "cy": 470, "trigger_rel": 1.50, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.50, "type": "pickaxe_clink", "gain": 0.68},
                {"rel": 1.05, "type": "pickaxe_clink", "gain": 0.62},
                {"rel": 1.58, "type": "dynamite_blast", "gain": 0.82},
                {"rel": 3.45, "type": "pickaxe_clink", "gain": 0.58},
                {"rel": 5.75, "type": "celesta_chime", "gain": 0.62},
            ],
        },
        {
            "id": "scene_07",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_07.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": 0.02, "pan_y": -0.02, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.20, "pan_x": -0.02, "pan_y": 0.01, "tilt_deg": -1.0},
            "sprites": [
                {
                    "bbox": [0.14, 0.43, 0.43, 0.60],
                    "motion": "lunge_right",
                    "pop_delay": 0.14,
                },
            ],
            "overhead": {"text": "NOT IN OUR RIVER!", "cx": 270, "cy": 420, "trigger_rel": 2.55, "style": "cloud"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.18, "type": "pawn_bounce", "gain": 0.68},
                {"rel": 2.55, "type": "cork_pop", "gain": 0.60},
                {"rel": 4.80, "type": "war_horn", "gain": 0.45},
            ],
        },
        {
            "id": "scene_08",
            "mode": "Mode B (2.5D Winter Dawn Diorama)",
            "keyframe": "keyframes/scene_08.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": 0.0, "pan_y": 0.02, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.22, "pan_x": 0.0, "pan_y": 0.04, "tilt_deg": -0.9},
            "impact_shake_rel": 7.52,
            "sprites": [],
            "overhead": {"text": "JAN 2, 1900!", "cx": 360, "cy": 185, "trigger_rel": 2.95, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.35, "type": "cold_wind", "gain": 0.58},
                {"rel": 2.95, "type": "cork_pop", "gain": 0.60},
                {"rel": 7.48, "type": "dynamite_blast", "gain": 0.90},
                {"rel": 7.85, "type": "river_rush", "gain": 0.68},
            ],
        },
        {
            "id": "scene_09",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_09.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": 0.02, "pan_y": -0.02, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.20, "pan_x": -0.02, "pan_y": 0.02, "tilt_deg": 1.0},
            "sprites": [
                {
                    "bbox": [0.13, 0.185, 0.43, 0.39],
                    "motion": "cheer_bounce",
                    "pop_delay": 0.10,
                },
                {
                    "bbox": [0.32, 0.535, 0.43, 0.615],
                    "motion": "barge_drift_sw",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "FLOW REVERSED!", "cx": 330, "cy": 165, "trigger_rel": 3.30, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.15, "type": "river_rush", "gain": 0.72},
                {"rel": 0.25, "type": "pawn_bounce", "gain": 0.60},
                {"rel": 3.30, "type": "cork_pop", "gain": 0.62},
                {"rel": 4.45, "type": "celesta_chime", "gain": 0.65},
            ],
        },
        {
            "id": "scene_10",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_10.jpg",
            "camera_start": {"zoom": 1.03, "pan_x": -0.01, "pan_y": 0.0, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.19, "pan_x": 0.02, "pan_y": -0.02, "tilt_deg": -0.8},
            "impact_shake_rel": 3.30,
            "sprites": [
                {
                    "bbox": [0.50, 0.34, 0.90, 0.61],
                    "exclude_rects": [[0.68, 0.32, 1.0, 0.375]],
                    "motion": "gavel_slam",
                    "pop_delay": 0.14,
                    "slam_rel": 3.30,
                },
                {
                    "bbox": [0.21, 0.43, 0.425, 0.595],
                    "motion": "shudder_after_slam",
                    "pop_delay": 0.22,
                    "slam_rel": 3.30,
                },
                {
                    "bbox": [0.36, 0.16, 0.535, 0.31],
                    "motion": "glare_bob",
                    "pop_delay": 0.18,
                },
            ],
            "overhead": {"text": "CASE DISMISSED!", "cx": 420, "cy": 135, "trigger_rel": 3.35, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.48},
                {"rel": 0.18, "type": "pawn_bounce", "gain": 0.65},
                {"rel": 3.30, "type": "gavel_slam", "gain": 0.88},
                {"rel": 3.45, "type": "jaw_drop", "gain": 0.68},
                {"rel": 3.55, "type": "cork_pop", "gain": 0.55},
            ],
        },
        {
            "id": "scene_11",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_11.jpg",
            "camera_start": {"zoom": 1.04, "pan_x": 0.0, "pan_y": -0.01, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.20, "pan_x": 0.0, "pan_y": -0.03, "tilt_deg": 0.9},
            "sprites": [
                {
                    "bbox": [0.15, 0.40, 0.43, 0.595],
                    "motion": "cheer_bounce",
                    "pop_delay": 0.12,
                },
                {
                    "bbox": [0.51, 0.495, 0.60, 0.56],
                    "motion": "ship_rock",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "STILL BACKWARDS!", "cx": 300, "cy": 255, "trigger_rel": 1.45, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 0.16, "type": "pawn_bounce", "gain": 0.62},
                {"rel": 1.45, "type": "cork_pop", "gain": 0.60},
                {"rel": 4.75, "type": "celesta_chime", "gain": 0.72},
                {"rel": 5.45, "type": "celesta_chime_hi", "gain": 0.68},
            ],
        },
        {
            "id": "scene_12",
            "mode": "Mode A (3D Relief Map)",
            "keyframe": "keyframes/scene_12.jpg",
            "camera_start": {"zoom": 1.03, "pan_x": 0.0, "pan_y": -0.01, "tilt_deg": 0.0},
            "camera_end": {"zoom": 1.17, "pan_x": 0.0, "pan_y": 0.01, "tilt_deg": 0.6},
            "sprites": [
                {
                    "bbox": [0.60, 0.095, 0.795, 0.255],
                    "motion": "football_hop_r",
                    "pop_delay": 0.14,
                },
                {
                    "bbox": [0.18, 0.42, 0.445, 0.595],
                    "motion": "football_hop_l",
                    "pop_delay": 0.26,
                },
            ],
            "overhead": {"text": "CHICAGO vs. ST. LOUIS", "cx": 270, "cy": 295, "trigger_rel": 2.35, "style": "badge"},
            "foley": [
                {"rel": 0.05, "type": "camera_whoosh", "gain": 0.50},
                {"rel": 0.25, "type": "stadium_swell", "gain": 0.60},
                {"rel": 2.35, "type": "cork_pop", "gain": 0.65},
            ],
        },
    ]

    for sp in specs:
        m = scenes_by_id[sp["id"]]
        sp["start_sec"] = m["start_sec"]
        sp["end_sec"] = m["end_sec"]
        sp["narration"] = m["text"]

    return {
        "video_settings": {
            "width": W,
            "height": H,
            "fps": FPS,
            "subtitle_y_ratio": 0.79,
        },
        "total_duration_sec": audio_meta["total_duration_sec"],
        "scenes": specs,
    }


def mix_foley_and_voice(config: dict, voice_wav_path: Path, out_wav_path: Path):
    with wave.open(str(voice_wav_path), "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        voice = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    foley_buf = np.zeros_like(voice)
    total_dur = len(voice) / SR

    for sc in config["scenes"]:
        s0, s1 = sc["start_sec"], sc["end_sec"]
        dur = s1 - s0
        for cue in sc.get("foley", []):
            rel = cue["rel"]
            t_abs = (s1 + rel) if rel < 0 else (s0 + rel)
            gain = cue.get("gain", 0.65)
            ctype = cue["type"]

            if ctype == "camera_whoosh":
                snd = fm.foley_camera_whoosh()
            elif ctype == "pawn_bounce":
                snd = fm.foley_pawn_bounce()
            elif ctype == "cork_pop":
                snd = fm.foley_cork_pop()
            elif ctype == "parchment_brush":
                snd = fm.foley_parchment_brush()
            elif ctype == "tape_rewind":
                snd = fm.foley_tape_rewind()
            elif ctype == "jaw_drop":
                snd = fm.foley_jaw_drop_clatter()
            elif ctype == "war_horn":
                snd = fm.foley_war_horn()
            elif ctype == "gavel_slam":
                snd = foley_gavel_slam()
            elif ctype == "cold_wind":
                snd = foley_cold_wind(duration=min(4.2, max(2.0, dur - 1.5)))
            elif ctype == "somber_bell":
                snd = fm.foley_somber_bell(duration=2.1)
            elif ctype == "pickaxe_clink":
                snd = foley_pickaxe_clink()
            elif ctype == "dynamite_blast":
                snd = foley_dynamite_blast()
            elif ctype == "river_rush":
                snd = foley_river_rush(duration=min(3.5, max(1.6, dur - 0.3)))
            elif ctype == "water_splash":
                snd = foley_water_splash()
            elif ctype == "storm_thunder":
                snd = foley_storm_thunder(duration=min(3.6, max(2.0, dur - 4.8)))
            elif ctype == "celesta_chime":
                snd = fm.foley_celesta_chime(freq=1046.5)
            elif ctype == "celesta_chime_hi":
                snd = fm.foley_celesta_chime(freq=1318.5)
            elif ctype == "stadium_swell":
                snd = foley_stadium_swell(duration=min(3.8, max(2.0, dur - 0.6)))
            else:
                continue

            fm.add_sound(foley_buf, t_abs, snd, gain=gain)

    max_f = np.max(np.abs(foley_buf))
    if max_f > 0.95:
        foley_buf = foley_buf / max_f * 0.92

    mixed = voice * 0.96 + foley_buf * 0.58
    peak = np.max(np.abs(mixed))
    if peak > 0.96:
        mixed = mixed / peak * 0.96

    pcm16 = (np.clip(mixed, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(out_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm16.tobytes())
    print(f"Mixed audio saved to {out_wav_path} ({total_dur:.2f}s)")


def compute_sprite_transform(motion: str, local_t: float, sp_cfg: dict):
    pop_delay = sp_cfg.get("pop_delay", 0.12)
    sc = eng.spring_scale(local_t - pop_delay, rise=0.34)
    dx, dy, ang = 0.0, 0.0, 0.0
    t = max(0.0, local_t - pop_delay)

    if motion == "lunge_right":
        dx = 10.0 * math.sin(t * 2.8) * (0.5 + 0.5 * math.sin(t * 1.3))
        dy = -5.0 * abs(math.sin(t * 4.0))
        ang = -3.5 * math.sin(t * 2.8)
    elif motion == "write_bob":
        dx = 6.0 * math.sin(t * 2.2)
        dy = -5.0 * abs(math.sin(t * 4.2))
        ang = 3.8 * math.sin(t * 2.8)
    elif motion == "shudder":
        dx = 5.0 * math.sin(t * 34.0) * math.exp(-max(0.0, t - 2.0) * 0.25)
        dy = -4.0 * abs(math.sin(t * 6.0))
        ang = 3.5 * math.sin(t * 18.0)
    elif motion == "shudder_after_slam":
        slam_rel = sp_cfg.get("slam_rel", 3.30)
        if local_t >= slam_rel:
            dt = local_t - slam_rel
            dx = 6.5 * math.sin(dt * 42.0) * math.exp(-dt * 0.65)
            dy = -5.0 * abs(math.sin(dt * 8.0)) * math.exp(-dt * 0.4)
            ang = 5.0 * math.sin(dt * 24.0) * math.exp(-dt * 0.6)
        else:
            dy = -3.0 * abs(math.sin(t * 2.8))
    elif motion == "glare_bob":
        dy = -5.0 * abs(math.sin(t * 3.2))
        ang = 2.5 * math.sin(t * 2.4)
    elif motion == "ship_rock":
        sc = 1.0
        dx = -8.0 * math.sin(local_t * 0.9)
        dy = 3.0 * math.sin(local_t * 2.8)
        ang = 4.5 * math.sin(local_t * 2.2)
    elif motion == "barge_drift_sw":
        sc = 1.0
        # Gently ride the reversed river flow diagonally down-left (southwest)
        drift = min(1.0, local_t / 5.2)
        dx = -26.0 * drift + 2.5 * math.sin(local_t * 3.0)
        dy = 36.0 * drift + 2.5 * math.cos(local_t * 2.6)
        ang = 4.0 * math.sin(local_t * 2.5)
    elif motion == "gavel_slam":
        slam_rel = sp_cfg.get("slam_rel", 3.30)
        dt_slam = local_t - slam_rel
        if -0.35 <= dt_slam < 0.0:
            p = (dt_slam + 0.35) / 0.35
            dy = -16.0 * p
            ang = 8.0 * p
        elif 0.0 <= dt_slam < 0.35:
            p = dt_slam / 0.35
            dy = 10.0 * math.exp(-p * 5.0)
            ang = -9.0 * math.exp(-p * 6.0)
        else:
            dy = -3.0 * abs(math.sin(t * 2.4))
    elif motion == "shiver":
        dx = 4.5 * math.sin(local_t * 46.0)
        dy = 1.8 * math.cos(local_t * 34.0)
        ang = 2.4 * math.sin(local_t * 40.0)
    elif motion == "cheer_bounce":
        dy = -13.0 * abs(math.sin(t * 5.0))
        ang = 4.8 * math.sin(t * 5.0)
    elif motion == "football_hop_l":
        dx = 6.0 * math.sin(t * 3.0)
        dy = -8.0 * abs(math.sin(t * 4.5))
        ang = -3.0 * math.sin(t * 3.0)
    elif motion == "football_hop_r":
        dx = -6.0 * math.sin(t * 3.0)
        dy = -8.0 * abs(math.sin(t * 4.5 + 0.7))
        ang = 3.0 * math.sin(t * 3.0)

    return dx, dy, sc, ang


def prepare_scene_assets(config: dict):
    prepared = []
    for sc in config["scenes"]:
        kf_path = EP_DIR / sc["keyframe"]
        img = Image.open(kf_path).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)

        bg_img = img
        extracted_sprites = []
        for sp_cfg in sc.get("sprites", []):
            bg_img, sp_rgba, base_rect = extract_sprite_clean(
                bg_img,
                sp_cfg["bbox"],
                exclude_rects=sp_cfg.get("exclude_rects"),
                width=W,
                height=H,
            )
            extracted_sprites.append((sp_rgba, base_rect, sp_cfg))

        prepared.append(
            {
                "cfg": sc,
                "bg_rgba": bg_img.convert("RGBA"),
                "sprites": extracted_sprites,
            }
        )
    return prepared


def main():
    audio_meta_path = EP_DIR / "audio_timings.json"
    with open(audio_meta_path, "r", encoding="utf-8") as f:
        audio_meta = json.load(f)

    config = build_scene_config(audio_meta)
    config_path = EP_DIR / "scene_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Saved {config_path}")

    # Step 1: Mix voiceover + procedural foley (rebuild voice WAV from MP3 if needed on another PC)
    voice_wav = EP_DIR / "chicago_river.wav"
    if not voice_wav.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(EP_DIR / "chicago_river.mp3"), "-ar", str(SR), "-ac", "1", str(voice_wav)],
            check=True,
        )
    mixed_wav = EP_DIR / "chicago_river_mixed.wav"
    mix_foley_and_voice(config, voice_wav, mixed_wav)

    # Step 2: Build subtitle cards
    subtitle_cards = build_subtitle_cards(audio_meta["scenes"])

    # Step 3: Extract sprites & inpaint backgrounds for all 12 scenes
    print("Extracting sprites & inpainting backgrounds...")
    prepared_scenes = prepare_scene_assets(config)

    sub_font = load_font(44, bold=True)
    ov_font = load_font(26, bold=True)
    vhs_font = load_font(30, bold=True)

    # QA frame targets (cover every major visual beat & badge placement)
    qa_dir = EP_DIR / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_targets = {}
    for sc in config["scenes"]:
        if sc["id"] in ("scene_01", "scene_02", "scene_03", "scene_04", "scene_06", "scene_08", "scene_09", "scene_10", "scene_11", "scene_12"):
            t_mid = sc["start_sec"] + (sc["end_sec"] - sc["start_sec"]) * 0.68
            qa_targets[sc["id"]] = int(t_mid * FPS)
    qa_targets["scene_12_final"] = int((config["total_duration_sec"] - 0.8) * FPS)

    total_frames = int(math.ceil(config["total_duration_sec"] * FPS))
    out_mp4 = EP_DIR / "heartland_mapped_ep02_chicago_river_reversal.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "warning",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(mixed_wav),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(out_mp4),
    ]
    print(f"Rendering {total_frames} frames ({config['total_duration_sec']:.2f}s @ {FPS} FPS) -> {out_mp4.name} ...")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    sub_idx = 0
    for f_idx in range(total_frames):
        t = f_idx / FPS

        active = prepared_scenes[-1]
        for ps in prepared_scenes:
            if ps["cfg"]["start_sec"] <= t < ps["cfg"]["end_sec"]:
                active = ps
                break

        sc = active["cfg"]
        s0, s1 = sc["start_sec"], sc["end_sec"]
        local_t = max(0.0, t - s0)
        dur = max(0.001, s1 - s0)
        prog = min(1.0, local_t / dur)
        eased = smoothstep(prog)

        canvas = active["bg_rgba"].copy()

        for sp_rgba, base_rect, sp_cfg in active["sprites"]:
            dx, dy, scale, ang = compute_sprite_transform(sp_cfg["motion"], local_t, sp_cfg)
            eng.paste_moving_sprite(canvas, sp_rgba, base_rect, dx=dx, dy=dy, scale=scale, angle_deg=ang, shadow=True)

        ov = sc.get("overhead")
        if ov and local_t >= ov["trigger_rel"]:
            ov_prog = min(1.0, (local_t - ov["trigger_rel"]) / 0.28)
            draw_overhead_crisp(
                canvas,
                ov["cx"],
                ov["cy"],
                ov["text"],
                ov_prog,
                ov_font,
                style=ov.get("style", "cloud"),
                width=W,
                height=H,
            )

        cs = sc["camera_start"]
        ce = sc["camera_end"]
        zoom = lerp(cs["zoom"], ce["zoom"], eased)
        pan_x = lerp(cs["pan_x"], ce["pan_x"], eased)
        pan_y = lerp(cs["pan_y"], ce["pan_y"], eased)
        tilt = lerp(cs["tilt_deg"], ce["tilt_deg"], eased)

        if "impact_shake_rel" in sc:
            dt_imp = local_t - sc["impact_shake_rel"]
            if 0.0 <= dt_imp < 0.40:
                decay = math.exp(-dt_imp * 9.0)
                pan_x += 0.014 * math.sin(dt_imp * 55.0) * decay
                pan_y += 0.012 * math.cos(dt_imp * 48.0) * decay

        t_blur = 0.0
        if local_t < 0.13 and sc["id"] != "scene_01":
            t_blur = (1.0 - local_t / 0.13) * 0.55
        elif (dur - local_t) < 0.12 and sc["id"] != "scene_12":
            t_blur = (1.0 - (dur - local_t) / 0.12) * 0.55

        frame = eng.apply_25d_camera(canvas, zoom, pan_x, pan_y, tilt, transition_blur=t_blur, width=W, height=H)

        if sc.get("vhs_rewind") or (sc["id"] == "scene_01" and (dur - local_t) < 0.38):
            vhs_p = prog if sc.get("vhs_rewind") else (1.0 - (dur - local_t) / 0.38)
            frame = apply_vhs_rewind(frame, vhs_p, vhs_font)

        while sub_idx < len(subtitle_cards) and subtitle_cards[sub_idx]["end"] < t:
            sub_idx += 1
        if sub_idx < len(subtitle_cards):
            card = subtitle_cards[sub_idx]
            if card["start"] <= t <= card["end"]:
                draw_subtitle_card(frame, card["text"], sub_font, y_ratio=0.79)

        for sid, target_f in qa_targets.items():
            if f_idx == target_f:
                frame.convert("RGB").save(qa_dir / f"qa_{sid}.jpg", quality=92)

        proc.stdin.write(frame.convert("RGB").tobytes())

        if (f_idx + 1) % 300 == 0 or f_idx + 1 == total_frames:
            print(f"  Rendered {f_idx + 1}/{total_frames} frames ({(f_idx + 1)/total_frames*100:.0f}%)")

    proc.stdin.close()
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"ffmpeg exited with code {ret}")
    print(f"SUCCESS! Final video saved to: {out_mp4}")


if __name__ == "__main__":
    main()
