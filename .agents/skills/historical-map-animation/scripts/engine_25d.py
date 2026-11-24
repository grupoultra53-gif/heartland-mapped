"""
Reusable 30 FPS 2.5D Sprite Extraction, Map Inpainting, Multi-Shot Camera,
Overhead Callouts, and Animated 1-Word Comment Panel Engine (v2).
"""
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 720, 1280


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def spring_scale(dt, rise=0.32):
    if dt <= 0:
        return 0.0
    if dt >= rise:
        return 1.0
    p = dt / rise
    return 1.0 + 0.18 * math.sin(p * math.pi) if p > 0.55 else (p / 0.55)


def extract_sprite_and_inpaint_bg(pil_img, bbox_norm, width=W, height=H):
    """
    Extracts an independent 2D character/ship/prop sprite from `pil_img` within `bbox_norm`
    (x0, y0, x1, y1 in 0..1) and inpaints the background map behind it using OpenCV Telea.
    """
    rgb = np.array(pil_img)
    x0, y0, x1, y1 = [
        int(bbox_norm[0] * width),
        int(bbox_norm[1] * height),
        int(bbox_norm[2] * width),
        int(bbox_norm[3] * height),
    ]
    patch = rgb[y0:y1, x0:x1].copy()
    ph, pw = patch.shape[:2]

    border_pixels = np.concatenate(
        [
            patch[0:4, :, :].reshape(-1, 3),
            patch[-4:, :, :].reshape(-1, 3),
            patch[:, 0:4, :].reshape(-1, 3),
            patch[:, -4:, :].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.float32)
    bg_med = np.median(border_pixels, axis=0)

    diff = np.linalg.norm(patch.astype(np.float32) - bg_med, axis=2)
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    dark_outline = gray < 65

    raw_mask = ((diff > 26.0) | dark_outline).astype(np.uint8) * 255
    raw_mask[:2, :] = raw_mask[-2:, :] = raw_mask[:, :2] = raw_mask[:, -2:] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    closed = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(closed)
    for cnt in contours:
        if cv2.contourArea(cnt) > 180:
            cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)

    full_mask = np.zeros((height, width), dtype=np.uint8)
    dil_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    full_mask[y0:y1, x0:x1] = cv2.dilate(filled, dil_k, iterations=1)
    inpainted_rgb = cv2.inpaint(rgb, full_mask, 7, cv2.INPAINT_TELEA)

    alpha = cv2.GaussianBlur(filled, (5, 5), 0)
    sprite_rgba = np.dstack([patch, alpha])
    return Image.fromarray(inpainted_rgb), Image.fromarray(sprite_rgba), (x0, y0, pw, ph)


def paste_moving_sprite(canvas_rgba, sprite_pil, base_rect, dx=0.0, dy=0.0, scale=1.0, angle_deg=0.0, shadow=True):
    """Composites an independent moving sprite (with soft drop shadow) onto `canvas_rgba`."""
    if scale <= 0.02:
        return
    x0, y0, pw, ph = base_rect
    nw, nh = max(2, int(pw * scale)), max(2, int(ph * scale))
    sp = sprite_pil.resize((nw, nh), Image.Resampling.BICUBIC)
    if abs(angle_deg) > 0.2:
        sp = sp.rotate(angle_deg, resample=Image.Resampling.BICUBIC, expand=True)

    sw, sh = sp.size
    cx = x0 + pw * 0.5 + dx
    cy = y0 + ph * 0.5 + dy
    px = int(cx - sw * 0.5)
    py = int(cy - sh * 0.5)

    if shadow:
        alpha_ch = sp.split()[3]
        shd = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        shd.putalpha(alpha_ch.point(lambda a: int(a * 0.35)))
        shd = shd.filter(ImageFilter.GaussianBlur(radius=6))
        canvas_rgba.alpha_composite(shd, dest=(px + 6, py + 8))

    canvas_rgba.alpha_composite(sp, dest=(px, py))


def eval_shot_camera(shots: list, local_t: float, dur: float):
    """
    Evaluates multi-shot camera beats inside a single scene (v2).
    Each shot dict:
      {"t": float, "zoom": float, "pan_x": float, "pan_y": float, "tilt_deg": float,
       "end_zoom": optional, "end_pan_x": optional, "end_pan_y": optional, "end_tilt_deg": optional,
       "cut": bool (default True — instant punch-in/cut with brief micro-blur)}
    Returns (zoom, pan_x, pan_y, tilt_deg, cut_blur).
    """
    active_idx = 0
    for idx, sh in enumerate(shots):
        if local_t >= sh["t"]:
            active_idx = idx
        else:
            break

    sh = shots[active_idx]
    t0 = sh["t"]
    t1 = shots[active_idx + 1]["t"] if active_idx + 1 < len(shots) else dur
    span = max(0.05, t1 - t0)
    u = smoothstep((local_t - t0) / span)

    z0 = sh["zoom"]
    px0 = sh.get("pan_x", 0.0)
    py0 = sh.get("pan_y", 0.0)
    tl0 = sh.get("tilt_deg", 0.0)

    z1 = sh.get("end_zoom", z0 * 1.05)
    px1 = sh.get("end_pan_x", px0)
    py1 = sh.get("end_pan_y", py0)
    tl1 = sh.get("end_tilt_deg", tl0)

    cut_blur = 0.0
    if active_idx > 0 and sh.get("cut", True):
        dt_cut = local_t - t0
        if 0.0 <= dt_cut < 0.07:
            cut_blur = (1.0 - dt_cut / 0.07) * 0.38

    return lerp(z0, z1, u), lerp(px0, px1, u), lerp(py0, py1, u), lerp(tl0, tl1, u), cut_blur


def draw_overhead_message(canvas_rgba, cx, cy, text, prog_in, font, style="cloud", width=W, height=H):
    """Draws a compact overhead thought cloud or pill badge above a character's head."""
    if prog_in <= 0.02:
        return
    scale = (prog_in / 0.65 * 1.12) if prog_in < 0.65 else (1.12 - 0.12 * ((prog_in - 0.65) / 0.35))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=3)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y = 16, 10
    bw = int((tw + pad_x * 2) * scale)
    bh = int((th + pad_y * 2) * scale)
    x0 = int(np.clip(cx - bw // 2, 14, width - bw - 14))
    y0 = int(np.clip(cy - bh // 2, 14, height - bh - 14))
    x1, y1 = x0 + bw, y0 + bh

    if style == "cloud":
        draw.ellipse([cx - 6, y1 + 4, cx + 6, y1 + 14], fill=(255, 255, 255, 240), outline=(25, 25, 25, 240), width=2)
        draw.ellipse([cx - 4, y1 + 17, cx + 4, y1 + 24], fill=(255, 255, 255, 230), outline=(25, 25, 25, 230), width=2)

    draw.rounded_rectangle([x0 + 3, y0 + 4, x1 + 3, y1 + 4], radius=16, fill=(0, 0, 0, 105))
    bg_col = (255, 253, 245, 246) if style == "cloud" else (25, 52, 135, 242)
    fg_col = (22, 20, 18, 255) if style == "cloud" else (255, 255, 255, 255)
    border_col = (28, 24, 20, 255) if style == "cloud" else (255, 215, 60, 255)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=bg_col, outline=border_col, width=3)

    if scale > 0.70:
        tx = x0 + (bw - tw) // 2
        ty = y0 + (bh - th) // 2 - 1
        draw.multiline_text((tx, ty), text, font=font, fill=fg_col, align="center", spacing=3)

    canvas_rgba.alpha_composite(layer)


def draw_animated_comment_panel(
    canvas_rgba: Image.Image,
    dt: float,
    keyword: str,
    comments: list,
    font_title,
    font_input,
    font_body,
    font_small,
    width: int = W,
    height: int = H,
):
    """
    Renders a sleek animated social-media comment drawer over the lower half (y ~ 55%..86%)
    in the final ~3.5 seconds of a Short/Reel:
      - Slides up smoothly (0.0..0.32s)
      - Types `keyword` letter-by-letter into the input bar (0.35..1.15s) + SEND pulse
      - Pops in 2 funny in-character historical comments (0.95s & 1.55s)
    """
    if dt <= 0.0:
        return
    slide = smoothstep(min(1.0, dt / 0.32))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    panel_w = width - 56
    panel_h = 375
    x0 = 28
    y_target = int(height * 0.56)
    y0 = int(lerp(height + 20, y_target, slide))
    x1 = x0 + panel_w
    y1 = y0 + panel_h

    # Drop shadow + main rounded card
    draw.rounded_rectangle([x0 + 4, y0 + 8, x1 + 4, y1 + 8], radius=26, fill=(0, 0, 0, 140))
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=26,
        fill=(18, 22, 32, 238),
        outline=(255, 214, 58, 235),
        width=3,
    )

    # Top drag handle + header
    draw.rounded_rectangle([width // 2 - 34, y0 + 12, width // 2 + 34, y0 + 18], radius=3, fill=(130, 140, 160, 190))
    draw.text((x0 + 24, y0 + 28), "COMMENTS", font=font_title, fill=(255, 255, 255, 255))
    draw.text((x1 - 145, y0 + 30), "1.4K replies", font=font_small, fill=(175, 188, 210, 230))
    draw.line([x0 + 18, y0 + 66, x1 - 18, y0 + 66], fill=(55, 65, 85, 200), width=2)

    # Input bar with typing animation
    in_x0, in_y0, in_x1, in_y1 = x0 + 20, y0 + 80, x1 - 20, y0 + 136
    draw.rounded_rectangle([in_x0, in_y0, in_x1, in_y1], radius=24, fill=(32, 39, 54, 250), outline=(95, 112, 145, 220), width=2)

    type_p = max(0.0, min(1.0, (dt - 0.30) / 0.78))
    n_chars = int(math.ceil(type_p * len(keyword)))
    typed = keyword[:n_chars]
    blink = "|" if (dt < 1.25 and int(dt * 8) % 2 == 0) else ""
    prompt_txt = f"{typed}{blink}" if typed else "Type your vote..."
    prompt_col = (255, 224, 72, 255) if typed else (145, 158, 180, 210)
    draw.text((in_x0 + 20, in_y0 + 12), prompt_txt, font=font_input, fill=prompt_col)

    # Send pill button (flashes bright gold when keyword finishes typing)
    sent = dt >= 1.15
    btn_fill = (255, 206, 48, 255) if sent else (45, 92, 210, 245)
    btn_txt_col = (18, 20, 26, 255) if sent else (255, 255, 255, 255)
    bx0, by0, bx1, by1 = in_x1 - 108, in_y0 + 7, in_x1 - 8, in_y1 - 7
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=18, fill=btn_fill)
    draw.text((bx0 + 20, by0 + 8), "POST", font=font_small, fill=btn_txt_col)

    # Animated little white-gloved cartoon pointer hand clicking POST around dt=1.08..1.45
    if 0.85 <= dt <= 1.65:
        hp = smoothstep(min(1.0, (dt - 0.85) / 0.25))
        hx = int(lerp(bx0 + 80, bx0 + 42, hp))
        hy = int(lerp(by1 + 52, by1 - 6, hp))
        if 1.12 <= dt <= 1.26:
            hy += 5  # tap bounce
        draw.ellipse([hx - 15, hy - 14, hx + 15, hy + 14], fill=(255, 255, 255, 255), outline=(20, 20, 20, 255), width=3)
        draw.rounded_rectangle([hx - 5, hy - 28, hx + 6, hy - 6], radius=5, fill=(255, 255, 255, 255), outline=(20, 20, 20, 255), width=3)

    # Pop-in 2 funny historical character comments
    row_y = y0 + 154
    for idx, cmt in enumerate(comments[:2]):
        c_delay = 0.82 + idx * 0.55
        if dt >= c_delay:
            cp = smoothstep(min(1.0, (dt - c_delay) / 0.24))
            ry = int(row_y + (1.0 - cp) * 18)
            av_col = tuple(cmt.get("color", (42, 118, 224))) + (255,)
            # Avatar circle + initial
            draw.ellipse([x0 + 22, ry + 6, x0 + 68, ry + 52], fill=av_col, outline=(255, 255, 255, 230), width=2)
            init = cmt["handle"].lstrip("@")[:1].upper()
            draw.text((x0 + 37, ry + 13), init, font=font_title, fill=(255, 255, 255, 255))
            # Handle + text
            draw.text((x0 + 82, ry + 2), cmt["handle"], font=font_small, fill=(140, 195, 255, 255))
            draw.text((x0 + 82, ry + 29), cmt["text"], font=font_body, fill=(248, 250, 255, 255))
            # Like heart count
            draw.text((x1 - 92, ry + 4), cmt.get("likes", "412 ♥"), font=font_small, fill=(255, 125, 145, 240))
        row_y += 96

    canvas_rgba.alpha_composite(layer)


def apply_25d_camera(canvas_rgba, zoom, pan_x, pan_y, tilt_deg, transition_blur=0.0, width=W, height=H):
    """Applies smooth 2.5D camera zoom, pan, perspective tilt, and whip-pan motion blur."""
    crop_w = width / zoom
    crop_h = height / zoom
    cx = (width * 0.5) + pan_x * width
    cy = (height * 0.5) + pan_y * height

    left = np.clip(cx - crop_w * 0.5, 0, width - crop_w)
    top = np.clip(cy - crop_h * 0.5, 0, height - crop_h)
    cropped = canvas_rgba.crop((left, top, left + crop_w, top + crop_h)).resize((width, height), Image.Resampling.BILINEAR)

    if abs(tilt_deg) > 0.15:
        cropped = cropped.rotate(tilt_deg * 0.35, resample=Image.Resampling.BILINEAR, expand=False)

    if transition_blur > 0.05:
        ksize = max(3, int(transition_blur * 21) | 1)
        arr = np.array(cropped)
        kernel = np.zeros((ksize, ksize), dtype=np.float32)
        kernel[ksize // 2, :] = 1.0 / ksize
        arr[:, :, :3] = cv2.filter2D(arr[:, :, :3], -1, kernel)
        cropped = Image.fromarray(arr)

    return cropped
