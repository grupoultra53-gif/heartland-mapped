"""
Heartland Mapped — Universal v2 Retention-Optimized 2.5D Episode Renderer
Reads `episode_spec.json` + `audio_timings.json` inside any episode folder and renders:
  - 720x1280 @ 30 FPS H.264 / AAC 192 kbps MP4
  - Immediate Frame 0 Hook (visible focal sprites + close-up zoom)
  - Word-synced multi-shot close-ups & reaction cuts (engine_25d.eval_shot_camera)
  - Full situational procedural foley library + auto-ducked Americana acoustic bed
  - Animated 1-word CTA comment panel + automatic subtitle lift (y=0.47)
  - Seamless visual whip-return loop into Scene 01 Frame 0
  - Automated QA frame captures

Usage:
  .\\.venv\\Scripts\\python.exe .agents\\skills\\historical-map-animation\\scripts\\render_episode_v2.py episodes\\ep06_kentucky_bend
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

SKILL_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS))

import engine_25d as eng
import foley_mixer as fm

W, H, FPS = 720, 1280, 30
SR = fm.SR


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
            r"C:\Windows\Fonts\impact.ttf",
        ]
        if bold
        else [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]
    )
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---------- Extended Procedural Situational Foley Library ----------

def foley_river_rush(duration: float = 4.0) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    roar = fm.bandpass(np.random.normal(0, 1, n), 160, 1400) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.45 * t))
    sub = fm.lowpass(np.random.normal(0, 1, n), 180) * 0.55
    return (roar * 0.42 + sub * 0.35) * (np.sin(np.pi * (t / duration)) ** 0.75)


def foley_quake_rumble(duration: float = 3.2) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    sub = fm.lowpass(np.random.normal(0, 1, n), 110) * 1.15
    gravel = fm.bandpass(np.random.normal(0, 1, n), 220, 1200) * (0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 3.5 * t))) * 0.45
    return (sub + gravel) * (np.sin(np.pi * (t / duration)) ** 0.65)


def foley_fire_roar(duration: float = 4.0) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    roar = fm.bandpass(np.random.normal(0, 1, n), 140, 950) * (0.65 + 0.35 * np.sin(2 * np.pi * 1.1 * t))
    crackle = np.zeros(n)
    rng = np.random.default_rng(71)
    for _ in range(int(duration * 18)):
        pos = int(rng.integers(0, max(1, n - 400)))
        crackle[pos : pos + 350] += fm.bandpass(rng.normal(0, 1, 350), 2400, 6800) * np.exp(-np.linspace(0, 8, 350)) * 0.55
    return (roar * 0.45 + crackle * 0.50) * (np.sin(np.pi * (t / duration)) ** 0.7)


def foley_storm_gale(duration: float = 4.2) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    wind = fm.bandpass(np.random.normal(0, 1, n), 220, 1650) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.38 * t))
    howl_f = 420 + 130 * np.sin(2 * np.pi * 0.32 * t)
    howl = np.sin(2 * np.pi * np.cumsum(howl_f) / SR) * 0.16
    waves = fm.lowpass(np.random.normal(0, 1, n), 220) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t)) * 0.55
    return (wind * 0.36 + howl + waves * 0.42) * (np.sin(np.pi * (t / duration)) ** 0.75)


def foley_ship_horn(duration: float = 1.9, base_f: float = 98.0) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    horn = sum(np.sin(2 * np.pi * base_f * k * t) * amp for k, amp in [(1, 0.60), (2, 0.42), (3, 0.25), (4, 0.14)])
    return horn * (np.sin(np.pi * (t / duration)) ** 0.85) * 0.48


def foley_church_bell(duration: float = 2.6, f0: float = 392.0) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    bell = (
        np.sin(2 * np.pi * f0 * t) * 0.55
        + np.sin(2 * np.pi * f0 * 2.0 * t) * 0.35 * np.exp(-t * 2.2)
        + np.sin(2 * np.pi * f0 * 2.76 * t) * 0.22 * np.exp(-t * 3.5)
    ) * np.exp(-t * 1.4)
    return bell * 0.52


def foley_jackscrew_ratchet(duration: float = 1.4) -> np.ndarray:
    n = int(duration * SR)
    out = np.zeros(n)
    for k in range(int(duration / 0.18)):
        idx = int(k * 0.18 * SR)
        cn = int(0.08 * SR)
        if idx + cn <= n:
            ct = np.linspace(0, 0.08, cn, endpoint=False)
            clank = (np.sin(2 * np.pi * 1650 * ct) * 0.4 + fm.bandpass(np.random.normal(0, 1, cn), 900, 4800) * 0.6) * np.exp(-ct * 42.0)
            out[idx : idx + cn] += clank * 0.65
    return out


def foley_whistle_blast(duration: float = 0.55) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    pea = 2650 + 140 * np.sin(2 * np.pi * 34 * t)
    sig = np.sin(2 * np.pi * np.cumsum(pea) / SR) * 0.36 + fm.bandpass(np.random.normal(0, 1, n), 2200, 5200) * 0.25
    return sig * (np.sin(np.pi * (t / duration)) ** 0.55)


def foley_car_honk() -> np.ndarray:
    n = int(0.45 * SR)
    out = np.zeros(n)
    for start in (0.0, 0.20):
        idx = int(start * SR)
        cn = int(0.14 * SR)
        ct = np.linspace(0, 0.14, cn, endpoint=False)
        horn = (np.sin(2 * np.pi * 415 * ct) + np.sin(2 * np.pi * 523 * ct) + 0.4 * np.sin(2 * np.pi * 830 * ct)) * np.sin(np.pi * ct / 0.14)
        out[idx : idx + cn] += horn * 0.24
    return out


def foley_gavel_slam() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.linspace(0, 0.45, n, endpoint=False)
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(160, 46, n)) / SR) * np.exp(-t * 14.0)
    wood = fm.bandpass(np.random.normal(0, 1, n), 450, 2600) * np.exp(-t * 28.0) * 0.78
    return (thud * 0.95 + wood) * 0.88


def foley_telegraph_beeps(duration: float = 1.2) -> np.ndarray:
    n = int(duration * SR)
    out = np.zeros(n)
    pattern = [0.0, 0.14, 0.28, 0.52, 0.66, 0.88]
    for st in pattern:
        idx = int(st * SR)
        cn = int(0.08 * SR)
        if idx + cn <= n:
            ct = np.linspace(0, 0.08, cn, endpoint=False)
            out[idx : idx + cn] += np.sin(2 * np.pi * 920 * ct) * np.sin(np.pi * ct / 0.08) * 0.35
    return out


def foley_stadium_swell(duration: float = 3.2) -> np.ndarray:
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    crowd = fm.bandpass(np.random.normal(0, 1, n), 240, 1900)
    low = fm.lowpass(np.random.normal(0, 1, n), 320) * 0.5
    return (crowd * 0.34 + low * 0.22) * (np.sin(np.pi * (t / duration)) ** 1.15)


def foley_water_splash() -> np.ndarray:
    n = int(0.65 * SR)
    t = np.linspace(0, 0.65, n, endpoint=False)
    plop = np.sin(2 * np.pi * np.cumsum(np.linspace(260, 560, n)) / SR) * np.exp(-t * 14.0) * 0.52
    splash = fm.bandpass(np.random.normal(0, 1, n), 550, 4200) * np.exp(-t * 6.5) * 0.65
    return (plop + splash) * 0.75


# ---------- Subtitles ----------

def restore_punct(scene_text: str, words: list) -> list:
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
        words = restore_punct(sc.get("text", ""), raw_words)
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
            cards.append({"start": chunk[0]["start"], "end": chunk[-1]["end"] + 0.14, "text": text})
    if cards and scenes_meta:
        cards[-1]["end"] = max(cards[-1]["end"], scenes_meta[-1]["end_sec"] - 0.18)
    for idx in range(len(cards) - 1):
        if cards[idx]["end"] > cards[idx + 1]["start"]:
            cards[idx]["end"] = max(cards[idx]["start"] + 0.08, cards[idx + 1]["start"] - 0.02)
    return cards


def draw_subtitle_card(canvas_rgba: Image.Image, text: str, font, highlight_words: set, y_ratio: float = 0.79):
    if not text:
        return
    draw = ImageDraw.Draw(canvas_rgba)
    upper_text = text.upper()
    cur_font = font
    bbox = draw.textbbox((0, 0), upper_text, font=cur_font, stroke_width=5)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw > W - 110:
        cur_font = load_font(max(30, int(font.size * (W - 120) / tw)), bold=True)
        bbox = draw.textbbox((0, 0), upper_text, font=cur_font, stroke_width=5)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    cx, cy = W // 2, int(H * y_ratio)
    pad_x, pad_y = 22, 12
    x0, y0 = cx - tw // 2 - pad_x, cy - th // 2 - pad_y
    x1, y1 = cx + tw // 2 + pad_x, cy + th // 2 + pad_y

    pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([x0, y0, x1, y1], radius=16, fill=(14, 14, 18, 188))
    canvas_rgba.alpha_composite(pill)

    clean_tokens = upper_text.split()
    has_kw = any(tok.strip(".,?!—:\"'") in highlight_words for tok in clean_tokens)
    fill_col = (255, 224, 72, 255) if has_kw and len(clean_tokens) <= 3 else (255, 255, 255, 255)
    ImageDraw.Draw(canvas_rgba).text(
        (cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]),
        upper_text,
        font=cur_font,
        fill=fill_col,
        stroke_width=5,
        stroke_fill=(12, 12, 16, 255),
    )


def extract_sprite_clean(pil_img: Image.Image, bbox_norm: list, exclude_rects: list = None):
    rgb = np.array(pil_img)
    x0, y0 = max(0, int(bbox_norm[0] * W)), max(0, int(bbox_norm[1] * H))
    x1, y1 = min(W, int(bbox_norm[2] * W)), min(H, int(bbox_norm[3] * H))
    patch = rgb[y0:y1, x0:x1].copy()
    ph, pw = patch.shape[:2]

    mask = np.full((ph, pw), cv2.GC_PR_FGD, dtype=np.uint8)
    m = max(4, min(8, min(ph, pw) // 18))
    mask[:m, :] = mask[-m:, :] = mask[:, :m] = mask[:, -m:] = cv2.GC_BGD
    if exclude_rects:
        for er in exclude_rects:
            ex0, ey0 = max(0, int(er[0] * W) - x0), max(0, int(er[1] * H) - y0)
            ex1, ey1 = min(pw, int(er[2] * W) - x0), min(ph, int(er[3] * H) - y0)
            if ex1 > ex0 and ey1 > ey0:
                mask[ey0:ey1, ex0:ex1] = cv2.GC_BGD

    bgd_m = np.zeros((1, 65), np.float64)
    fgd_m = np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(patch, cv2.COLOR_RGB2BGR), mask, None, bgd_m, fgd_m, 5, cv2.GC_INIT_WITH_MASK)

    fg_bin = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if exclude_rects:
        for er in exclude_rects:
            ex0, ey0 = max(0, int(er[0] * W) - x0), max(0, int(er[1] * H) - y0)
            ex1, ey1 = min(pw, int(er[2] * W) - x0), min(ph, int(er[3] * H) - y0)
            if ex1 > ex0 and ey1 > ey0:
                fg_bin[ey0:ey1, ex0:ex1] = 0

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg_bin = cv2.morphologyEx(cv2.morphologyEx(fg_bin, cv2.MORPH_OPEN, k, iterations=1), cv2.MORPH_CLOSE, k, iterations=2)
    contours, _ = cv2.findContours(fg_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(fg_bin)
    min_area = max(140, int(ph * pw * 0.015))
    for cnt in contours:
        if cv2.contourArea(cnt) >= min_area:
            cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)
    if np.count_nonzero(filled) < ph * pw * 0.04:
        return eng.extract_sprite_and_inpaint_bg(pil_img, bbox_norm, width=W, height=H)

    full_mask = np.zeros((H, W), dtype=np.uint8)
    full_mask[y0:y1, x0:x1] = cv2.dilate(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)), iterations=1)
    if exclude_rects:
        for er in exclude_rects:
            full_mask[max(0, int(er[1] * H)) : min(H, int(er[3] * H)), max(0, int(er[0] * W)) : min(W, int(er[2] * W))] = 0
    inpainted = cv2.inpaint(rgb, full_mask, 7, cv2.INPAINT_TELEA)
    sprite_rgba = np.dstack([patch, cv2.GaussianBlur(filled, (3, 3), 0)])
    return Image.fromarray(inpainted), Image.fromarray(sprite_rgba), (x0, y0, pw, ph)


def draw_overhead_crisp(canvas_rgba, cx, cy, text, prog_in, font, style="cloud"):
    if prog_in <= 0.02:
        return
    scale = (prog_in / 0.65 * 1.10) if prog_in < 0.65 else (1.10 - 0.10 * ((prog_in - 0.65) / 0.35))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bw, bh = int((tw + 40) * scale), int((th + 26) * scale)
    x0 = int(np.clip(cx - bw // 2, 16, W - bw - 16))
    y0 = int(np.clip(cy - bh // 2, 16, H - bh - 16))
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
        draw.multiline_text((x0 + (bw - tw) // 2 - bbox[0], y0 + (bh - th) // 2 - bbox[1]), text, font=font, fill=fg_col, align="center", spacing=4)
    canvas_rgba.alpha_composite(layer)


def apply_vhs_rewind(frame_rgba: Image.Image, progress: float, font, label: str) -> Image.Image:
    arr = np.array(frame_rgba).copy()
    arr[::4, :, :3] = (arr[::4, :, :3] * 0.72).astype(np.uint8)
    shift = max(2, int(5 + 3 * math.sin(progress * 28.0)))
    arr[:, shift:, 0] = arr[:, :-shift, 0]
    arr[:, :-shift, 2] = arr[:, shift:, 2]
    bar_y = int((1.0 - (progress * 1.8 % 1.0)) * (H - 40))
    arr[bar_y : bar_y + 28, :, :3] = np.clip(arr[bar_y : bar_y + 28, :, :3].astype(np.int16) + np.random.randint(-35, 35, (28, W, 3)), 0, 255).astype(np.uint8)
    out = Image.fromarray(arr, mode="RGBA")
    draw = ImageDraw.Draw(out)
    if int(progress * 10) % 2 == 0 or progress < 0.75:
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        bx0, by0 = (W - tw) // 2 - 22, 248
        draw.rounded_rectangle([bx0, by0, bx0 + tw + 44, by0 + th + 22], radius=12, fill=(10, 12, 18, 208), outline=(255, 255, 255, 232), width=2)
        draw.text((bx0 + 22 - tb[0], by0 + 11 - tb[1]), label, font=font, fill=(255, 255, 255, 255))
    return out


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
    elif motion == "ship_rock":
        sc = 1.0
        dx = -9.0 * math.sin(local_t * 0.85)
        dy = 4.0 * math.sin(local_t * 2.6)
        ang = 5.0 * math.sin(local_t * 2.1)
    elif motion == "car_drive":
        sc = 1.0
        dx = 12.0 * math.sin(local_t * 1.05)
        dy = -2.0 * abs(math.sin(local_t * 8.0)) + 6.0 * math.sin(local_t * 1.05)
        ang = 2.5 * math.sin(local_t * 4.5)
    elif motion == "rise_lift":
        sc = 1.0
        dy = -16.0 * smoothstep(min(1.0, local_t / 3.5))
        dx = 1.5 * math.sin(local_t * 14.0)
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


def build_foley_clip(ctype: str, dur: float):
    if ctype == "camera_whoosh": return fm.foley_camera_whoosh()
    if ctype == "pawn_bounce": return fm.foley_pawn_bounce()
    if ctype == "cork_pop": return fm.foley_cork_pop()
    if ctype == "parchment_brush": return fm.foley_parchment_brush()
    if ctype == "tape_rewind": return fm.foley_tape_rewind()
    if ctype == "map_crack": return fm.foley_map_crack_and_tear()
    if ctype == "jaw_drop": return fm.foley_jaw_drop_clatter()
    if ctype == "ocean_ship": return fm.foley_ocean_and_ship(duration=min(4.8, max(2.0, dur - 0.3)))
    if ctype == "river_rush": return foley_river_rush(duration=min(4.4, max(2.0, dur - 0.3)))
    if ctype == "quake_rumble": return foley_quake_rumble(duration=min(3.8, max(1.8, dur - 0.3)))
    if ctype == "fire_roar": return foley_fire_roar(duration=min(4.5, max(2.0, dur - 0.3)))
    if ctype == "storm_gale": return foley_storm_gale(duration=min(4.5, max(2.0, dur - 0.3)))
    if ctype == "ship_horn": return foley_ship_horn()
    if ctype == "church_bell": return foley_church_bell()
    if ctype == "somber_bell": return fm.foley_somber_bell(duration=2.4)
    if ctype == "jackscrew": return foley_jackscrew_ratchet()
    if ctype == "whistle_blast": return foley_whistle_blast()
    if ctype == "car_honk": return foley_car_honk()
    if ctype == "gavel_slam": return foley_gavel_slam()
    if ctype == "telegraph": return foley_telegraph_beeps()
    if ctype == "water_splash": return foley_water_splash()
    if ctype == "celesta_chime": return fm.foley_celesta_chime(freq=1046.5)
    if ctype == "celesta_chime_hi": return fm.foley_celesta_chime(freq=1318.5)
    if ctype == "stadium_swell": return foley_stadium_swell(duration=min(3.2, max(1.8, dur - 0.4)))
    return None


def render_episode(ep_dir: Path):
    spec = json.load(open(ep_dir / "episode_spec.json", "r", encoding="utf-8"))
    audio_meta = json.load(open(ep_dir / "audio_timings.json", "r", encoding="utf-8"))
    scenes_by_id = {s["id"]: s for s in audio_meta["scenes"]}

    scenes_cfg = []
    for sp in spec["scenes"]:
        m = scenes_by_id[sp["id"]]
        entry = dict(sp)
        entry["start_sec"] = m["start_sec"]
        entry["end_sec"] = m["end_sec"]
        entry["narration"] = m["text"]
        scenes_cfg.append(entry)

    config = {
        "video_settings": {
            "width": W, "height": H, "fps": FPS,
            "subtitle_y_ratio": 0.79, "subtitle_panel_y_ratio": 0.47,
            "version": "v2",
            "voice_provider": audio_meta.get("voice", "Fish Audio S2.1 Pro — Ethan (@Fish Official)"),
        },
        "total_duration_sec": audio_meta["total_duration_sec"],
        "scenes": scenes_cfg,
    }
    with open(ep_dir / "scene_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    slug = spec["slug"]
    voice_wav = ep_dir / f"{slug}.wav"
    if not voice_wav.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(ep_dir / f"{slug}.mp3"), "-ar", str(SR), "-ac", "1", str(voice_wav)], check=True)
    mixed_wav = ep_dir / f"{slug}_mixed.wav"

    with wave.open(str(voice_wav), "rb") as wf:
        voice = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    foley_buf = np.zeros_like(voice)

    for sc in scenes_cfg:
        s0, s1 = sc["start_sec"], sc["end_sec"]
        dur = s1 - s0
        shots = sc.get("shots", [])
        for idx in range(1, len(shots)):
            if abs(shots[idx]["zoom"] - shots[idx - 1].get("end_zoom", shots[idx - 1]["zoom"])) >= 0.45:
                fm.add_sound(foley_buf, s0 + shots[idx]["t"], fm.foley_punch_zoom(), gain=0.34)
        cp = sc.get("comment_panel")
        if cp:
            t_p = s0 + cp["trigger_rel"]
            kw = cp["keyword"]
            for ci in range(len(kw)):
                fm.add_sound(foley_buf, t_p + 0.30 + ci * (0.78 / max(1, len(kw))), fm.foley_type_click(), gain=0.52)
            fm.add_sound(foley_buf, t_p + 1.14, fm.foley_cork_pop(), gain=0.55)
            fm.add_sound(foley_buf, t_p + 0.85, fm.foley_type_click(), gain=0.40)
            fm.add_sound(foley_buf, t_p + 1.40, fm.foley_cork_pop(), gain=0.45)
        if sc.get("loop_return_sec"):
            fm.add_sound(foley_buf, s1 - sc["loop_return_sec"], fm.foley_punch_zoom(0.24), gain=0.40)
        for cue in sc.get("foley", []):
            t_abs = (s1 + cue["rel"]) if cue["rel"] < 0 else (s0 + cue["rel"])
            snd = build_foley_clip(cue["type"], dur)
            if snd is not None:
                fm.add_sound(foley_buf, t_abs, snd, gain=cue.get("gain", 0.65))

    mixed = fm.mix_voice_foley_and_bed(
        voice, foley_buf, audio_meta["words"],
        bpm=spec.get("bed_bpm", 96.0), seed=spec.get("bed_seed", 600),
        voice_gain=0.96, foley_gain=0.56, bed_under_speech=0.15, bed_in_pauses=0.46,
    )
    with wave.open(str(mixed_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(mixed, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes())
    print(f"Mixed audio saved: {mixed_wav.name} ({len(voice)/SR:.2f}s)")

    subtitle_cards = build_subtitle_cards(audio_meta["scenes"])
    highlight_words = set(w.upper() for w in spec.get("highlight_words", []))
    rewind_label = spec.get("rewind_label", "<< REW  TODAY -> PAST")

    print("Extracting sprites & inpainting backgrounds...")
    prepared = []
    for sc in scenes_cfg:
        img = Image.open(ep_dir / sc["keyframe"]).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
        bg = img
        sprs = []
        for sp_cfg in sc.get("sprites", []):
            bg, sp_rgba, rect = extract_sprite_clean(bg, sp_cfg["bbox"], exclude_rects=sp_cfg.get("exclude_rects"))
            sprs.append((sp_rgba, rect, sp_cfg))
        prepared.append({"cfg": sc, "bg_rgba": bg.convert("RGBA"), "sprites": sprs})

    sub_font = load_font(44, bold=True)
    ov_font = load_font(26, bold=True)
    vhs_font = load_font(30, bold=True)
    p_title = load_font(22, bold=True)
    p_in = load_font(24, bold=True)
    p_body = load_font(22, bold=True)
    p_small = load_font(18, bold=True)

    qa_dir = ep_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    s_map = {sc["id"]: sc for sc in scenes_cfg}
    qa_targets = {"scene_01_frame0": 0, "scene_12_panel": int((s_map["scene_12"]["start_sec"] + 2.15) * FPS), "scene_12_loop": int((config["total_duration_sec"] - 0.14) * FPS)}
    for k, qspec in spec.get("qa_points", {}).items():
        sc_q = s_map[qspec["scene"]]
        qa_targets[k] = int((sc_q["start_sec"] + qspec["rel"]) * FPS)

    total_frames = int(math.ceil(config["total_duration_sec"] * FPS))
    out_mp4 = ep_dir / spec["output_mp4"]
    cmd = [
        "ffmpeg", "-y", "-v", "warning",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(mixed_wav),
        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out_mp4),
    ]
    print(f"Rendering {total_frames} frames ({config['total_duration_sec']:.2f}s @ {FPS} FPS) -> {out_mp4.name} ...")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    sub_idx = 0
    frame0_rgba = None

    for f_idx in range(total_frames):
        t = f_idx / FPS
        active = prepared[-1]
        for ps in prepared:
            if ps["cfg"]["start_sec"] <= t < ps["cfg"]["end_sec"]:
                active = ps
                break
        sc = active["cfg"]
        s0, s1 = sc["start_sec"], sc["end_sec"]
        local_t = max(0.0, t - s0)
        dur = max(0.001, s1 - s0)
        prog = min(1.0, local_t / dur)

        canvas = active["bg_rgba"].copy()
        for sp_rgba, rect, sp_cfg in active["sprites"]:
            dx, dy, scale, ang = compute_sprite_transform(sp_cfg["motion"], local_t, sp_cfg)
            eng.paste_moving_sprite(canvas, sp_rgba, rect, dx=dx, dy=dy, scale=scale, angle_deg=ang, shadow=True)

        ov = sc.get("overhead")
        if ov and ov["trigger_rel"] <= local_t < ov.get("end_rel", 999.0):
            draw_overhead_crisp(canvas, ov["cx"], ov["cy"], ov["text"], min(1.0, (local_t - ov["trigger_rel"]) / 0.28), ov_font, style=ov.get("style", "cloud"))

        zoom, pan_x, pan_y, tilt, cut_blur = eng.eval_shot_camera(sc["shots"], local_t, dur)
        if sc.get("quake_shake"):
            pan_x += 0.008 * math.sin(local_t * 42.0)
            pan_y += 0.007 * math.cos(local_t * 36.0)
        if "impact_shake_rel" in sc:
            dt_imp = local_t - sc["impact_shake_rel"]
            if 0.0 <= dt_imp < 0.42:
                dec = math.exp(-dt_imp * 8.5)
                pan_x += 0.013 * math.sin(dt_imp * 55.0) * dec
                pan_y += 0.011 * math.cos(dt_imp * 48.0) * dec

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
            frame = apply_vhs_rewind(frame, vhs_p, vhs_font, rewind_label)

        cp = sc.get("comment_panel")
        panel_active = False
        if cp and local_t >= cp["trigger_rel"]:
            loop_sec = sc.get("loop_return_sec", 0.0)
            if (dur - local_t) > loop_sec * 0.55:
                panel_active = True
                eng.draw_animated_comment_panel(frame, local_t - cp["trigger_rel"], cp["keyword"], cp["comments"], p_title, p_in, p_body, p_small, width=W, height=H)

        loop_sec = sc.get("loop_return_sec", 0.0)
        in_loop = False
        if loop_sec > 0.0 and frame0_rgba is not None and (dur - local_t) <= loop_sec:
            in_loop = True
            lp = smoothstep(1.0 - (dur - local_t) / loop_sec)
            frame = Image.blend(frame, frame0_rgba, lp)
            whip = math.sin(lp * math.pi) * 0.45
            if whip > 0.06:
                ks = max(3, int(whip * 21) | 1)
                arr = np.array(frame)
                ker = np.zeros((ks, ks), dtype=np.float32)
                ker[ks // 2, :] = 1.0 / ks
                arr[:, :, :3] = cv2.filter2D(arr[:, :, :3], -1, ker)
                frame = Image.fromarray(arr)

        while sub_idx < len(subtitle_cards) and subtitle_cards[sub_idx]["end"] < t:
            sub_idx += 1
        if not in_loop and sub_idx < len(subtitle_cards):
            card = subtitle_cards[sub_idx]
            if card["start"] <= t <= card["end"]:
                draw_subtitle_card(frame, card["text"], sub_font, highlight_words, y_ratio=0.47 if panel_active else 0.79)

        for sid, tf in qa_targets.items():
            if f_idx == tf:
                frame.convert("RGB").save(qa_dir / f"qa_{sid}.jpg", quality=92)

        proc.stdin.write(frame.convert("RGB").tobytes())
        if (f_idx + 1) % 300 == 0 or f_idx + 1 == total_frames:
            print(f"  Rendered {f_idx + 1}/{total_frames} frames ({(f_idx + 1)/total_frames*100:.0f}%)")

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    print(f"SUCCESS! Final video saved to: {out_mp4}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python render_episode_v2.py <episode_dir>")
        sys.exit(1)
    render_episode(Path(sys.argv[1]))
