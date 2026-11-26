r"""
Heartland Mapped — 16:9 Webdoc Long-Form Modular Renderer (v1)
Implements the complete Heartland Mapped longform specification:
  - 1920x1080 @ 24 FPS (or 640x360 --preview), libx264 + AAC 192 kbps
  - Audio-first single mastered timeline:
      * Per-block loudness normalization + programmed dramatic pauses & chapter-card breathing
      * Multi-mood music tracks with 2.5s crossfades, 1.5s pre-twist silence dips, and voice-activity ducking (-21 dB under speech)
      * Subtle chapter ambience + restrained situational foley (foley_mixer.py)
      * Final 2-pass FFmpeg loudnorm (-14.0 LUFS integrated, <= -1.0 dBTP true peak)
      * Automatic faster-whisper word alignment + clean YouTube .srt (<=2 lines, <=42 chars/line)
  - Parallel per-scene rendering (ProcessPoolExecutor) with SHA256 scene cache + FFmpeg concat -c copy
  - Unified warm archival color grade + subtle film grain + parchment museum mat framing (never scales archive > 145%)
  - Scene types: archive (with optional parallax, focus zoom, highlight circle/bar), map, today,
    oldmap_to_map, then_now, chapter_card, graphic (stat/quote/timeline/list), end_screen
  - Smart TV safe text overlays (>=44px lower-thirds, 72-110px headlines, >=5% side margin, strictly above bottom 12%)

Usage:
  .\.venv\Scripts\python.exe scripts\render_longform.py longform\lf01_midwest_border_fights --audio-only
  .\.venv\Scripts\python.exe scripts\render_longform.py longform\lf01_midwest_border_fights --preview
  .\.venv\Scripts\python.exe scripts\render_longform.py longform\lf01_midwest_border_fights
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = ROOT / ".agents" / "skills" / "historical-map-animation" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import foley_mixer as fm  # noqa: E402

SR = 44100
FPS = 24
BASE_W, BASE_H = 1920, 1080


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def load_font(size: int, style: str = "serif_bold") -> ImageFont.FreeTypeFont:
    table = {
        "serif_bold": [r"C:\Windows\Fonts\georgiab.ttf", r"C:\Windows\Fonts\timesbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"],
        "serif": [r"C:\Windows\Fonts\georgia.ttf", r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\segoeui.ttf"],
        "sans_bold": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\calibrib.ttf"],
        "sans": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
        "impact": [r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\segoeuib.ttf"],
    }
    for p in table.get(style, table["sans_bold"]):
        if os.path.exists(p):
            return ImageFont.truetype(p, max(10, int(size)))
    return ImageFont.load_default()


# ======================== AUDIO PIPELINE ========================

def decode_audio_mono(path: Path, sr: int = SR, tempo: float = 1.0) -> np.ndarray:
    cmd = ["ffmpeg", "-y", "-i", str(path)]
    if abs(tempo - 1.0) > 0.005:
        cmd += ["-af", f"atempo={tempo:.4f}"]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def decode_audio_stereo(path: Path, sr: int = SR) -> np.ndarray:
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-ac", "2", "-ar", str(sr), "-f", "f32le", "pipe:1",
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    arr = np.frombuffer(res.stdout, dtype=np.float32).copy()
    return arr.reshape(-1, 2)


def trim_silence(arr: np.ndarray, threshold: float = 0.008, pad_sec: float = 0.08) -> np.ndarray:
    idx = np.where(np.abs(arr) > threshold)[0]
    if len(idx) == 0:
        return arr
    pad = int(pad_sec * SR)
    s = max(0, int(idx[0]) - pad)
    e = min(len(arr), int(idx[-1]) + pad)
    return arr[s:e]


def normalize_rms(arr: np.ndarray, target_dbfs: float = -18.5) -> np.ndarray:
    active = arr[np.abs(arr) > 0.012]
    rms = float(np.sqrt(np.mean(active ** 2))) if len(active) > 1000 else float(np.sqrt(np.mean(arr ** 2)) + 1e-9)
    target = 10 ** (target_dbfs / 20.0)
    gain = min(4.0, target / max(rms, 1e-6))
    out = arr * gain
    peak = float(np.max(np.abs(out)) + 1e-9)
    if peak > 0.92:
        out = out * (0.92 / peak)
    return out


def write_wav_stereo(path: Path, stereo: np.ndarray, sr: int = SR):
    clipped = np.clip(stereo, -0.99, 0.99)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def write_wav_mono(path: Path, mono: np.ndarray, sr: int = SR):
    clipped = np.clip(mono, -0.99, 0.99)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def loudnorm_two_pass(in_wav: Path, out_wav: Path, target_i: float = -14.0, target_tp: float = -1.0, target_lra: float = 7.0) -> dict:
    # Pass 1: measure
    cmd1 = [
        "ffmpeg", "-y", "-i", str(in_wav),
        "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
        "-f", "null", "-",
    ]
    res1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", res1.stderr, re.DOTALL)
    if not m:
        raise RuntimeError("Could not parse FFmpeg loudnorm pass 1 JSON")
    stats = json.loads(m[-1])
    af2 = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}:print_format=json"
    )
    cmd2 = ["ffmpeg", "-y", "-i", str(in_wav), "-af", af2, "-ar", str(SR), "-ac", "2", str(out_wav)]
    res2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    m2 = re.findall(r"\{[^{}]*\"output_i\"[^{}]*\}", res2.stderr, re.DOTALL)
    return json.loads(m2[-1]) if m2 else stats


def loop_track_stereo(track: np.ndarray, total_samples: int, xfade_sec: float = 3.0) -> np.ndarray:
    if len(track) >= total_samples:
        return track[:total_samples].copy()
    xf = min(int(xfade_sec * SR), len(track) // 4)
    out = np.zeros((total_samples, 2), dtype=np.float32)
    pos = 0
    first = True
    while pos < total_samples:
        chunk = track.copy()
        rem = total_samples - pos
        take = min(len(chunk), rem)
        if first:
            out[pos : pos + take] = chunk[:take]
            first = False
            pos += take - xf
        else:
            ov = min(xf, take, total_samples - pos)
            if ov > 0:
                fade_in = np.linspace(0.0, 1.0, ov, dtype=np.float32)[:, None]
                fade_out = 1.0 - fade_in
                out[pos : pos + ov] = out[pos : pos + ov] * fade_out + chunk[:ov] * fade_in
            if take > ov:
                out[pos + ov : pos + take] = chunk[ov:take]
            pos += take - xf
        if take < len(chunk):
            break
    return out


def format_srt_ts(sec: float) -> str:
    sec = max(0.0, sec)
    ms = int(round((sec - int(sec)) * 1000))
    total = int(sec)
    if ms >= 1000:
        total += 1
        ms -= 1000
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_clean_srt(words: list[dict], srt_path: Path, replacements: dict[str, str] | None = None):
    """Build YouTube-ready .srt: <=2 lines, <=42 chars/line, 1.0-6.0s per cue."""
    repl = replacements or {}

    def clean_word(w: str) -> str:
        out = w.strip()
        for src, dst in repl.items():
            out = re.sub(re.escape(src), dst, out, flags=re.IGNORECASE)
        return out

    cues = []
    buf = []
    start_t = None

    def flush():
        nonlocal buf, start_t
        if not buf:
            return
        text = " ".join(x["text"] for x in buf)
        text = re.sub(r"\s+([,.;:?!])", r"\1", text)
        for src, dst in repl.items():
            text = re.sub(re.escape(src), dst, text, flags=re.IGNORECASE)
        end_t = buf[-1]["end"]
        if end_t - start_t < 1.0:
            end_t = start_t + 1.0
        # Wrap into max 2 lines <= 42 chars
        if len(text) <= 42:
            lines = [text]
        else:
            mid = len(text) // 2
            split_idx = text.rfind(" ", 0, min(len(text), 43))
            # Try balanced split near mid
            best = None
            for i, ch in enumerate(text):
                if ch == " " and i <= 42 and (len(text) - i - 1) <= 42:
                    if best is None or abs(i - mid) < abs(best - mid):
                        best = i
            idx = best if best is not None else (split_idx if split_idx > 0 else 42)
            lines = [text[:idx].strip(), text[idx:].strip()[:42]]
        cues.append((start_t, end_t, "\n".join(lines)))
        buf = []
        start_t = None

    for item in words:
        w = clean_word(item["word"])
        if not w:
            continue
        if start_t is None:
            start_t = item["start"]
        gap = (item["start"] - buf[-1]["end"]) if buf else 0.0
        cand_len = sum(len(x["text"]) + 1 for x in buf) + len(w)
        dur = item["end"] - start_t
        if buf and (gap > 0.65 or cand_len > 78 or dur > 5.4):
            flush()
            start_t = item["start"]
        buf.append({"text": w, "start": item["start"], "end": item["end"]})
        if w.endswith((".", "?", "!")) and (item["end"] - start_t) >= 1.5 and cand_len >= 28:
            flush()
    flush()

    # Ensure zero overlaps and cap duration <= 6.0s
    lines_out = []
    for i, (st, et, txt) in enumerate(cues):
        if et - st > 6.0:
            et = st + 6.0
        if i + 1 < len(cues) and et > cues[i + 1][0] - 0.04:
            et = max(st + 0.8, cues[i + 1][0] - 0.04)
        lines_out.append(f"{i + 1}\n{format_srt_ts(st)} --> {format_srt_ts(et)}\n{txt}\n")
    srt_path.write_text("\n".join(lines_out), encoding="utf-8")
    return len(cues)


def assemble_and_master_audio(ep_dir: Path, script_data: dict, music_map: dict[str, Path], foley_cues: list[dict] | None = None, silence_dips: list[tuple[float, float]] | None = None):
    """
    1. Assemble normalized Ethan narration blocks with programmed pauses & chapter-card lead/tail.
    2. Run faster-whisper to produce exact word-level audio_timings.json + legendas.srt.
    3. Mix multi-mood music (-21 dB under voice, 2.5s chapter crossfades, 1.5s pre-twist dips),
       subtle chapter ambience (-35 dB), and restrained situational foley (>=8 dB below voice).
    4. Run 2-pass FFmpeg loudnorm (-14.0 LUFS, <= -1.0 dBTP) -> audio/master_audio.wav.
    """
    audio_dir = ep_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    blocks = script_data["blocks"]

    voice_parts = []
    block_timeline = []
    cursor = 0.45  # Voice starts cleanly at 0.45s (<= 1.0s audit rule!)
    voice_parts.append(np.zeros(int(cursor * SR), dtype=np.float32))

    voice_tempo = float(script_data.get("voice_tempo", 1.14))
    for blk in blocks:
        bid = blk["id"]
        src_mp3 = audio_dir / f"{bid}.mp3"
        if not src_mp3.exists():
            raise FileNotFoundError(f"Missing Fish Audio narration block: {src_mp3}")
        # If block opens a chapter card, reserve clean breathing room before speech!
        card_start = None
        card_end = None
        if blk.get("chapter_card"):
            card_dur = float(blk.get("chapter_card_dur", 2.35))
            card_start = cursor
            card_end = cursor + card_dur
            voice_parts.append(np.zeros(int(card_dur * SR), dtype=np.float32))
            cursor = card_end

        blk_tempo = float(blk.get("voice_tempo", voice_tempo))
        raw = trim_silence(decode_audio_mono(src_mp3, SR, tempo=blk_tempo), threshold=0.008, pad_sec=0.05)
        norm = normalize_rms(raw, target_dbfs=-18.5)
        b_start = cursor
        b_end = b_start + len(norm) / SR
        voice_parts.append(norm)
        cursor = b_end

        pause_after = min(0.75, float(blk.get("pause_after_sec", 0.65)))
        if pause_after > 0:
            voice_parts.append(np.zeros(int(pause_after * SR), dtype=np.float32))
            cursor += pause_after

        block_timeline.append({
            "id": bid,
            "chapter": blk.get("chapter", ""),
            "chapter_card": blk.get("chapter_card"),
            "chapter_card_start": round(card_start, 3) if card_start is not None else None,
            "chapter_card_end": round(card_end, 3) if card_end is not None else None,
            "speech_start": round(b_start, 3),
            "speech_end": round(b_end, 3),
            "block_end": round(cursor, 3),
            "mood": blk.get("mood", "curiosity"),
        })

    # Gentle 4.0s closing musical tail after Ethan finishes (end screen spans final 20s covering outro + tail!)
    tail_sec = 4.0
    voice_parts.append(np.zeros(int(tail_sec * SR), dtype=np.float32))
    total_dur = cursor + tail_sec

    voice_mono = np.concatenate(voice_parts)
    total_samples = len(voice_mono)
    voice_wav = audio_dir / "voice_assembled.wav"
    write_wav_mono(voice_wav, voice_mono, SR)

    # Align words using faster-whisper only if not already cached (preserves polished legendas.srt!)
    timings_path = ep_dir / "audio_timings.json"
    if not timings_path.exists() or not (ep_dir / "legendas.srt").exists():
        from faster_whisper import WhisperModel
        from scipy.signal import resample_poly
        print(f"Running faster-whisper alignment on {total_dur:.2f}s assembled narration...")
        voice_16k = resample_poly(voice_mono, 160, 441).astype(np.float32)
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(voice_16k, word_timestamps=True, language="en")
        words = []
        for seg in segments:
            for w in seg.words or []:
                words.append({"word": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3)})

        srt_repl = {v: k for k, v in script_data.get("pronunciation_notes", {}).items()}
        srt_repl.update({
            "Duh Moyn": "Des Moines", "Du Moyn": "Des Moines", "De Moyn": "Des Moines", "Duh Moin": "Des Moines",
            "KEE-oh-kuk": "Keokuk", "Kee-oh-kuk": "Keokuk", "Kee-oh-SAW-kwah": "Keosauqua",
            "New MAD-rid": "New Madrid", "New Mad-rid": "New Madrid",
            "Maw-mee": "Maumee", "Mawmee": "Maumee",
            "Man-ih-TOE-bah": "Manitoba", "Manitobah": "Manitoba",
            "PESH-tih-go": "Peshtigo", "Mackinaw": "Mackinac",
        })
        cue_count = build_clean_srt(words, ep_dir / "legendas.srt", srt_repl)
        print(f"Generated legendas.srt ({cue_count} cues) and {len(words)} aligned words.")
        timings_payload = {"duration": round(total_dur, 3), "blocks": block_timeline, "words": words}
        timings_path.write_text(json.dumps(timings_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        timings_payload = json.loads(timings_path.read_text(encoding="utf-8"))
        print(f"Using cached whisper alignment ({len(timings_payload.get('words', []))} words, {total_dur:.2f}s).")

    # Build multi-mood stereo music bed
    loaded_tracks = {}
    for mood, path in music_map.items():
        if path.exists():
            st = decode_audio_stereo(path, SR)
            # Normalize track RMS to -18 dBFS so ducking math is exact
            rms = float(np.sqrt(np.mean(st ** 2)) + 1e-9)
            st = st * (10 ** (-18.0 / 20.0) / rms)
            loaded_tracks[mood] = loop_track_stereo(st, total_samples, xfade_sec=3.0)

    music_stereo = np.zeros((total_samples, 2), dtype=np.float32)
    xf_s = int(2.5 * SR)
    for i, bt in enumerate(block_timeline):
        mood = bt["mood"] if bt["mood"] in loaded_tracks else next(iter(loaded_tracks.keys()))
        seg_s = int((bt["chapter_card_start"] if bt["chapter_card_start"] is not None else bt["speech_start"]) * SR)
        seg_e = total_samples if i == len(block_timeline) - 1 else int((block_timeline[i + 1]["chapter_card_start"] if block_timeline[i + 1]["chapter_card_start"] is not None else block_timeline[i + 1]["speech_start"]) * SR)
        if i == 0:
            seg_s = 0
        seg_s = max(0, min(total_samples, seg_s))
        seg_e = max(seg_s, min(total_samples, seg_e))
        if i == 0:
            music_stereo[seg_s:seg_e] = loaded_tracks[mood][seg_s:seg_e]
        else:
            ov_s = max(0, seg_s - xf_s // 2)
            ov_e = min(total_samples, seg_s + xf_s // 2)
            ov_len = ov_e - ov_s
            if ov_len > 0:
                fi = np.linspace(0.0, 1.0, ov_len, dtype=np.float32)[:, None]
                music_stereo[ov_s:ov_e] = music_stereo[ov_s:ov_e] * (1.0 - fi) + loaded_tracks[mood][ov_s:ov_e] * fi
            if seg_e > ov_e:
                music_stereo[ov_e:seg_e] = loaded_tracks[mood][ov_e:seg_e]

    # Voice-activity ducking envelope: music stays -21.5 dB below voice during speech (passes >= 18 dB rule!)
    # and lifts gently to -13 dB on chapter cards & final tail
    win = int(0.18 * SR)
    abs_v = np.abs(voice_mono)
    # Fast smoothed speech activity detector via decimated convolution
    step = 220
    dec = abs_v[::step]
    kern = np.ones(max(3, win // step), dtype=np.float32)
    kern /= kern.sum()
    env_dec = np.convolve(dec, kern, mode="same")
    speech_mask_dec = np.clip((env_dec - 0.008) / 0.025, 0.0, 1.0)
    # Smooth release/attack over ~0.45s
    sm_k = np.ones(max(3, int(0.45 * SR / step)), dtype=np.float32)
    sm_k /= sm_k.sum()
    speech_smooth_dec = np.convolve(speech_mask_dec, sm_k, mode="same")
    speech_env = np.interp(np.arange(total_samples), np.arange(len(speech_smooth_dec)) * step, speech_smooth_dec).astype(np.float32)

    # -21.5 dB under speech (~0.084), -12.5 dB in chapter cards/pauses (~0.237)
    gain_speech = 10 ** (-21.8 / 20.0)
    gain_pause = 10 ** (-13.0 / 20.0)
    duck_gain = gain_pause * (1.0 - speech_env) + gain_speech * speech_env

    # Apply dramatic 1.5s music silence dips right before big plot twists
    for d_start, d_end in (silence_dips or []):
        s0 = max(0, int(d_start * SR))
        s1 = min(total_samples, int(d_end * SR))
        ramp = int(0.28 * SR)
        if s1 > s0 + 2 * ramp:
            duck_gain[s0 : s0 + ramp] *= np.linspace(1.0, 0.04, ramp, dtype=np.float32)
            duck_gain[s0 + ramp : s1 - ramp] *= 0.04
            duck_gain[s1 - ramp : s1] *= np.linspace(0.04, 1.0, ramp, dtype=np.float32)

    # Gentle fade-in (0.4s) & fade-out (2.5s)
    fi_n = int(0.4 * SR)
    fo_n = int(2.5 * SR)
    duck_gain[:fi_n] *= np.linspace(0.0, 1.0, fi_n, dtype=np.float32)
    duck_gain[-fo_n:] *= np.linspace(1.0, 0.0, fo_n, dtype=np.float32)

    music_ducked = music_stereo * duck_gain[:, None]
    # Save music-only track for audit_longform.py exact voice-vs-music separation check!
    write_wav_stereo(audio_dir / "music_ducked.wav", music_ducked, SR)

    # Subtle continuous plains wind ambience (-35 dB so TV never sounds dead)
    amb_path = ROOT / "assets" / "music" / "ambience_plains_wind.mp3"
    amb_stereo = np.zeros((total_samples, 2), dtype=np.float32)
    if amb_path.exists():
        amb_raw = decode_audio_stereo(amb_path, SR)
        amb_rms = float(np.sqrt(np.mean(amb_raw ** 2)) + 1e-9)
        amb_norm = amb_raw * (10 ** (-36.0 / 20.0) / amb_rms)
        amb_stereo = loop_track_stereo(amb_norm, total_samples, xfade_sec=3.0)
        amb_stereo[-fo_n:] *= np.linspace(1.0, 0.0, fo_n, dtype=np.float32)[:, None]

    # Restrained self-contained situational foley (1 cue every ~25-30s, strictly >= 8 dB below voice)
    foley_mono = np.zeros(total_samples, dtype=np.float32)

    def _gen_foley(kind: str) -> np.ndarray:
        rng = np.random.default_rng(1871)
        if kind == "parchment":
            n = int(0.65 * SR); t = np.linspace(0, 0.65, n)
            return fm.bandpass(rng.normal(0, 1, n), 900, 3800) * np.sin(np.pi * t / 0.65) ** 1.4
        if kind == "whoosh":
            n = int(0.42 * SR); t = np.linspace(0, 0.42, n)
            return fm.bandpass(rng.normal(0, 1, n), 240, 1400) * np.sin(np.pi * t / 0.42) ** 1.8
        if kind == "bell":
            n = int(2.4 * SR); t = np.linspace(0, 2.4, n)
            return (np.sin(2 * np.pi * 392 * t) * 0.6 + np.sin(2 * np.pi * 784 * t) * 0.3 * np.exp(-t * 2.0)) * np.exp(-t * 1.5)
        if kind == "chime":
            n = int(1.1 * SR); t = np.linspace(0, 1.1, n)
            return (np.sin(2 * np.pi * 880 * t) * 0.5 + np.sin(2 * np.pi * 1320 * t) * 0.35) * np.exp(-t * 3.8)
        if kind == "river":
            n = int(2.6 * SR); t = np.linspace(0, 2.6, n)
            return (fm.bandpass(rng.normal(0, 1, n), 180, 1200) * 0.6 + fm.lowpass(rng.normal(0, 1, n), 180) * 0.4) * np.sin(np.pi * t / 2.6) ** 0.8
        if kind == "crack":
            n = int(1.1 * SR); t = np.linspace(0, 1.1, n)
            return fm.bandpass(rng.normal(0, 1, n), 450, 2600) * np.exp(-t * 5.2)
        if kind == "war_horn":
            n = int(1.9 * SR); t = np.linspace(0, 1.9, n)
            return (np.sin(2 * np.pi * 146.8 * t) * 0.6 + np.sin(2 * np.pi * 293.7 * t) * 0.35) * np.sin(np.pi * t / 1.9) ** 0.9
        if kind == "march":
            n = int(2.2 * SR); out = np.zeros(n)
            for k in range(4):
                p0 = int(k * 0.52 * SR); ln = int(0.16 * SR); tt = np.linspace(0, 0.16, ln)
                if p0 + ln < n:
                    out[p0:p0 + ln] += fm.lowpass(rng.normal(0, 1, ln), 240) * np.exp(-tt * 18.0)
            return out
        if kind == "fire":
            n = int(3.0 * SR); t = np.linspace(0, 3.0, n)
            roar = fm.bandpass(rng.normal(0, 1, n), 140, 950) * 0.65
            crackle = np.zeros(n)
            for _ in range(36):
                pos = int(rng.integers(0, n - 350))
                crackle[pos:pos + 300] += fm.bandpass(rng.normal(0, 1, 300), 2200, 6200) * np.exp(-np.linspace(0, 8, 300)) * 0.5
            return (roar + crackle) * np.sin(np.pi * t / 3.0) ** 0.75
        return np.zeros(int(0.5 * SR))

    for fc in (foley_cues or []):
        snd = _gen_foley(fc.get("type", "parchment")).astype(np.float32)
        pk = float(np.max(np.abs(snd)) + 1e-9)
        snd = snd * (0.13 * float(fc.get("gain", 0.65)) / pk)
        fm.add_sound(foley_mono, float(fc["t"]), snd, gain=1.0)

    # Combine stereo mix
    voice_stereo = np.stack([voice_mono, voice_mono], axis=1)
    foley_stereo = np.stack([foley_mono, foley_mono], axis=1)
    pre_master = voice_stereo + music_ducked + amb_stereo + foley_stereo

    pre_wav = audio_dir / "pre_master.wav"
    master_wav = audio_dir / "master_audio.wav"
    write_wav_stereo(pre_wav, pre_master, SR)

    print("Running 2-pass FFmpeg loudnorm (-14.0 LUFS / -2.4 dBTP pre-AAC headroom)...")
    ln_stats = loudnorm_two_pass(pre_wav, master_wav, target_i=-14.0, target_tp=-2.4, target_lra=7.0)
    print(f"Mastered audio ready: {master_wav} (I={ln_stats.get('output_i')} LUFS, TP={ln_stats.get('output_tp')} dBTP)")
    (audio_dir / "loudnorm_stats.json").write_text(json.dumps(ln_stats, indent=2), encoding="utf-8")
    return timings_payload


# ======================== VISUAL ENGINE ========================

def unified_archive_grade(rgb: np.ndarray, strength: float = 0.75) -> np.ndarray:
    """Apply subtle unified warm PBS-documentary tone + fine archival grain."""
    img = rgb.astype(np.float32)
    # Warm sepia-amber balance (slightly lift R, gentle G, subtly soften harsh blue)
    warm = img.copy()
    warm[:, :, 0] = np.clip(img[:, :, 0] * 1.04 + 5.0, 0, 255)
    warm[:, :, 1] = np.clip(img[:, :, 1] * 1.01 + 2.0, 0, 255)
    warm[:, :, 2] = np.clip(img[:, :, 2] * 0.93 - 2.0, 0, 255)
    # Gentle S-curve contrast without crushing shadows
    warm = np.clip((warm - 128.0) * 1.05 + 128.0, 0, 255)
    out = img * (1.0 - strength) + warm * strength
    # Soft corner vignette
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rx = (xx - w * 0.5) / (w * 0.55)
    ry = (yy - h * 0.5) / (h * 0.55)
    vig = np.clip(1.0 - 0.16 * (rx * rx + ry * ry), 0.78, 1.0)
    out *= vig[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def add_subtle_grain(rgb: np.ndarray, seed: int, amount: float = 4.2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    h, w = rgb.shape[:2]
    # Fast half-res grain upscaled for organic film texture
    noise = rng.normal(0.0, amount, (h // 2, w // 2, 1)).astype(np.float32)
    noise = cv2.resize(noise, (w, h), interpolation=cv2.INTER_LINEAR)[:, :, None]
    return np.clip(rgb.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def compose_archival_plate(img_rgb: np.ndarray, bg_rgb: np.ndarray, out_w: int, out_h: int, frame_style: str = "photo", max_scale: float = 1.42) -> tuple[np.ndarray, float]:
    """
    Prepares an archival photo/document on 16:9 canvas:
      - If wide high-res landscape (>= 1280px wide and aspect >= 1.35) and frame_style == 'fullbleed': fills 16:9 cleanly without exceeding max_scale.
      - Otherwise mounts inside an authentic vintage museum photo/newspaper/document frame over parchment backdrop so small or portrait scans are NEVER over-stretched past 145%!
    Returns (prepared_rgb_16x9, effective_scale_factor).
    """
    ih, iw = img_rgb.shape[:2]
    graded = unified_archive_grade(img_rgb, strength=0.80)

    if frame_style == "fullbleed" and iw >= int(out_w / max_scale) and (iw / float(ih)) >= 1.35:
        scale = max(out_w / float(iw), out_h / float(ih))
        if scale <= max_scale:
            nw, nh = int(round(iw * scale)), int(round(ih * scale))
            res = cv2.resize(graded, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)
            x0 = (nw - out_w) // 2
            y0 = (nh - out_h) // 2
            return res[y0 : y0 + out_h, x0 : x0 + out_w], scale

    # Framed archival plate over warm parchment studio backdrop (guaranteed <= max_scale!)
    canvas = Image.fromarray(cv2.resize(bg_rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)).convert("RGBA")
    pad_x = int(out_w * 0.08)
    pad_top = int(out_h * 0.07)
    pad_bot = int(out_h * 0.14)  # Leave room above bottom 12% safe area!
    avail_w = out_w - 2 * pad_x
    avail_h = out_h - pad_top - pad_bot

    fit_scale = min(avail_w / float(iw), avail_h / float(ih), max_scale)
    nw, nh = max(64, int(round(iw * fit_scale))), max(64, int(round(ih * fit_scale)))
    pic = Image.fromarray(cv2.resize(graded, (nw, nh), interpolation=cv2.INTER_AREA if fit_scale < 1.0 else cv2.INTER_CUBIC)).convert("RGBA")

    border = max(8, int(out_h * (0.022 if frame_style == "photo" else 0.016)))
    mat_col = (246, 238, 220, 255) if frame_style != "newspaper" else (238, 229, 206, 255)
    frame_w, frame_h = nw + 2 * border, nh + 2 * border

    # Drop shadow
    shd = Image.new("RGBA", (frame_w + 36, frame_h + 36), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shd)
    sd.rounded_rectangle([18, 22, frame_w + 18, frame_h + 22], radius=4, fill=(32, 22, 12, 115))
    shd = shd.filter(ImageFilter.GaussianBlur(14))

    plate = Image.new("RGBA", (frame_w, frame_h), mat_col)
    pd = ImageDraw.Draw(plate)
    pd.rectangle([0, 0, frame_w - 1, frame_h - 1], outline=(78, 60, 42, 220), width=max(2, out_h // 450))
    pd.rectangle([border - 2, border - 2, border + nw + 1, border + nh + 1], outline=(110, 90, 66, 180), width=1)
    plate.paste(pic, (border, border))

    # Slight organic documentary tilt (-1.1 to +1.1 deg) for newspaper/photo authenticity
    tilt = 0.0 if frame_style == "document" else (-0.8 if (iw + ih) % 2 == 0 else 0.7)
    if abs(tilt) > 0.05:
        shd = shd.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)
        plate = plate.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)

    cx = out_w // 2
    cy = pad_top + avail_h // 2
    canvas.alpha_composite(shd, (cx - shd.width // 2, cy - shd.height // 2))
    canvas.alpha_composite(plate, (cx - plate.width // 2, cy - plate.height // 2))
    return np.array(canvas.convert("RGB")), fit_scale


def warp_camera(img_rgb: np.ndarray, zoom: float, pan_x: float, pan_y: float, out_w: int, out_h: int) -> np.ndarray:
    """Fast OpenCV C++ camera transform (pan_x/pan_y in normalized -0.5..+0.5)."""
    h, w = img_rgb.shape[:2]
    cx = w * (0.5 + pan_x)
    cy = h * (0.5 + pan_y)
    # Clamp viewport so black borders NEVER appear
    half_w = (w / zoom) * 0.5
    half_h = (h / zoom) * 0.5
    cx = max(half_w, min(w - half_w, cx))
    cy = max(half_h, min(h - half_h, cy))

    scale_x = (out_w * zoom) / float(w)
    scale_y = (out_h * zoom) / float(h)
    tx = out_w * 0.5 - cx * scale_x
    ty = out_h * 0.5 - cy * scale_y
    M = np.array([[scale_x, 0.0, tx], [0.0, scale_y, ty]], dtype=np.float32)
    return cv2.warpAffine(img_rgb, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def build_parallax_layers(plate_rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extracts central subject softly and inpaints background behind it via OpenCV Telea for 2.5D depth drift."""
    h, w = plate_rgb.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    # Soft central oval region for portrait/focal foreground drift
    cv2.ellipse(mask, (w // 2, int(h * 0.46)), (int(w * 0.24), int(h * 0.34)), 0, 0, 360, 255, -1)
    # Feather alpha smoothly
    alpha = cv2.GaussianBlur(mask, (0, 0), sigmaX=w * 0.045, sigmaY=h * 0.045)
    bg_inpaint = cv2.inpaint(plate_rgb, (mask > 180).astype(np.uint8) * 255, 7, cv2.INPAINT_TELEA)
    fg_rgba = np.dstack([plate_rgb, alpha])
    return bg_inpaint, fg_rgba


def draw_smart_tv_overlays(frame_rgb: np.ndarray, overlays: list[dict], local_t: float, scene_dur: float, out_w: int, out_h: int) -> np.ndarray:
    """
    Renders crisp Smart-TV safe editorial overlays (>=44px lower-thirds, 72-110px big stats/quotes,
    solid cream ink-bordered plates, 5% horizontal margins, strictly ABOVE the bottom 12% TV bar!).
    """
    if not overlays:
        return frame_rgb
    scale = out_h / float(BASE_H)
    active = [ov for ov in overlays if float(ov.get("start", 0.0)) <= local_t <= float(ov.get("end", scene_dur))]
    if not active:
        return frame_rgb

    img = Image.fromarray(frame_rgb).convert("RGBA")
    layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    safe_x = int(out_w * 0.055)
    safe_bottom = int(out_h * 0.865)  # Strictly above bottom 12% (88% = 950px)!

    for ov in active:
        t0 = float(ov.get("start", 0.0))
        t1 = float(ov.get("end", scene_dur))
        fade_in = min(1.0, (local_t - t0) / 0.35)
        fade_out = min(1.0, (t1 - local_t) / 0.35)
        alpha = max(0.0, min(1.0, ease_in_out(min(fade_in, fade_out))))
        a255 = int(round(255 * alpha))
        otype = ov.get("type", "rodape")

        if otype == "rodape":
            # Lower-third solid cream plate with crimson accent bar, strictly above bottom 12%
            title = ov.get("title", "")
            sub = ov.get("subtitle", "")
            f_title = load_font(int(48 * scale), "serif_bold")
            f_sub = load_font(int(40 * scale), "sans")
            tb = draw.textbbox((0, 0), title, font=f_title)
            sb = draw.textbbox((0, 0), sub, font=f_sub) if sub else (0, 0, 0, 0)
            bw = min(out_w - 2 * safe_x, max(tb[2] - tb[0], sb[2] - sb[0]) + int(68 * scale))
            bh = (tb[3] - tb[1]) + ((sb[3] - sb[1] + int(14 * scale)) if sub else 0) + int(34 * scale)
            bx = safe_x
            by = safe_bottom - bh
            # Slide gently in from left
            slide_dx = int((1.0 - ease_out_cubic(fade_in)) * -32 * scale)
            bx += slide_dx
            draw.rounded_rectangle([bx + 4, by + 6, bx + bw + 4, by + bh + 6], radius=int(8 * scale), fill=(24, 18, 12, int(115 * alpha)))
            draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(8 * scale), fill=(246, 238, 219, int(244 * alpha)), outline=(56, 40, 26, a255), width=max(2, int(3 * scale)))
            # Crimson left stripe
            draw.rectangle([bx, by + int(6 * scale), bx + int(12 * scale), by + bh - int(6 * scale)], fill=(166, 36, 32, a255))
            tx = bx + int(30 * scale)
            ty = by + int(14 * scale)
            draw.text((tx, ty), title, font=f_title, fill=(32, 22, 14, a255))
            if sub:
                draw.text((tx, ty + (tb[3] - tb[1]) + int(10 * scale)), sub, font=f_sub, fill=(84, 62, 42, a255))

        elif otype == "stat":
            # Big dramatic number/date + label plate (top-right or top-left)
            big = ov.get("big", "")
            label = ov.get("label", "")
            pos = ov.get("pos", "top_left")
            f_big = load_font(int(88 * scale), "serif_bold")
            f_lbl = load_font(int(44 * scale), "sans_bold")
            bb = draw.textbbox((0, 0), big, font=f_big)
            lb = draw.textbbox((0, 0), label, font=f_lbl) if label else (0, 0, 0, 0)
            bw = max(bb[2] - bb[0], lb[2] - lb[0]) + int(64 * scale)
            bh = (bb[3] - bb[1]) + ((lb[3] - lb[1] + int(14 * scale)) if label else 0) + int(42 * scale)
            bx = safe_x if "left" in pos else (out_w - safe_x - bw)
            by = int(out_h * 0.085) if "top" in pos else (safe_bottom - bh)
            draw.rounded_rectangle([bx + 5, by + 7, bx + bw + 5, by + bh + 7], radius=int(10 * scale), fill=(22, 16, 10, int(120 * alpha)))
            draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(10 * scale), fill=(246, 238, 219, int(245 * alpha)), outline=(58, 42, 26, a255), width=max(2, int(3 * scale)))
            draw.rectangle([bx, by, bx + bw, by + int(9 * scale)], fill=(166, 36, 32, a255))
            draw.text((bx + int(32 * scale), by + int(18 * scale)), big, font=f_big, fill=(148, 28, 24, a255))
            if label:
                draw.text((bx + int(32 * scale), by + int(28 * scale) + (bb[3] - bb[1])), label, font=f_lbl, fill=(38, 26, 16, a255))

        elif otype == "destaque":
            # Centered high-contrast documentary quote / key takeaway banner
            lines = ov.get("lines", [ov.get("text", "")])
            f_q = load_font(int(62 * scale), "serif_bold")
            sub = ov.get("attribution", "")
            f_a = load_font(int(40 * scale), "sans")
            widths = [draw.textbbox((0, 0), ln, font=f_q)[2] for ln in lines]
            line_h = int(76 * scale)
            bw = min(out_w - 2 * safe_x, max(widths + [int(400 * scale)]) + int(96 * scale))
            bh = len(lines) * line_h + (int(52 * scale) if sub else 0) + int(56 * scale)
            bx = (out_w - bw) // 2
            by = int(out_h * 0.36) if ov.get("pos") != "bottom" else (safe_bottom - bh)
            draw.rounded_rectangle([bx + 6, by + 8, bx + bw + 6, by + bh + 8], radius=int(12 * scale), fill=(18, 12, 8, int(145 * alpha)))
            draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(12 * scale), fill=(246, 238, 219, int(246 * alpha)), outline=(56, 40, 26, a255), width=max(3, int(4 * scale)))
            cy = by + int(28 * scale)
            for ln in lines:
                lw = draw.textbbox((0, 0), ln, font=f_q)[2]
                draw.text(((out_w - lw) // 2, cy), ln, font=f_q, fill=(30, 20, 12, a255))
                cy += line_h
            if sub:
                sw = draw.textbbox((0, 0), sub, font=f_a)[2]
                draw.text(((out_w - sw) // 2, cy + int(6 * scale)), sub, font=f_a, fill=(134, 38, 32, a255))

        elif otype == "highlight_ring":
            # Animated crimson/gold target circle over a focus point on map or newspaper
            rx = int(ov["cx"] * out_w)
            ry = int(ov["cy"] * out_h)
            rad = int(ov.get("radius", 0.09) * out_h)
            prog = min(1.0, (local_t - t0) / 0.55)
            end_ang = -90 + int(360 * ease_out_cubic(prog))
            col = (196, 36, 28, a255) if ov.get("color", "red") == "red" else (218, 158, 24, a255)
            draw.arc([rx - rad, ry - rad, rx + rad, ry + rad], start=-90, end=end_ang, fill=col, width=max(4, int(8 * scale)))

        elif otype == "credit":
            # Subtle source credit in top-right corner (never competing with bottom 12%)
            txt = ov.get("text", "")
            f_c = load_font(int(28 * scale), "sans")
            cb = draw.textbbox((0, 0), txt, font=f_c)
            cw = cb[2] - cb[0] + int(24 * scale)
            ch = cb[3] - cb[1] + int(14 * scale)
            cx = out_w - safe_x - cw
            cy = int(out_h * 0.032)
            draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=int(5 * scale), fill=(26, 20, 14, int(165 * alpha)))
            draw.text((cx + int(12 * scale), cy + int(6 * scale)), txt, font=f_c, fill=(240, 232, 214, a255))

    img.alpha_composite(layer)
    return np.array(img.convert("RGB"))


def render_chapter_card_frame(bg_rgb: np.ndarray, card: dict, local_t: float, dur: float, out_w: int, out_h: int) -> np.ndarray:
    scale = out_h / float(BASE_H)
    base = cv2.resize(bg_rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)
    # Slow subtle zoom on parchment
    z = 1.0 + 0.04 * ease_in_out(local_t / max(0.1, dur))
    base = warp_camera(base, z, 0.0, 0.0, out_w, out_h)

    img = Image.fromarray(base).convert("RGBA")
    ov = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    fade = min(ease_out_cubic(local_t / 0.45), ease_out_cubic((dur - local_t) / 0.40))
    a255 = int(round(255 * max(0.0, min(1.0, fade))))

    # Ornamental double ink border inside 6% safe margin
    m = int(out_w * 0.065)
    m2 = m + int(10 * scale)
    d.rectangle([m, int(out_h * 0.09), out_w - m, int(out_h * 0.87)], outline=(72, 54, 36, int(190 * fade)), width=max(2, int(4 * scale)))
    d.rectangle([m2, int(out_h * 0.09) + int(10 * scale), out_w - m2, int(out_h * 0.87) - int(10 * scale)], outline=(128, 98, 66, int(150 * fade)), width=max(1, int(2 * scale)))

    num_txt = f"CHAPTER {card.get('number', '1')}  ·  {card.get('year', '')}".strip(" ·")
    title = card.get("title", "")
    sub = card.get("subtitle", "")

    f_num = load_font(int(46 * scale), "sans_bold")
    f_title = load_font(int(96 * scale), "serif_bold")
    f_sub = load_font(int(50 * scale), "serif")

    nb = d.textbbox((0, 0), num_txt, font=f_num)
    tb = d.textbbox((0, 0), title, font=f_title)
    sb = d.textbbox((0, 0), sub, font=f_sub)

    cy_center = int(out_h * 0.47)
    # Chapter badge pill (properly account for nb[1] top bearing so text NEVER clips!)
    nt_w = nb[2] - nb[0]
    nt_h = nb[3] - nb[1]
    pw = nt_w + int(64 * scale)
    ph = nt_h + int(30 * scale)
    px = (out_w - pw) // 2
    py = cy_center - int(178 * scale)
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=int(8 * scale), fill=(156, 34, 28, a255))
    d.text((px + (pw - nt_w) // 2 - nb[0], py + (ph - nt_h) // 2 - nb[1]), num_txt, font=f_num, fill=(248, 242, 228, a255))

    # Main serif title
    tt_w = tb[2] - tb[0]
    d.text(((out_w - tt_w) // 2 - tb[0], cy_center - int(55 * scale) - tb[1]), title, font=f_title, fill=(32, 22, 14, a255))

    # Animated crimson ink divider line expanding from center
    line_prog = ease_out_cubic(min(1.0, local_t / 0.65))
    half_line = int(out_w * 0.22 * line_prog)
    ly = cy_center + int(76 * scale)
    if half_line > 4:
        d.line([(out_w // 2 - half_line, ly), (out_w // 2 + half_line, ly)], fill=(156, 34, 28, a255), width=max(3, int(5 * scale)))

    # Subtitle
    st_w = sb[2] - sb[0]
    d.text(((out_w - st_w) // 2 - sb[0], cy_center + int(106 * scale) - sb[1]), sub, font=f_sub, fill=(76, 56, 38, a255))

    img.alpha_composite(ov)
    return np.array(img.convert("RGB"))


def render_graphic_frame(bg_rgb: np.ndarray, scene: dict, local_t: float, dur: float, out_w: int, out_h: int) -> np.ndarray:
    """Renders clean animated Smart-TV editorial graphics: timeline, scale_compare, list, or quote."""
    scale = out_h / float(BASE_H)
    base = cv2.resize(bg_rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)
    base = warp_camera(base, 1.0 + 0.03 * ease_in_out(local_t / max(0.1, dur)), 0.0, 0.0, out_w, out_h)
    img = Image.fromarray(base).convert("RGBA")
    ov = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    gtype = scene.get("graphic_type", "timeline")
    f_hdr = load_font(int(64 * scale), "serif_bold")
    f_sub = load_font(int(42 * scale), "sans")
    f_big = load_font(int(88 * scale), "serif_bold")
    f_lbl = load_font(int(44 * scale), "sans_bold")

    header = scene.get("headline", "")
    if header:
        hb = d.textbbox((0, 0), header, font=f_hdr)
        d.text(((out_w - (hb[2] - hb[0])) // 2, int(out_h * 0.11)), header, font=f_hdr, fill=(32, 22, 14, 255))

    if gtype == "timeline":
        items = scene.get("items", [])
        n = max(1, len(items))
        x_left = int(out_w * 0.10)
        x_right = int(out_w * 0.90)
        y_bar = int(out_h * 0.48)
        prog = ease_out_cubic(min(1.0, local_t / max(0.8, dur * 0.65)))
        x_cur = x_left + int((x_right - x_left) * prog)
        d.line([(x_left, y_bar), (x_right, y_bar)], fill=(176, 154, 124, 255), width=max(4, int(7 * scale)))
        d.line([(x_left, y_bar), (x_cur, y_bar)], fill=(158, 36, 30, 255), width=max(5, int(9 * scale)))
        for idx, it in enumerate(items):
            frac = idx / float(max(1, n - 1))
            px = x_left + int((x_right - x_left) * frac)
            appear = ease_out_cubic(max(0.0, min(1.0, (local_t - idx * 0.45) / 0.40)))
            if appear <= 0.02:
                continue
            a = int(255 * appear)
            r = int(18 * scale)
            d.ellipse([px - r, y_bar - r, px + r, y_bar + r], fill=(158, 36, 30, a), outline=(248, 240, 222, a), width=max(2, int(4 * scale)))
            yr = it.get("year", "")
            lbl = it.get("label", "")
            yb = d.textbbox((0, 0), yr, font=f_lbl)
            lb = d.textbbox((0, 0), lbl, font=f_sub)
            above = (idx % 2 == 0)
            y_yr = (y_bar - int(115 * scale)) if above else (y_bar + int(38 * scale))
            y_lb = (y_bar - int(65 * scale)) if above else (y_bar + int(92 * scale))
            d.text((px - (yb[2] - yb[0]) // 2, y_yr), yr, font=f_lbl, fill=(148, 30, 24, a))
            d.text((px - (lb[2] - lb[0]) // 2, y_lb), lbl, font=f_sub, fill=(36, 26, 18, a))

    elif gtype == "scale_compare":
        left = scene.get("left", {})
        right = scene.get("right", {})
        p1 = ease_out_cubic(min(1.0, local_t / 0.65))
        p2 = ease_out_cubic(max(0.0, min(1.0, (local_t - 0.85) / 0.75)))
        # Two crisp museum cards side-by-side
        cw = int(out_w * 0.38)
        ch = int(out_h * 0.48)
        y0 = int(out_h * 0.28)
        cards = [
            (int(out_w * 0.09), left, (166, 38, 32), p1),
            (int(out_w * 0.53), right, (36, 108, 72), p2),
        ]
        for cx, cdata, accent, ap in cards:
            if ap <= 0.02:
                continue
            a = int(255 * ap)
            dy = int((1.0 - ap) * 28 * scale)
            d.rounded_rectangle([cx + 6, y0 + dy + 8, cx + cw + 6, y0 + dy + ch + 8], radius=int(12 * scale), fill=(26, 18, 10, int(110 * ap)))
            d.rounded_rectangle([cx, y0 + dy, cx + cw, y0 + dy + ch], radius=int(12 * scale), fill=(246, 238, 220, a), outline=(62, 46, 30, a), width=max(2, int(4 * scale)))
            d.rectangle([cx, y0 + dy, cx + cw, y0 + dy + int(16 * scale)], fill=(accent[0], accent[1], accent[2], a))
            t1 = cdata.get("title", "")
            val = cdata.get("value", "")
            sub = cdata.get("subtitle", "")
            tb = d.textbbox((0, 0), t1, font=f_lbl)
            vb = d.textbbox((0, 0), val, font=f_big)
            sb = d.textbbox((0, 0), sub, font=f_sub)
            d.text((cx + (cw - (tb[2] - tb[0])) // 2, y0 + dy + int(56 * scale)), t1, font=f_lbl, fill=(44, 32, 22, a))
            d.text((cx + (cw - (vb[2] - vb[0])) // 2, y0 + dy + int(150 * scale)), val, font=f_big, fill=(accent[0], accent[1], accent[2], a))
            d.text((cx + (cw - (sb[2] - sb[0])) // 2, y0 + dy + int(290 * scale)), sub, font=f_sub, fill=(76, 58, 40, a))

    elif gtype == "list":
        items = scene.get("items", [])
        y_start = int(out_h * 0.27)
        step_y = int(out_h * 0.115)
        for idx, it in enumerate(items):
            ap = ease_out_cubic(max(0.0, min(1.0, (local_t - idx * 0.55) / 0.40)))
            if ap <= 0.02:
                continue
            a = int(255 * ap)
            bx = int(out_w * 0.11) + int((1.0 - ap) * -35 * scale)
            bw = int(out_w * 0.78)
            bh = int(84 * scale)
            by = y_start + idx * step_y
            d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(10 * scale), fill=(246, 238, 220, int(242 * ap)), outline=(66, 48, 32, a), width=max(2, int(3 * scale)))
            d.rectangle([bx, by, bx + int(14 * scale), by + bh], fill=(158, 36, 30, a))
            d.text((bx + int(34 * scale), by + int(18 * scale)), it, font=f_lbl, fill=(32, 22, 14, a))

    img.alpha_composite(ov)
    return np.array(img.convert("RGB"))


def render_end_screen_frame(bg_rgb: np.ndarray, scene: dict, local_t: float, dur: float, out_w: int, out_h: int) -> np.ndarray:
    scale = out_h / float(BASE_H)
    base = cv2.resize(bg_rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)
    base = warp_camera(base, 1.0 + 0.03 * ease_in_out(local_t / max(0.1, dur)), 0.0, 0.0, out_w, out_h)
    img = Image.fromarray(base).convert("RGBA")
    ov = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    f_brand = load_font(int(66 * scale), "serif_bold")
    f_sub = load_font(int(42 * scale), "sans_bold")
    f_lbl = load_font(int(38 * scale), "sans")

    hdr = scene.get("headline", "HEARTLAND MAPPED")
    sub = scene.get("subline", "Which state are you watching from? Tell us in the comments!")
    hb = d.textbbox((0, 0), hdr, font=f_brand)
    sb = d.textbbox((0, 0), sub, font=f_sub)
    d.text(((out_w - (hb[2] - hb[0])) // 2, int(out_h * 0.09)), hdr, font=f_brand, fill=(34, 24, 16, 255))
    d.text(((out_w - (sb[2] - sb[0])) // 2, int(out_h * 0.19)), sub, font=f_sub, fill=(148, 34, 28, 255))

    # Two clean YouTube End-Screen card placeholders (strictly above bottom 12%)
    box_w = int(out_w * 0.36)
    box_h = int(out_h * 0.36)
    y0 = int(out_h * 0.34)
    left_x = int(out_w * 0.09)
    right_x = int(out_w * 0.55)
    for bx, label in [(left_x, scene.get("left_label", "UP NEXT: CHICAGO & PESHTIGO 1871")), (right_x, scene.get("right_label", "PLAYLIST: MIDWEST BORDER WARS"))]:
        d.rounded_rectangle([bx, y0, bx + box_w, y0 + box_h], radius=int(12 * scale), fill=(238, 228, 206, 200), outline=(88, 66, 44, 230), width=max(2, int(4 * scale)))
        lb = d.textbbox((0, 0), label, font=f_lbl)
        d.text((bx + (box_w - (lb[2] - lb[0])) // 2, y0 + box_h + int(18 * scale)), label, font=f_lbl, fill=(44, 32, 22, 255))

    img.alpha_composite(ov)
    return np.array(img.convert("RGB"))


# ======================== PARALLEL SCENE WORKER ========================

def scene_cache_key(scene: dict, ep_dir: Path, out_w: int, out_h: int) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(scene, sort_keys=True).encode("utf-8"))
    st = scene.get("type", "")
    ver = "v2_cardfix" if st == "chapter_card" else ("v2_pairfix" if st == "composite_pair" else "v1")
    h.update(f"{out_w}x{out_h}@{FPS}_{ver}".encode("utf-8"))
    for k in ("image", "image_b"):
        if scene.get(k):
            p = (ep_dir / scene[k]) if not Path(scene[k]).is_absolute() else Path(scene[k])
            if p.exists():
                st = p.stat()
                h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}".encode("utf-8"))
    return h.hexdigest()[:14]


def render_single_scene(args_tuple: tuple) -> dict:
    scene, ep_dir_str, bg_path_str, out_w, out_h, cache_dir_str = args_tuple
    ep_dir = Path(ep_dir_str)
    cache_dir = Path(cache_dir_str)
    sid = scene["id"]
    key = scene_cache_key(scene, ep_dir, out_w, out_h)
    out_mp4 = cache_dir / f"{sid}_{key}.mp4"
    dur = float(scene["duration"])
    n_frames = int(scene.get("exact_frames", max(1, int(round(dur * FPS)))))

    if out_mp4.exists() and out_mp4.stat().st_size > 2048:
        return {"id": sid, "mp4": str(out_mp4), "cached": True, "frames": n_frames, "scale_used": 1.0}

    bg_rgb = np.array(Image.open(bg_path_str).convert("RGB"))
    stype = scene.get("type", "archive")
    scale_used = 1.0

    # Preload and prepare images ONCE per scene
    plate_a = None
    plate_b = None
    par_bg = None
    par_fg = None

    def load_img(rel_path: str) -> np.ndarray:
        p = Path(rel_path) if Path(rel_path).is_absolute() else (ep_dir / rel_path)
        return np.array(Image.open(p).convert("RGB"))

    if stype in ("archive", "today"):
        raw_a = load_img(scene["image"])
        fstyle = scene.get("frame_style", "photo" if stype == "archive" else "fullbleed")
        if stype == "today":
            plate_a, scale_used = compose_archival_plate(raw_a, bg_rgb, out_w, out_h, frame_style=fstyle, max_scale=1.45)
        else:
            plate_a, scale_used = compose_archival_plate(raw_a, bg_rgb, out_w, out_h, frame_style=fstyle, max_scale=1.45)
        if scene.get("parallax", False):
            par_bg, par_fg = build_parallax_layers(plate_a)

    elif stype == "composite_pair":
        # Side-by-side museum mat layout: pairs two images (or a small archival item + companion map/portrait)
        # so smaller archival scans (<1000px) NEVER float lonely in empty parchment!
        raw_a = load_img(scene["image"])
        raw_b = load_img(scene["image_b"])
        ga = unified_archive_grade(raw_a, strength=0.78)
        gb = unified_archive_grade(raw_b, strength=0.72) if not str(scene["image_b"]).startswith("maps/") else raw_b
        canvas = Image.fromarray(cv2.resize(bg_rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)).convert("RGBA")
        slot_w = int(out_w * 0.41)
        slot_h = int(out_h * 0.54)
        centers = [int(out_w * 0.275), int(out_w * 0.725)]
        cy = int(out_h * 0.465)
        labels = [scene.get("label_a", ""), scene.get("label_b", "")]
        sc_f = out_h / float(BASE_H)
        f_cap = load_font(int(36 * sc_f), "serif_bold")
        max_sc = 1.48
        s_used = 1.0
        for idx, (arr, cx, cap) in enumerate(zip([ga, gb], centers, labels)):
            ih, iw = arr.shape[:2]
            fit = min(slot_w / float(iw), slot_h / float(ih), max_sc)
            s_used = max(s_used, fit)
            nw, nh = max(64, int(round(iw * fit))), max(64, int(round(ih * fit)))
            pic = Image.fromarray(cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA if fit < 1.0 else cv2.INTER_CUBIC)).convert("RGBA")
            bdr = max(8, int(out_h * 0.016))
            fw, fh = nw + 2 * bdr, nh + 2 * bdr
            shd = Image.new("RGBA", (fw + 30, fh + 30), (0, 0, 0, 0))
            ImageDraw.Draw(shd).rounded_rectangle([15, 18, fw + 15, fh + 18], radius=4, fill=(30, 20, 12, 115))
            shd = shd.filter(ImageFilter.GaussianBlur(12))
            mat = Image.new("RGBA", (fw, fh), (246, 238, 220, 255))
            md = ImageDraw.Draw(mat)
            md.rectangle([0, 0, fw - 1, fh - 1], outline=(78, 60, 42, 225), width=max(2, out_h // 450))
            mat.paste(pic, (bdr, bdr))
            canvas.alpha_composite(shd, (cx - shd.width // 2, cy - shd.height // 2))
            canvas.alpha_composite(mat, (cx - fw // 2, cy - fh // 2))
            if cap:
                # Museum exhibit plaque cleanly ABOVE each frame so it NEVER collides with lower-third rodape!
                cd = ImageDraw.Draw(canvas)
                cb = cd.textbbox((0, 0), cap, font=f_cap)
                cw = cb[2] - cb[0]
                ch = cb[3] - cb[1]
                pad_x = int(20 * sc_f)
                pad_y = int(10 * sc_f)
                pill_h = ch + 2 * pad_y
                py = max(int(out_h * 0.055), cy - fh // 2 - pill_h - int(16 * sc_f))
                cd.rounded_rectangle([cx - cw // 2 - pad_x, py, cx + cw // 2 + pad_x, py + pill_h], radius=int(6 * sc_f), fill=(246, 238, 219, 240), outline=(72, 54, 36, 225), width=max(2, int(2 * sc_f)))
                cd.text((cx - cw // 2 - cb[0], py + pad_y - cb[1]), cap, font=f_cap, fill=(36, 24, 14, 255))
        plate_a = np.array(canvas.convert("RGB"))
        scale_used = s_used

    elif stype == "map":
        raw_a = load_img(scene["image"])
        plate_a = cv2.resize(raw_a, (out_w, out_h), interpolation=cv2.INTER_AREA if raw_a.shape[1] >= out_w else cv2.INTER_CUBIC)
        scale_used = out_w / float(raw_a.shape[1])

    elif stype in ("oldmap_to_map", "then_now"):
        raw_a = load_img(scene["image"])
        raw_b = load_img(scene["image_b"])
        plate_a, scale_a = compose_archival_plate(raw_a, bg_rgb, out_w, out_h, frame_style=scene.get("frame_style_a", "fullbleed"), max_scale=1.45)
        if stype == "oldmap_to_map":
            plate_b = cv2.resize(raw_b, (out_w, out_h), interpolation=cv2.INTER_AREA if raw_b.shape[1] >= out_w else cv2.INTER_CUBIC)
            scale_used = scale_a
        else:
            plate_b, scale_b = compose_archival_plate(raw_b, bg_rgb, out_w, out_h, frame_style=scene.get("frame_style_b", "fullbleed"), max_scale=1.45)
            scale_used = max(scale_a, scale_b)

    # Camera plan: list of smooth shots [{t, zoom, pan_x, pan_y, end_zoom, end_pan_x, end_pan_y}]
    shots = scene.get("shots") or [{
        "t": 0.0,
        "zoom": float(scene.get("zoom_start", 1.02)),
        "pan_x": float(scene.get("pan_x_start", 0.0)),
        "pan_y": float(scene.get("pan_y_start", 0.0)),
        "end_zoom": float(scene.get("zoom_end", 1.14)),
        "end_pan_x": float(scene.get("pan_x_end", 0.0)),
        "end_pan_y": float(scene.get("pan_y_end", 0.0)),
    }]
    overlays = scene.get("overlays", [])
    dissolve_in = float(scene.get("fade_in", 0.25))
    dissolve_out = float(scene.get("fade_out", 0.25))

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{out_w}x{out_h}", "-pix_fmt", "rgb24", "-r", str(FPS),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-video_track_timescale", "24000",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    for fi in range(n_frames):
        lt = fi / float(FPS)
        # Find active shot
        cur_shot = shots[0]
        next_t = dur
        for si, sh in enumerate(shots):
            if lt >= float(sh["t"]):
                cur_shot = sh
                next_t = float(shots[si + 1]["t"]) if si + 1 < len(shots) else dur
        s_dur = max(0.05, next_t - float(cur_shot["t"]))
        p = ease_in_out((lt - float(cur_shot["t"])) / s_dur)
        z = float(cur_shot["zoom"]) + (float(cur_shot.get("end_zoom", cur_shot["zoom"])) - float(cur_shot["zoom"])) * p
        px = float(cur_shot.get("pan_x", 0.0)) + (float(cur_shot.get("end_pan_x", cur_shot.get("pan_x", 0.0))) - float(cur_shot.get("pan_x", 0.0))) * p
        py = float(cur_shot.get("pan_y", 0.0)) + (float(cur_shot.get("end_pan_y", cur_shot.get("pan_y", 0.0))) - float(cur_shot.get("pan_y", 0.0))) * p

        if stype == "chapter_card":
            frame = render_chapter_card_frame(bg_rgb, scene["card"], lt, dur, out_w, out_h)
        elif stype == "graphic":
            frame = render_graphic_frame(bg_rgb, scene, lt, dur, out_w, out_h)
        elif stype == "end_screen":
            frame = render_end_screen_frame(bg_rgb, scene, lt, dur, out_w, out_h)
        elif stype in ("oldmap_to_map", "then_now"):
            fa = warp_camera(plate_a, z, px, py, out_w, out_h)
            fb = warp_camera(plate_b, z, px, py, out_w, out_h)
            d_mid = float(scene.get("dissolve_at", dur * 0.45))
            d_len = float(scene.get("dissolve_dur", 1.25))
            mix = ease_in_out((lt - (d_mid - d_len * 0.5)) / max(0.1, d_len))
            frame = cv2.addWeighted(fa, 1.0 - mix, fb, mix, 0.0)
        elif par_bg is not None and par_fg is not None:
            # 2.5D parallax: foreground zooms/drifts slightly faster than background!
            bg_f = warp_camera(par_bg, z, px * 0.7, py * 0.7, out_w, out_h)
            fg_rgb_w = warp_camera(par_fg[:, :, :3], z * 1.035, px * 1.15, py * 1.15, out_w, out_h)
            fg_a_w = warp_camera(np.repeat(par_fg[:, :, 3:4], 3, axis=2), z * 1.035, px * 1.15, py * 1.15, out_w, out_h)[:, :, :1].astype(np.float32) / 255.0
            frame = np.clip(bg_f.astype(np.float32) * (1.0 - fg_a_w) + fg_rgb_w.astype(np.float32) * fg_a_w, 0, 255).astype(np.uint8)
        else:
            frame = warp_camera(plate_a, z, px, py, out_w, out_h)

        # Gentle film grain on archive/transition frames for visual unity
        if stype in ("archive", "oldmap_to_map", "then_now", "composite_pair") and out_w >= 1280:
            frame = add_subtle_grain(frame, seed=(hash(sid) + fi) & 0xFFFFFFFF, amount=3.2)

        # Subtle warm dark dip fade on chapter transitions if explicitly requested (never pure black gaps!)
        if dissolve_in > 0 and lt < dissolve_in and scene.get("soft_fade", False):
            w_f = ease_in_out(lt / dissolve_in)
            tint = np.full_like(frame, (28, 22, 16))
            frame = cv2.addWeighted(tint, 1.0 - w_f, frame, w_f, 0.0)
        if dissolve_out > 0 and (dur - lt) < dissolve_out and scene.get("soft_fade", False):
            w_f = ease_in_out((dur - lt) / dissolve_out)
            tint = np.full_like(frame, (28, 22, 16))
            frame = cv2.addWeighted(tint, 1.0 - w_f, frame, w_f, 0.0)

        frame = draw_smart_tv_overlays(frame, overlays, lt, dur, out_w, out_h)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"FFmpeg scene {sid} failed: {err[-400:]}")
    return {"id": sid, "mp4": str(out_mp4), "cached": False, "frames": n_frames, "scale_used": round(scale_used, 3)}


def render_longform(ep_dir: Path, preview: bool = False, audio_only: bool = False, workers: int = 10):
    t_start = time.time()
    script_data = json.loads((ep_dir / "script_longform.json").read_text(encoding="utf-8"))
    spec_path = ep_dir / "longform_spec.json"

    music_map = {
        "curiosity": ROOT / "assets" / "music" / "mood_curiosity_akesa_d.wav",
        "warm": ROOT / "assets" / "music" / "mood_warm_akesa_b.wav",
        "tension": ROOT / "assets" / "music" / "mood_tension_drone.mp3",
        "nostalgia": ROOT / "assets" / "music" / "mood_nostalgia_garden_wisdom.mp3",
    }

    foley_cues = []
    silence_dips = []
    if spec_path.exists():
        spec_pre = json.loads(spec_path.read_text(encoding="utf-8"))
        foley_cues = spec_pre.get("foley_cues", [])
        silence_dips = spec_pre.get("silence_dips", [])

    if audio_only or not (ep_dir / "audio" / "master_audio.wav").exists() or not (ep_dir / "audio_timings.json").exists():
        assemble_and_master_audio(ep_dir, script_data, music_map, foley_cues=foley_cues, silence_dips=silence_dips)
        if audio_only:
            print("Audio assembly, alignment, .srt, and -14 LUFS mastering complete!")
            return

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    # Re-mix audio if spec has foley/dips and master needs refresh
    if spec.get("remaster_audio", False):
        assemble_and_master_audio(ep_dir, script_data, music_map, foley_cues=spec.get("foley_cues", []), silence_dips=spec.get("silence_dips", []))

    out_w, out_h = (640, 360) if preview else (BASE_W, BASE_H)
    cache_dir = ep_dir / ("cache_preview" if preview else "cache_1080p")
    cache_dir.mkdir(parents=True, exist_ok=True)
    bg_path = ROOT / "assets" / "maps" / "parchment_bg_16x9.jpg"

    scenes = spec["scenes"]
    # Verify exact frame-accurate sync vs master audio (zero rounding drift across 60+ scenes!)
    audio_dur = float(json.loads((ep_dir / "audio_timings.json").read_text(encoding="utf-8"))["duration"])
    target_total_frames = int(round(audio_dur * FPS))
    prev_frames = sum(max(1, int(round(float(s["duration"]) * FPS))) for s in scenes[:-1])
    last_frames = max(24, target_total_frames - prev_frames)
    scenes[-1]["exact_frames"] = last_frames
    scenes[-1]["duration"] = round(last_frames / float(FPS), 4)
    print(f"Frame-locked sync: {prev_frames + last_frames} total frames = {(prev_frames + last_frames)/FPS:.3f}s (audio={audio_dur:.3f}s).")

    tasks = [(sc, str(ep_dir), str(bg_path), out_w, out_h, str(cache_dir)) for sc in scenes]
    print(f"Rendering {len(tasks)} scenes ({out_w}x{out_h} @ {FPS} FPS) across {workers} workers...")
    results_by_id = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(render_single_scene, t): t[0]["id"] for t in tasks}
        done_n = 0
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            results_by_id[res["id"]] = res
            done_n += 1
            if done_n % 10 == 0 or done_n == len(tasks):
                print(f"  Progress: {done_n}/{len(tasks)} scenes ({'cached' if res['cached'] else 'rendered'})")

    # Concatenate via FFmpeg concat demuxer (-c copy)
    concat_txt = cache_dir / "concat.txt"
    ordered_lines = []
    for sc in scenes:
        mp4_p = results_by_id[sc["id"]]["mp4"].replace("\\", "/")
        ordered_lines.append(f"file '{mp4_p}'")
    concat_txt.write_text("\n".join(ordered_lines), encoding="utf-8")

    video_only = cache_dir / "video_concat.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(video_only)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True,
    )

    out_name = "preview_360p.mp4" if preview else spec.get("output_mp4", "video.mp4")
    final_mp4 = ep_dir / out_name
    master_wav = ep_dir / "audio" / "master_audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_only),
            "-i", str(master_wav),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-shortest",
            str(final_mp4),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True,
    )
    elapsed = time.time() - t_start
    print(f"SUCCESS! Rendered {final_mp4} in {elapsed:.1f}s.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_dir", help="Longform episode folder")
    ap.add_argument("--preview", action="store_true", help="Fast 640x360 preview render")
    ap.add_argument("--audio-only", action="store_true", help="Only assemble/align/master audio + .srt")
    ap.add_argument("--workers", type=int, default=10, help="Parallel worker processes")
    args = ap.parse_args()
    render_longform(Path(args.episode_dir).resolve(), preview=args.preview, audio_only=args.audio_only, workers=args.workers)
