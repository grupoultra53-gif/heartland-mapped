"""
Reusable 30 FPS 2.5D Sprite Extraction, Map Inpainting, Overhead Callout & Camera Engine.
"""
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 720, 1280

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
