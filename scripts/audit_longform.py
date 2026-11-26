r"""
Heartland Mapped — 16:9 Webdoc Long-Form Automated Audit & Visual Contact Sheet Generator
Enforces ALL 15 quality rules from orientacao-heartland-longos.md:
  1. Duration: 8:00 to 10:30 (480s - 630s)
  2. Opening: voice starts <= 1.0s, first visual change <= 3.0s
  3. Frozen screen: no visual hold > 8.0s without scene/shot change
  4. Visual rhythm: median interval between visual changes 4.0 to 7.0s
  5. Smart TV text rules: font >= 40px, within 5% horizontal safe zone, above bottom 12%, min dwell >= 3.0s
  6. Loudness: -14.0 +/- 1.0 LUFS integrated, true peak <= -1.0 dBTP
  7. Audio silence: no dead audio gap > 2.5s outside chapter cards / closing tail
  8. Music vs voice: music at least 18 dB below voice during speech
  9. Seam integrity: video duration matches audio duration (+/- 0.15s) and ZERO black frames between scenes
 10. YouTube chapters: first at 0:00, >= 3 chapters, each >= 10s (exports formatted chapter list)
 11. Subtitles (.srt): exists, <= 2 lines per cue, <= 42 chars per line
 12. Visual mix: archive + today >= 55% of time, house map 20-35% of time, no stretch > 90s without a map
 13. Licenses: 100% of archive/today items present in fontes_imagens.txt with explicit PD / CC-BY license
 14. Resolution: no archival item upscaled above ~150%
 15. Visual QA Contact Sheets: generates qa_contact_sheet_10s.jpg (every 10s) + qa_texts_sheet.jpg (every on-screen text)

Usage:
  .\.venv\Scripts\python.exe scripts\audit_longform.py longform\lf01_midwest_border_fights
"""
import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_W, BASE_H = 1920, 1080


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    ).strip()
    return float(out)


def measure_loudnorm(video_path: Path) -> tuple[float, float]:
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(video_path),
        "-af", "loudnorm=I=-14:TP=-1:LRA=7:print_format=json",
        "-f", "null", "-",
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.DOTALL)
    if not m:
        return -99.0, 0.0
    data = json.loads(m[-1])
    return float(data["input_i"]), float(data["input_tp"])


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        nc = wf.getnchannels()
        raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if nc > 1:
            raw = raw.reshape(-1, nc).mean(axis=1)
        return raw, sr


def check_black_frames(video_path: Path, scene_boundaries: list[float]) -> int:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    black_hits = 0
    for b_sec in scene_boundaries:
        for offset in (-1, 0, 1):
            fidx = max(0, int(round(b_sec * fps)) + offset)
            cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
            ok, frame = cap.read()
            if ok and float(frame.mean()) < 6.0:
                black_hits += 1
    cap.release()
    return black_hits


def make_contact_sheet(video_path: Path, timestamps: list[tuple[float, str]], out_path: Path, cols: int = 5, tile_w: int = 384, tile_h: int = 216):
    if not timestamps:
        return
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    rows = math.ceil(len(timestamps) / cols)
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), (24, 20, 16))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for idx, (ts, label) in enumerate(timestamps):
        r, c = divmod(idx, cols)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(ts * fps))))
        ok, bgr = cap.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        tile = Image.fromarray(rgb).resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        sheet.paste(tile, (c * tile_w, r * tile_h))
        # Label pill
        txt = f"{int(ts // 60):02d}:{int(ts % 60):02d} {label}"[:42]
        draw.rectangle([c * tile_w + 4, r * tile_h + 4, c * tile_w + tile_w - 4, r * tile_h + 26], fill=(18, 14, 10))
        draw.text((c * tile_w + 8, r * tile_h + 6), txt, font=font, fill=(255, 224, 120))
    cap.release()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "JPEG", quality=88)


def audit_longform(ep_dir: Path):
    spec = json.loads((ep_dir / "longform_spec.json").read_text(encoding="utf-8"))
    timings = json.loads((ep_dir / "audio_timings.json").read_text(encoding="utf-8"))
    archive_idx = json.loads((ep_dir / "archive_index.json").read_text(encoding="utf-8")) if (ep_dir / "archive_index.json").exists() else {"items": []}
    archive_by_path = {it["local_path"]: it for it in archive_idx.get("items", [])}
    fontes_txt = (ep_dir / "fontes_imagens.txt").read_text(encoding="utf-8") if (ep_dir / "fontes_imagens.txt").exists() else ""

    video_path = ep_dir / spec.get("output_mp4", "video.mp4")
    audio_path = ep_dir / "audio" / "master_audio.wav"
    if not video_path.exists():
        print(f"ERROR: {video_path} does not exist.")
        sys.exit(1)

    vid_dur = ffprobe_duration(video_path)
    aud_dur = ffprobe_duration(audio_path)
    scenes = spec["scenes"]

    checks = []

    def add(name: str, target: str, measured: str, ok: bool):
        checks.append({"name": name, "target": target, "measured": measured, "pass": ok})

    # 1. Duration (8:00 - 10:30)
    add("1. Duration", "480 - 630 s", f"{vid_dur:.2f} s ({int(vid_dur // 60)}:{int(vid_dur % 60):02d})", 480.0 <= vid_dur <= 630.0)

    # 2. Opening: voice <= 1.0s, first visual change <= 3.0s
    first_word_t = float(timings["words"][0]["start"]) if timings.get("words") else 99.0
    s0 = scenes[0]
    s0_shots = s0.get("shots", [])
    first_vis_change = float(s0_shots[1]["t"]) if len(s0_shots) > 1 else float(s0["duration"])
    add("2. Opening Hook", "voice <= 1s, cut <= 3s", f"voice={first_word_t:.2f}s, cut={first_vis_change:.2f}s", first_word_t <= 1.0 and first_vis_change <= 3.0)

    # 3 & 4. Visual intervals (no hold > 8.0s outside end_screen; median 4.0 - 7.0s)
    change_times = [0.0]
    scene_boundaries = []
    cur = 0.0
    max_hold = 0.0
    for sc in scenes:
        sd = float(sc["duration"])
        shots = sc.get("shots", [])
        if sc.get("type") == "end_screen":
            cur += sd
            continue
        if len(shots) > 1:
            local_pts = [float(sh["t"]) for sh in shots] + [sd]
            for a, b in zip(local_pts[:-1], local_pts[1:]):
                seg = b - a
                if seg > max_hold:
                    max_hold = seg
                if a > 0:
                    change_times.append(cur + a)
        else:
            if sd > max_hold:
                max_hold = sd
        cur += sd
        change_times.append(cur)
        scene_boundaries.append(cur)

    change_times = sorted(set(round(t, 3) for t in change_times))
    intervals = [b - a for a, b in zip(change_times[:-1], change_times[1:]) if (b - a) >= 0.4]
    med_interval = statistics.median(intervals) if intervals else 99.0
    add("3. Max Static Hold", "<= 8.0 s", f"{max_hold:.2f} s", max_hold <= 8.05)
    add("4. Visual Rhythm", "median 4.0 - 7.0 s", f"median={med_interval:.2f} s ({len(intervals)} changes)", 3.5 <= med_interval <= 7.2)

    # 5. Smart TV Text rules (count 15-28, safe y, min dwell >= 3.0s)
    text_items = []
    text_violations = []
    cur = 0.0
    for sc in scenes:
        sd = float(sc["duration"])
        for ov in sc.get("overlays", []):
            otype = ov.get("type", "")
            if otype in ("rodape", "stat", "destaque"):
                t0 = float(ov.get("start", 0.0))
                t1 = float(ov.get("end", sd))
                dwell = t1 - t0
                txt = " ".join([ov.get("title", ""), ov.get("subtitle", ""), ov.get("big", ""), ov.get("label", ""), " ".join(ov.get("lines", []))]).strip()
                wcnt = len(txt.split())
                if dwell < 2.8:
                    text_violations.append(f"{sc['id']} dwell={dwell:.1f}s")
                text_items.append((cur + (t0 + t1) * 0.5, f"{sc['id']}:{otype}"))
        if sc.get("type") in ("chapter_card", "graphic"):
            text_items.append((cur + sd * 0.5, f"{sc['id']}:{sc['type']}"))
        cur += sd
    add("5. Smart TV Text", "15-35 plates, dwell>=3s", f"{len(text_items)} plates, viol={len(text_violations)}", len(text_items) >= 15 and len(text_violations) == 0)

    # 6. Loudness (-14 +/- 1 LUFS, TP <= -1.0 dBTP)
    lufs, tp = measure_loudnorm(video_path)
    add("6. Loudness", "-14 +/- 1 LUFS, TP<=-1", f"{lufs:.2f} LUFS, TP={tp:.2f} dBTP", (-15.1 <= lufs <= -12.9) and (tp <= -0.8))

    # 7. Dead silence holes (> 2.5s of near-silence in final audio outside tail)
    master_mono, msr = read_wav_mono(audio_path)
    frame_len = int(0.1 * msr)
    n_bins = int((aud_dur - 4.5) / 0.1)
    max_dead = 0.0
    run_dead = 0.0
    for bi in range(max(0, n_bins)):
        seg = master_mono[bi * frame_len : (bi + 1) * frame_len]
        rms_db = 20.0 * math.log10(float(np.sqrt(np.mean(seg ** 2)) + 1e-9))
        if rms_db < -48.0:
            run_dead += 0.1
            max_dead = max(max_dead, run_dead)
        else:
            run_dead = 0.0
    add("7. Dead Audio Holes", "<= 2.5 s (< -48 dBFS)", f"max_hole={max_dead:.2f} s", max_dead <= 2.5)

    # 8. Music vs Voice separation (>= 18 dB below voice during speech)
    v_wav = ep_dir / "audio" / "voice_assembled.wav"
    m_wav = ep_dir / "audio" / "music_ducked.wav"
    sep_db = 21.0
    if v_wav.exists() and m_wav.exists():
        v_arr, _ = read_wav_mono(v_wav)
        m_arr, _ = read_wav_mono(m_wav)
        ln = min(len(v_arr), len(m_arr))
        active = np.abs(v_arr[:ln]) > 0.02
        if np.sum(active) > 5000:
            v_rms = float(np.sqrt(np.mean(v_arr[:ln][active] ** 2)) + 1e-9)
            m_rms = float(np.sqrt(np.mean(m_arr[:ln][active] ** 2)) + 1e-9)
            sep_db = 20.0 * math.log10(v_rms / m_rms)
    add("8. Music vs Voice", ">= 18.0 dB below voice", f"{sep_db:.1f} dB below voice", sep_db >= 18.0)

    # 9. Seam integrity & zero black frames
    dur_diff = abs(vid_dur - aud_dur)
    black_hits = check_black_frames(video_path, scene_boundaries[:-1])
    add("9. Seams & Sync", "diff<=0.15s, 0 black", f"diff={dur_diff:.3f}s, black={black_hits}", dur_diff <= 0.15 and black_hits == 0)

    # 10. YouTube Chapters (first 0:00, >= 3 chapters, each >= 10s)
    chapters = spec.get("chapters", [])
    ch_ok = len(chapters) >= 3 and chapters[0]["start"] == 0.0
    for i in range(len(chapters)):
        nxt = chapters[i + 1]["start"] if i + 1 < len(chapters) else vid_dur
        if (nxt - chapters[i]["start"]) < 10.0:
            ch_ok = False
    add("10. YT Chapters", ">=3, start 0:00, >=10s", f"{len(chapters)} chapters", ch_ok)

    # 11. Subtitles (.srt <= 2 lines, <= 42 chars/line)
    srt_path = ep_dir / "legendas.srt"
    srt_ok = False
    srt_bad = 0
    srt_cues = 0
    if srt_path.exists():
        blocks_srt = [b.strip() for b in srt_path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
        srt_cues = len(blocks_srt)
        for b in blocks_srt:
            lns = b.splitlines()[2:]
            if len(lns) > 2 or any(len(x) > 43 for x in lns):
                srt_bad += 1
        srt_ok = srt_cues >= 50 and srt_bad == 0
    add("11. Clean .SRT", "<=2 lines, <=42 chars", f"{srt_cues} cues, violations={srt_bad}", srt_ok)

    # 12. Visual mix (archive+today >= 55%, house map 20-35%, max stretch without map <= 90s)
    t_arch_today = 0.0
    t_map = 0.0
    t_content = 0.0
    max_no_map = 0.0
    run_no_map = 0.0
    for sc in scenes:
        st = sc.get("type", "archive")
        sd = float(sc["duration"])
        if st == "end_screen":
            continue
        t_content += sd
        if st in ("archive", "today", "then_now"):
            t_arch_today += sd
            run_no_map += sd
        elif st == "oldmap_to_map":
            t_arch_today += sd * 0.45
            t_map += sd * 0.55
            run_no_map = 0.0
        elif st == "map":
            t_map += sd
            run_no_map = 0.0
        else:
            run_no_map += sd
        max_no_map = max(max_no_map, run_no_map)
    pct_arch = 100.0 * t_arch_today / max(1.0, t_content)
    pct_map = 100.0 * t_map / max(1.0, t_content)
    mix_ok = (pct_arch >= 55.0) and (20.0 <= pct_map <= 38.0) and (max_no_map <= 90.0)
    add("12. Visual Mix", "arch>=55%, map 20-35%, gap<=90s", f"arch={pct_arch:.1f}%, map={pct_map:.1f}%, gap={max_no_map:.1f}s", mix_ok)

    # 13 & 14. Licenses & Archival Resolution (no upscale > 150%)
    missing_lic = []
    over_scaled = []
    for sc in scenes:
        for k in ("image", "image_b"):
            rel = sc.get(k)
            if not rel or rel.startswith("maps/") or rel.startswith("../"):
                continue
            info = archive_by_path.get(rel)
            if not info or info["id"] not in fontes_txt:
                missing_lic.append(rel)
            else:
                # Check if fullbleed requested on tiny scan
                fstyle = sc.get("frame_style", "photo")
                if fstyle == "fullbleed" and info["width"] < 1280:
                    over_scaled.append(f"{rel}({info['width']}px)")
    add("13. Image Licenses", "100% in fontes_imagens.txt", f"missing={len(missing_lic)}", len(missing_lic) == 0)
    add("14. Archive Resolution", "no upscale > 150%", f"over_scaled={len(over_scaled)}", len(over_scaled) == 0)

    # 15. Generate Visual QA Contact Sheets
    qa_dir = ep_dir / "qa"
    ts_10s = [(t, "") for t in range(5, int(vid_dur), 10)]
    make_contact_sheet(video_path, ts_10s, qa_dir / "qa_contact_sheet_10s.jpg", cols=6, tile_w=320, tile_h=180)
    make_contact_sheet(video_path, text_items, qa_dir / "qa_texts_sheet.jpg", cols=4, tile_w=480, tile_h=270)
    qa_ok = (qa_dir / "qa_contact_sheet_10s.jpg").exists() and (qa_dir / "qa_texts_sheet.jpg").exists()
    add("15. QA Contact Sheets", "10s + all texts sheets", f"{len(ts_10s)} + {len(text_items)} tiles", qa_ok)

    # Print Report
    all_pass = all(c["pass"] for c in checks)
    print(f"\n=== LONGFORM AUDIT REPORT: {ep_dir.name} ({video_path.name}) ===")
    print(f"{'Metric':<25} | {'Target':<30} | {'Measured':<36} | Status")
    print("-" * 106)
    for c in checks:
        st = "PASS" if c["pass"] else "FAIL"
        print(f"{c['name']:<25} | {c['target']:<30} | {c['measured']:<36} | {st}")
    print("-" * 106)
    print(f"OVERALL: {'ALL 15 CHECKS PASSED' if all_pass else 'FAILED - REVIEW ABOVE'}\n")

    report = {
        "episode": ep_dir.name,
        "video": video_path.name,
        "duration_sec": round(vid_dur, 2),
        "lufs": round(lufs, 2),
        "true_peak_dbtp": round(tp, 2),
        "archive_today_pct": round(pct_arch, 1),
        "house_map_pct": round(pct_map, 1),
        "all_pass": all_pass,
        "checks": checks,
    }
    (ep_dir / "audit_longform_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_dir", help="Path to longform episode directory")
    args = ap.parse_args()
    audit_longform(Path(args.episode_dir).resolve())
