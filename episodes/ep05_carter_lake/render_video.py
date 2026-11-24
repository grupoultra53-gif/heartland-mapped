"""
Heartland Mapped — Episode 05 (v2): Carter Lake — The Iowa Town Trapped Inside Nebraska (1877)
2.5D Historical Map Animation Renderer (720x1280, 30 FPS)
Voiceover: Fish Audio S2.1 Pro — Ethan (@Fish Official) + faster-whisper word alignment
v2 Retention Upgrades:
  - Immediate Frame 0 hook (visible focal sprites + tight close-up zoom)
  - Word-synced multi-shot close-ups & reaction cuts (eval_shot_camera)
  - Warm Americana acoustic documentary underscore with fast broadcast auto-ducking
  - Animated 1-word CTA comment panel ("IOWA" / "NEBRASKA") + subtitle auto-lift
  - Seamless grammatical & visual whip-return loop into Scene 01 Frame 0
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


# ---------- Custom Procedural Situational Foley Accents ----------

def foley_river_rush(duration: float = 4.2) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    roar = fm.bandpass(np.random.normal(0, 1, n), 160, 1400) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.45 * t))
    sub = fm.lowpass(np.random.normal(0, 1, n), 180) * 0.55
    env = np.sin(np.pi * (t / duration)) ** 0.75
    return (roar * 0.42 + sub * 0.35) * env


def foley_ice_crash() -> np.ndarray:
    n = int(0.85 * SR)
    t = np.linspace(0, 0.85, n, endpoint=False)
    crack = fm.bandpass(np.random.normal(0, 1, n), 1200, 6200) * np.exp(-t * 14.0) * 0.85
    crunch = fm.bandpass(np.random.normal(0, 1, n), 300, 1800) * np.exp(-t * 6.5) * 0.75
    thump = np.sin(2 * np.pi * np.cumsum(np.linspace(140, 42, n)) / SR) * np.exp(-t * 11.0) * 0.70
    return (crack * 0.65 + crunch * 0.60 + thump * 0.85) * 0.85


def foley_steam_whistle() -> np.ndarray:
    """Comic teapot steam puff for furious Iowa governor."""
    n = int(0.45 * SR)
    t = np.linspace(0, 0.45, n, endpoint=False)
    hiss = fm.bandpass(np.random.normal(0, 1, n), 2200, 7500) * np.exp(-t * 5.5) * 0.55
    whistle = np.sin(2 * np.pi * np.cumsum(np.linspace(1350, 1850, n)) / SR) * np.sin(np.pi * t / 0.45) * 0.32
    return (hiss + whistle) * 0.75


def foley_gavel_slam() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.linspace(0, 0.45, n, endpoint=False)
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(160, 46, n)) / SR) * np.exp(-t * 14.0)
    wood_crack = fm.bandpass(np.random.normal(0, 1, n), 450, 2600) * np.exp(-t * 28.0) * 0.78
    return (thud * 0.95 + wood_crack) * 0.88


def foley_jet_flyby(duration: float = 2.0) -> np.ndarray:
    """Subtle distant commercial airliner takeoff whoosh."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    jet = fm.bandpass(np.random.normal(0, 1, n), 260, 2600)
    whine_f = np.linspace(620, 440, n)
    whine = np.sin(2 * np.pi * np.cumsum(whine_f) / SR) * 0.14
    env = np.sin(np.pi * (t / duration)) ** 1.4
    return (jet * 0.36 + whine) * env


def foley_stadium_swell(duration: float = 3.2) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    crowd = fm.bandpass(np.random.normal(0, 1, n), 240, 1900)
    low_roar = fm.lowpass(np.random.normal(0, 1, n), 320) * 0.5
    env = np.sin(np.pi * (t / duration)) ** 1.15
    return (crowd * 0.34 + low_roar * 0.22) * env


# ---------- Subtitle Chunk Builder (2-4 words, 50+ readable, preserves ? / ! / em-dash) ----------

def restore_question_and_excl_punctuation(scene_text: str, words: list) -> list:
    raw_tokens = re.findall(r"[A-Za-z0-9'\-]+|[?!.—]", scene_text)
    punct_after = {}
    w_idx = 0
    for tok in raw_tokens:
        if tok in ("?", "!", ".", "—"):
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
                "break_after": p in ("?", "!", ".", "—"),
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
            end = chunk[-1]["end"] + 0.14
            cards.append({"start": start, "end": end, "text": text})
    if cards and scenes_meta:
        cards[-1]["end"] = max(cards[-1]["end"], scenes_meta[-1]["end_sec"] - 0.18)
    for idx in range(len(cards) - 1):
        if cards[idx]["end"] > cards[idx + 1]["start"]:
            cards[idx]["end"] = max(cards[idx]["start"] + 0.08, cards[idx + 1]["start"] - 0.02)
    return cards


def draw_subtitle_card(canvas_rgba: Image.Image, text: str, font: ImageFont.FreeTypeFont, y_ratio: float = 0.79):
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
    pdraw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=(14, 14, 18, 188))
    canvas_rgba.alpha_composite(pill)

    highlight_words = {
        "IOWA", "NEBRASKA", "NEBRASKA'S", "CARTER", "LAKE", "MISSOURI", "RIVER",
        "1846", "1877", "1892", "1,300", "3,800", "FLOOD", "OVERNIGHT", "OMAHA",
        "OMAHA'S", "AIRPORT", "SUPREME", "COURT", "BORDER", "REWIND", "VICTORY", "ICE"
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
    min_area = max(140, int(ph * pw * 0.015))
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
        label = "<< REW  TODAY -> 1877"
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        bx0 = (W - tw) // 2 - 22
        by0 = 248
        bx1 = bx0 + tw + 44
        by1 = by0 + th + 22
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=12, fill=(10, 12, 18, 208), outline=(255, 255, 255, 232), width=2)
        draw.text((bx0 + 22 - tb[0], by0 + 11 - tb[1]), label, font=font, fill=(255, 255, 255, 255))
    return out


# ---------- Scene Config Definition (12 Scenes, v2 Multi-Shot) ----------

def build_scene_config(audio_meta: dict) -> dict:
    scenes_by_id = {s["id"]: s for s in audio_meta["scenes"]}

    specs = [
        {
            "id": "scene_01",
            "mode": "Mode A (3D Relief Map — Frame 0 Hook)",
            "keyframe": "keyframes/scene_01.jpg",
            "shots": [
                {"t": 0.00, "zoom": 2.04, "pan_x": -0.09, "pan_y": -0.05, "tilt_deg": 0.0, "end_zoom": 2.16, "end_pan_x": -0.08, "end_pan_y": -0.05, "end_tilt_deg": 0.5},
                {"t": 1.65, "zoom": 1.40, "pan_x": -0.02, "pan_y": -0.14, "tilt_deg": 0.0, "end_zoom": 1.48, "end_pan_x": -0.02, "end_pan_y": -0.14, "end_tilt_deg": 0.5},
                {"t": 2.75, "zoom": 2.10, "pan_x": -0.27, "pan_y": 0.04, "tilt_deg": -0.4, "end_zoom": 2.22, "end_pan_x": -0.26, "end_pan_y": 0.04, "end_tilt_deg": 0.4},
            ],
            "sprites": [
                {
                    "bbox": [0.31, 0.36, 0.55, 0.495],
                    "motion": "cheer_bounce",
                    "pop_delay": 0.0,
                },
                {
                    "bbox": [0.09, 0.495, 0.255, 0.625],
                    "motion": "glare_bob",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "INSIDE NEBRASKA?!", "cx": 420, "cy": 250, "trigger_rel": 1.70, "end_rel": 2.72, "style": "badge"},
            "foley": [
                {"rel": 0.02, "type": "pawn_bounce", "gain": 0.65},
                {"rel": 1.70, "type": "cork_pop", "gain": 0.65},
                {"rel": -0.50, "type": "tape_rewind", "gain": 0.72},
            ],
        },
        {
            "id": "scene_02",
            "mode": "Mode A (VHS Rewind -> 1877)",
            "keyframe": "keyframes/scene_02.jpg",
            "vhs_rewind": True,
            "shots": [
                {"t": 0.00, "zoom": 1.14, "pan_x": 0.0, "pan_y": -0.05, "tilt_deg": -0.8, "end_zoom": 1.04, "end_pan_x": 0.0, "end_pan_y": -0.02, "end_tilt_deg": 0.0},
                {"t": 1.02, "zoom": 1.78, "pan_x": 0.0, "pan_y": -0.28, "tilt_deg": 0.5, "end_zoom": 1.92, "end_pan_x": 0.0, "end_pan_y": -0.30, "end_tilt_deg": 0.0},
            ],
            "sprites": [],
            "overhead": None,
            "foley": [
                {"rel": 0.04, "type": "tape_rewind", "gain": 0.70},
                {"rel": 1.00, "type": "parchment_brush", "gain": 0.65},
            ],
        },
        {
            "id": "scene_03",
            "mode": "Mode A (3D Relief Map — 1846 Saratoga Bend)",
            "keyframe": "keyframes/scene_03.jpg",
            "shots": [
                {"t": 0.00, "zoom": 1.06, "pan_x": 0.0, "pan_y": -0.02, "tilt_deg": 0.0, "end_zoom": 1.15, "end_pan_x": 0.0, "end_pan_y": -0.03, "end_tilt_deg": 0.3},
                {"t": 2.68, "zoom": 2.04, "pan_x": 0.22, "pan_y": -0.02, "tilt_deg": -0.4, "end_zoom": 2.16, "end_pan_x": 0.22, "end_pan_y": -0.02, "end_tilt_deg": 0.3},
                {"t": 4.80, "zoom": 1.82, "pan_x": -0.06, "pan_y": 0.16, "tilt_deg": 0.3, "end_zoom": 1.96, "end_pan_x": -0.05, "end_pan_y": 0.16, "end_tilt_deg": -0.3},
                {"t": 6.60, "zoom": 1.10, "pan_x": 0.0, "pan_y": 0.02, "tilt_deg": 0.0, "end_zoom": 1.20, "end_pan_x": 0.0, "end_pan_y": 0.01, "end_tilt_deg": 0.5},
            ],
            "sprites": [
                {
                    "bbox": [0.55, 0.355, 0.90, 0.605],
                    "motion": "write_bob",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "SARATOGA BEND!", "cx": 360, "cy": 255, "trigger_rel": 6.62, "style": "badge"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 2.70, "type": "parchment_brush", "gain": 0.66},
                {"rel": 6.64, "type": "cork_pop", "gain": 0.60},
            ],
        },
        {
            "id": "scene_04",
            "mode": "Mode B (2.5D March 1877 Ice Jam Diorama)",
            "keyframe": "keyframes/scene_04.jpg",
            "impact_shake_rel": 3.50,
            "shots": [
                {"t": 0.00, "zoom": 1.06, "pan_x": 0.0, "pan_y": 0.0, "tilt_deg": -0.4, "end_zoom": 1.14, "end_pan_x": 0.0, "end_pan_y": 0.0, "end_tilt_deg": 0.3},
                {"t": 1.95, "zoom": 1.96, "pan_x": 0.02, "pan_y": -0.08, "tilt_deg": 0.4, "end_zoom": 2.10, "end_pan_x": 0.02, "end_pan_y": -0.08, "end_tilt_deg": -0.3},
                {"t": 3.45, "zoom": 1.98, "pan_x": 0.04, "pan_y": 0.08, "tilt_deg": -0.4, "end_zoom": 2.12, "end_pan_x": 0.04, "end_pan_y": 0.08, "end_tilt_deg": 0.4},
            ],
            "sprites": [],
            "overhead": {"text": "MARCH 1877!", "cx": 360, "cy": 500, "trigger_rel": 3.50, "style": "badge"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 0.15, "type": "river_rush", "gain": 0.56},
                {"rel": 2.20, "type": "ice_crash", "gain": 0.72},
                {"rel": 3.50, "type": "ice_crash", "gain": 0.80},
                {"rel": 3.55, "type": "cork_pop", "gain": 0.58},
            ],
        },
        {
            "id": "scene_05",
            "mode": "Mode A (3D Relief Map — Overnight Avulsion)",
            "keyframe": "keyframes/scene_05.jpg",
            "impact_shake_rel": 1.80,
            "shots": [
                {"t": 0.00, "zoom": 1.06, "pan_x": 0.0, "pan_y": -0.02, "tilt_deg": 0.0, "end_zoom": 1.14, "end_pan_x": 0.0, "end_pan_y": -0.02, "end_tilt_deg": -0.3},
                {"t": 1.78, "zoom": 1.96, "pan_x": 0.08, "pan_y": -0.06, "tilt_deg": -0.4, "end_zoom": 2.10, "end_pan_x": 0.08, "end_pan_y": 0.02, "end_tilt_deg": 0.4},
                {"t": 3.95, "zoom": 2.10, "pan_x": 0.28, "pan_y": -0.03, "tilt_deg": 0.4, "end_zoom": 2.22, "end_pan_x": 0.28, "end_pan_y": -0.03, "end_tilt_deg": -0.3},
                {"t": 5.15, "zoom": 1.12, "pan_x": 0.0, "pan_y": 0.06, "tilt_deg": 0.0, "end_zoom": 1.22, "end_pan_x": 0.0, "end_pan_y": 0.08, "end_tilt_deg": -0.6},
            ],
            "sprites": [
                {
                    "bbox": [0.785, 0.44, 0.945, 0.565],
                    "motion": "shudder",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "1 MILE EAST!", "cx": 250, "cy": 255, "trigger_rel": 5.18, "style": "badge"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 1.75, "type": "map_crack", "gain": 0.78},
                {"rel": 1.90, "type": "river_rush", "gain": 0.54},
                {"rel": 3.98, "type": "jaw_drop", "gain": 0.66},
                {"rel": 5.20, "type": "cork_pop", "gain": 0.58},
            ],
        },
        {
            "id": "scene_06",
            "mode": "Mode A (3D Relief Map — 1,300 Acres Stranded)",
            "keyframe": "keyframes/scene_06.jpg",
            "shots": [
                {"t": 0.00, "zoom": 1.82, "pan_x": -0.16, "pan_y": -0.01, "tilt_deg": 0.0, "end_zoom": 1.94, "end_pan_x": -0.15, "end_pan_y": -0.01, "end_tilt_deg": 0.3},
                {"t": 2.45, "zoom": 2.12, "pan_x": -0.14, "pan_y": -0.03, "tilt_deg": -0.4, "end_zoom": 2.24, "end_pan_x": -0.14, "end_pan_y": -0.03, "end_tilt_deg": 0.3},
                {"t": 4.60, "zoom": 1.08, "pan_x": 0.0, "pan_y": -0.02, "tilt_deg": 0.0, "end_zoom": 1.18, "end_pan_x": 0.0, "end_pan_y": -0.03, "end_tilt_deg": -0.5},
            ],
            "sprites": [
                {
                    "bbox": [0.27, 0.345, 0.445, 0.50],
                    "motion": "shudder",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "1,300 ACRES STRANDED!", "cx": 360, "cy": 235, "trigger_rel": 4.65, "style": "badge"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 2.50, "type": "jaw_drop", "gain": 0.68},
                {"rel": 4.65, "type": "cork_pop", "gain": 0.60},
            ],
        },
        {
            "id": "scene_07",
            "mode": "Mode A (3D Relief Map — Nebraska vs. Iowa Feud)",
            "keyframe": "keyframes/scene_07.jpg",
            "impact_shake_rel": 4.28,
            "shots": [
                {"t": 0.00, "zoom": 1.08, "pan_x": 0.0, "pan_y": -0.04, "tilt_deg": 0.0, "end_zoom": 1.16, "end_pan_x": 0.0, "end_pan_y": -0.04, "end_tilt_deg": -0.3},
                {"t": 1.88, "zoom": 2.14, "pan_x": -0.20, "pan_y": -0.12, "tilt_deg": 0.4, "end_zoom": 2.26, "end_pan_x": -0.19, "end_pan_y": -0.12, "end_tilt_deg": -0.3},
                {"t": 4.25, "zoom": 2.14, "pan_x": 0.25, "pan_y": -0.05, "tilt_deg": -0.4, "end_zoom": 2.28, "end_pan_x": 0.25, "end_pan_y": -0.05, "end_tilt_deg": 0.4},
            ],
            "sprites": [
                {
                    "bbox": [0.15, 0.265, 0.445, 0.47],
                    "motion": "lunge_right",
                    "pop_delay": 0.0,
                },
                {
                    "bbox": [0.60, 0.34, 0.93, 0.58],
                    "motion": "lunge_left",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": None,
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 1.92, "type": "cork_pop", "gain": 0.62},
                {"rel": 4.28, "type": "steam_whistle", "gain": 0.72},
            ],
        },
        {
            "id": "scene_08",
            "mode": "Mode A (3D Relief Map — 1892 Supreme Court Avulsion Rule)",
            "keyframe": "keyframes/scene_08.jpg",
            "shots": [
                {"t": 0.00, "zoom": 2.04, "pan_x": 0.12, "pan_y": -0.13, "tilt_deg": -0.3, "end_zoom": 2.16, "end_pan_x": 0.12, "end_pan_y": -0.13, "end_tilt_deg": 0.3},
                {"t": 2.75, "zoom": 1.08, "pan_x": 0.0, "pan_y": -0.02, "tilt_deg": 0.0, "end_zoom": 1.16, "end_pan_x": 0.0, "end_pan_y": -0.02, "end_tilt_deg": 0.4},
                {"t": 4.80, "zoom": 1.96, "pan_x": -0.18, "pan_y": 0.0, "tilt_deg": 0.3, "end_zoom": 2.08, "end_pan_x": -0.17, "end_pan_y": 0.0, "end_tilt_deg": -0.3},
                {"t": 6.75, "zoom": 2.06, "pan_x": 0.28, "pan_y": 0.08, "tilt_deg": -0.4, "end_zoom": 2.18, "end_pan_x": 0.28, "end_pan_y": 0.08, "end_tilt_deg": 0.3},
            ],
            "sprites": [],
            "overhead": None,
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 2.80, "type": "parchment_brush", "gain": 0.66},
                {"rel": 6.80, "type": "cork_pop", "gain": 0.62},
            ],
        },
        {
            "id": "scene_09",
            "mode": "Mode A (3D Relief Map — Unanimous Victory to Iowa)",
            "keyframe": "keyframes/scene_09.jpg",
            "impact_shake_rel": 2.58,
            "shots": [
                {"t": 0.00, "zoom": 1.08, "pan_x": 0.0, "pan_y": -0.02, "tilt_deg": 0.0, "end_zoom": 1.18, "end_pan_x": 0.0, "end_pan_y": -0.03, "end_tilt_deg": 0.4},
                {"t": 2.55, "zoom": 2.12, "pan_x": -0.08, "pan_y": -0.04, "tilt_deg": -0.3, "end_zoom": 2.26, "end_pan_x": -0.08, "end_pan_y": -0.04, "end_tilt_deg": 0.4},
            ],
            "sprites": [
                {
                    "bbox": [0.33, 0.395, 0.53, 0.52],
                    "motion": "cheer_bounce",
                    "pop_delay": 0.0,
                },
                {
                    "bbox": [0.08, 0.535, 0.22, 0.655],
                    "motion": "glare_bob_alt",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "IOWA WINS!", "cx": 360, "cy": 285, "trigger_rel": 0.85, "end_rel": 2.52, "style": "badge"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 0.88, "type": "cork_pop", "gain": 0.58},
                {"rel": 2.56, "type": "gavel_slam", "gain": 0.86},
                {"rel": 2.85, "type": "celesta_chime", "gain": 0.68},
                {"rel": 3.40, "type": "celesta_chime_hi", "gain": 0.64},
            ],
        },
        {
            "id": "scene_10",
            "mode": "Mode B (2.5D Omaha Airport & Welcome Signs Diorama)",
            "keyframe": "keyframes/scene_10.jpg",
            "shots": [
                {"t": 0.00, "zoom": 1.06, "pan_x": 0.0, "pan_y": 0.02, "tilt_deg": 0.0, "end_zoom": 1.15, "end_pan_x": 0.0, "end_pan_y": 0.02, "end_tilt_deg": 0.3},
                {"t": 2.65, "zoom": 2.04, "pan_x": -0.22, "pan_y": -0.03, "tilt_deg": -0.3, "end_zoom": 2.16, "end_pan_x": -0.21, "end_pan_y": -0.03, "end_tilt_deg": 0.3},
                {"t": 6.15, "zoom": 2.02, "pan_x": 0.16, "pan_y": -0.08, "tilt_deg": 0.4, "end_zoom": 2.16, "end_pan_x": 0.18, "end_pan_y": -0.09, "end_tilt_deg": -0.3},
                {"t": 7.70, "zoom": 2.08, "pan_x": 0.14, "pan_y": 0.11, "tilt_deg": -0.3, "end_zoom": 2.20, "end_pan_x": 0.14, "end_pan_y": 0.11, "end_tilt_deg": 0.4},
            ],
            "sprites": [],
            "overhead": {"text": "WAIT... IOWA?!", "cx": 485, "cy": 565, "trigger_rel": 7.75, "style": "cloud"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 6.15, "type": "jet_flyby", "gain": 0.56},
                {"rel": 7.78, "type": "cork_pop", "gain": 0.62},
            ],
        },
        {
            "id": "scene_11",
            "mode": "Mode A (3D Relief Map — Cross Nebraska to Reach Iowa)",
            "keyframe": "keyframes/scene_11.jpg",
            "shots": [
                {"t": 0.00, "zoom": 1.92, "pan_x": -0.20, "pan_y": -0.26, "tilt_deg": 0.0, "end_zoom": 2.04, "end_pan_x": -0.20, "end_pan_y": -0.26, "end_tilt_deg": 0.3},
                {"t": 1.60, "zoom": 2.02, "pan_x": -0.22, "pan_y": 0.15, "tilt_deg": -0.3, "end_zoom": 2.14, "end_pan_x": -0.20, "end_pan_y": 0.16, "end_tilt_deg": 0.3},
                {"t": 2.85, "zoom": 1.08, "pan_x": 0.0, "pan_y": 0.02, "tilt_deg": 0.0, "end_zoom": 1.18, "end_pan_x": 0.0, "end_pan_y": 0.03, "end_tilt_deg": 0.5},
            ],
            "sprites": [
                {
                    "bbox": [0.21, 0.62, 0.315, 0.69],
                    "motion": "car_drive",
                    "pop_delay": 0.0,
                },
                {
                    "bbox": [0.68, 0.70, 0.77, 0.785],
                    "motion": "glare_bob",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": {"text": "VIA NEBRASKA!", "cx": 360, "cy": 360, "trigger_rel": 2.88, "style": "badge"},
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.45},
                {"rel": 2.90, "type": "cork_pop", "gain": 0.60},
            ],
        },
        {
            "id": "scene_12",
            "mode": "Mode A (3D Relief Map + Comment Panel + Loop)",
            "keyframe": "keyframes/scene_12.jpg",
            "shots": [
                {"t": 0.00, "zoom": 1.01, "pan_x": 0.0, "pan_y": 0.0, "tilt_deg": 0.0, "end_zoom": 1.06, "end_pan_x": 0.0, "end_pan_y": -0.01, "end_tilt_deg": 0.2},
                {"t": 1.45, "zoom": 1.08, "pan_x": 0.0, "pan_y": -0.02, "tilt_deg": -0.2, "end_zoom": 1.13, "end_pan_x": 0.0, "end_pan_y": -0.03, "end_tilt_deg": 0.2},
            ],
            "sprites": [
                {
                    "bbox": [0.075, 0.175, 0.345, 0.405],
                    "motion": "football_hop_l",
                    "pop_delay": 0.0,
                },
                {
                    "bbox": [0.675, 0.195, 0.955, 0.405],
                    "motion": "football_hop_r",
                    "pop_delay": 0.0,
                },
            ],
            "overhead": None,
            "comment_panel": {
                "trigger_rel": 0.14,
                "keyword": "IOWA",
                "comments": [
                    {"handle": "@IowaHawkeye", "text": "IOWA! Supreme Court settled it!", "likes": "814 ♥", "color": [26, 78, 198]},
                    {"handle": "@OmahaLocal", "text": "NEBRASKA! It's on our side!!", "likes": "629 ♥", "color": [196, 38, 38]},
                ],
            },
            "loop_return_sec": 0.30,
            "foley": [
                {"rel": 0.04, "type": "camera_whoosh", "gain": 0.46},
                {"rel": 0.18, "type": "stadium_swell", "gain": 0.42},
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
            "subtitle_panel_y_ratio": 0.47,
            "version": "v2",
            "voice_provider": "Fish Audio S2.1 Pro — Ethan (@Fish Official)",
        },
        "total_duration_sec": audio_meta["total_duration_sec"],
        "scenes": specs,
    }


def mix_foley_and_voice(config: dict, audio_meta: dict, voice_wav_path: Path, out_wav_path: Path):
    with wave.open(str(voice_wav_path), "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        voice = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    foley_buf = np.zeros_like(voice)
    total_dur = len(voice) / SR

    for sc in config["scenes"]:
        s0, s1 = sc["start_sec"], sc["end_sec"]
        dur = s1 - s0

        shots = sc.get("shots", [])
        for idx in range(1, len(shots)):
            if abs(shots[idx]["zoom"] - shots[idx - 1].get("end_zoom", shots[idx - 1]["zoom"])) >= 0.45:
                fm.add_sound(foley_buf, s0 + shots[idx]["t"], fm.foley_punch_zoom(), gain=0.34)

        cp = sc.get("comment_panel")
        if cp:
            t_panel = s0 + cp["trigger_rel"]
            kw = cp["keyword"]
            for ci in range(len(kw)):
                fm.add_sound(foley_buf, t_panel + 0.30 + ci * (0.78 / max(1, len(kw))), fm.foley_type_click(), gain=0.52)
            fm.add_sound(foley_buf, t_panel + 1.14, fm.foley_cork_pop(), gain=0.55)
            fm.add_sound(foley_buf, t_panel + 0.85, fm.foley_type_click(), gain=0.40)
            fm.add_sound(foley_buf, t_panel + 1.40, fm.foley_cork_pop(), gain=0.45)

        if sc.get("loop_return_sec"):
            fm.add_sound(foley_buf, s1 - sc["loop_return_sec"], fm.foley_punch_zoom(0.24), gain=0.40)

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
            elif ctype == "map_crack":
                snd = fm.foley_map_crack_and_tear()
            elif ctype == "jaw_drop":
                snd = fm.foley_jaw_drop_clatter()
            elif ctype == "river_rush":
                snd = foley_river_rush(duration=min(4.4, max(2.0, dur - 0.3)))
            elif ctype == "ice_crash":
                snd = foley_ice_crash()
            elif ctype == "steam_whistle":
                snd = foley_steam_whistle()
            elif ctype == "gavel_slam":
                snd = foley_gavel_slam()
            elif ctype == "jet_flyby":
                snd = foley_jet_flyby(duration=1.9)
            elif ctype == "celesta_chime":
                snd = fm.foley_celesta_chime(freq=1046.5)
            elif ctype == "celesta_chime_hi":
                snd = fm.foley_celesta_chime(freq=1318.5)
            elif ctype == "stadium_swell":
                snd = foley_stadium_swell(duration=min(3.2, max(1.8, dur - 0.4)))
            else:
                continue

            fm.add_sound(foley_buf, t_abs, snd, gain=gain)

    mixed = fm.mix_voice_foley_and_bed(
        voice,
        foley_buf,
        audio_meta["words"],
        bpm=96.0,
        seed=505,
        voice_gain=0.96,
        foley_gain=0.56,
        bed_under_speech=0.15,
        bed_in_pauses=0.46,
    )

    pcm16 = (np.clip(mixed, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(out_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm16.tobytes())
    print(f"Mixed audio (Ethan + foley + auto-ducked acoustic bed) saved to {out_wav_path} ({total_dur:.2f}s)")


def compute_sprite_transform(motion: str, local_t: float, sp_cfg: dict):
    pop_delay = sp_cfg.get("pop_delay", 0.0)
    sc = 1.0 if pop_delay <= 0.0 else eng.spring_scale(local_t - pop_delay, rise=0.30)
    dx, dy, ang = 0.0, 0.0, 0.0
    t = max(0.0, local_t - pop_delay)

    if motion == "lunge_right":
        dx = 8.0 * math.sin(t * 2.8) * (0.5 + 0.5 * math.sin(t * 1.3))
        dy = -4.0 * abs(math.sin(t * 4.0))
        ang = -3.0 * math.sin(t * 2.8)
    elif motion == "lunge_left":
        dx = -8.0 * math.sin(t * 2.8) * (0.5 + 0.5 * math.sin(t * 1.3))
        dy = -4.0 * abs(math.sin(t * 4.0))
        ang = 3.0 * math.sin(t * 2.8)
    elif motion == "write_bob":
        dx = 6.0 * math.sin(t * 2.2)
        dy = -5.0 * abs(math.sin(t * 4.2))
        ang = 3.8 * math.sin(t * 2.8)
    elif motion == "shudder":
        dx = 5.0 * math.sin(t * 36.0) * math.exp(-max(0.0, t - 2.0) * 0.25)
        dy = -4.0 * abs(math.sin(t * 6.0))
        ang = 3.5 * math.sin(t * 18.0)
    elif motion == "glare_bob":
        dy = -5.0 * abs(math.sin(t * 3.2))
        ang = 2.5 * math.sin(t * 2.4)
    elif motion == "glare_bob_alt":
        dy = -5.0 * abs(math.sin(t * 3.2 + 1.1))
        ang = -2.5 * math.sin(t * 2.4 + 0.8)
    elif motion == "car_drive":
        sc = 1.0
        dx = 10.0 * math.sin(local_t * 1.1)
        dy = 12.0 * math.sin(local_t * 1.1) - 2.0 * abs(math.sin(local_t * 8.0))
        ang = 3.0 * math.sin(local_t * 4.5)
    elif motion == "cheer_bounce":
        dy = -12.0 * abs(math.sin(t * 5.0))
        ang = 4.5 * math.sin(t * 5.0)
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

    voice_wav = EP_DIR / "carter_lake.wav"
    if not voice_wav.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(EP_DIR / "carter_lake.mp3"), "-ar", str(SR), "-ac", "1", str(voice_wav)],
            check=True,
        )
    mixed_wav = EP_DIR / "carter_lake_mixed.wav"
    mix_foley_and_voice(config, audio_meta, voice_wav, mixed_wav)

    subtitle_cards = build_subtitle_cards(audio_meta["scenes"])

    print("Extracting sprites & inpainting backgrounds...")
    prepared_scenes = prepare_scene_assets(config)

    sub_font = load_font(44, bold=True)
    ov_font = load_font(26, bold=True)
    vhs_font = load_font(30, bold=True)
    panel_title_font = load_font(22, bold=True)
    panel_input_font = load_font(24, bold=True)
    panel_body_font = load_font(22, bold=True)
    panel_small_font = load_font(18, bold=True)

    qa_dir = EP_DIR / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    s_map = {sc["id"]: sc for sc in config["scenes"]}
    qa_targets = {
        "scene_01_frame0": 0,
        "scene_01_wide": int((s_map["scene_01"]["start_sec"] + 2.15) * FPS),
        "scene_04_ice": int((s_map["scene_04"]["start_sec"] + 3.90) * FPS),
        "scene_05_channel": int((s_map["scene_05"]["start_sec"] + 4.35) * FPS),
        "scene_06_farmer": int((s_map["scene_06"]["start_sec"] + 3.10) * FPS),
        "scene_07_iowa_mad": int((s_map["scene_07"]["start_sec"] + 5.15) * FPS),
        "scene_08_avulsion": int((s_map["scene_08"]["start_sec"] + 7.40) * FPS),
        "scene_09_win": int((s_map["scene_09"]["start_sec"] + 3.25) * FPS),
        "scene_10_signs": int((s_map["scene_10"]["start_sec"] + 3.80) * FPS),
        "scene_10_driver": int((s_map["scene_10"]["start_sec"] + 8.35) * FPS),
        "scene_12_panel": int((s_map["scene_12"]["start_sec"] + 2.20) * FPS),
        "scene_12_loop": int((config["total_duration_sec"] - 0.14) * FPS),
    }

    total_frames = int(math.ceil(config["total_duration_sec"] * FPS))
    out_mp4 = EP_DIR / "heartland_mapped_ep05_carter_lake.mp4"

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
    frame0_rgba = None

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

        canvas = active["bg_rgba"].copy()

        for sp_rgba, base_rect, sp_cfg in active["sprites"]:
            dx, dy, scale, ang = compute_sprite_transform(sp_cfg["motion"], local_t, sp_cfg)
            eng.paste_moving_sprite(canvas, sp_rgba, base_rect, dx=dx, dy=dy, scale=scale, angle_deg=ang, shadow=True)

        ov = sc.get("overhead")
        if ov and ov["trigger_rel"] <= local_t < ov.get("end_rel", 999.0):
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

        zoom, pan_x, pan_y, tilt, cut_blur = eng.eval_shot_camera(sc["shots"], local_t, dur)

        if "impact_shake_rel" in sc:
            dt_imp = local_t - sc["impact_shake_rel"]
            if 0.0 <= dt_imp < 0.40:
                decay = math.exp(-dt_imp * 9.0)
                pan_x += 0.013 * math.sin(dt_imp * 55.0) * decay
                pan_y += 0.011 * math.cos(dt_imp * 48.0) * decay

        t_blur = cut_blur
        if local_t < 0.11 and sc["id"] != "scene_01":
            t_blur = max(t_blur, (1.0 - local_t / 0.11) * 0.50)
        elif (dur - local_t) < 0.10 and sc["id"] != "scene_12":
            t_blur = max(t_blur, (1.0 - (dur - local_t) / 0.10) * 0.50)

        frame = eng.apply_25d_camera(canvas, zoom, pan_x, pan_y, tilt, transition_blur=t_blur, width=W, height=H)

        if f_idx == 0:
            frame0_rgba = frame.copy()

        if sc.get("vhs_rewind") or (sc["id"] == "scene_01" and (dur - local_t) < 0.36):
            vhs_p = prog if sc.get("vhs_rewind") else (1.0 - (dur - local_t) / 0.36)
            frame = apply_vhs_rewind(frame, vhs_p, vhs_font)

        cp = sc.get("comment_panel")
        panel_active = False
        if cp and local_t >= cp["trigger_rel"]:
            loop_sec = sc.get("loop_return_sec", 0.0)
            if (dur - local_t) > loop_sec * 0.55:
                panel_active = True
                eng.draw_animated_comment_panel(
                    frame,
                    local_t - cp["trigger_rel"],
                    cp["keyword"],
                    cp["comments"],
                    panel_title_font,
                    panel_input_font,
                    panel_body_font,
                    panel_small_font,
                    width=W,
                    height=H,
                )

        loop_sec = sc.get("loop_return_sec", 0.0)
        in_loop_return = False
        if loop_sec > 0.0 and frame0_rgba is not None and (dur - local_t) <= loop_sec:
            in_loop_return = True
            lp = smoothstep(1.0 - (dur - local_t) / loop_sec)
            frame = Image.blend(frame, frame0_rgba, lp)
            whip = math.sin(lp * math.pi) * 0.45
            if whip > 0.06:
                ksize = max(3, int(whip * 21) | 1)
                arr = np.array(frame)
                kernel = np.zeros((ksize, ksize), dtype=np.float32)
                kernel[ksize // 2, :] = 1.0 / ksize
                arr[:, :, :3] = cv2.filter2D(arr[:, :, :3], -1, kernel)
                frame = Image.fromarray(arr)

        while sub_idx < len(subtitle_cards) and subtitle_cards[sub_idx]["end"] < t:
            sub_idx += 1
        if not in_loop_return and sub_idx < len(subtitle_cards):
            card = subtitle_cards[sub_idx]
            if card["start"] <= t <= card["end"]:
                sub_y = 0.47 if panel_active else 0.79
                draw_subtitle_card(frame, card["text"], sub_font, y_ratio=sub_y)

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
    print(f"SUCCESS! Final Ep 05 v2 video saved to: {out_mp4}")


if __name__ == "__main__":
    main()
