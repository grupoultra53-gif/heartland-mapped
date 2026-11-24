"""
Heartland Mapped — Fish Audio (or any human/AI narration) -> Word-Level Aligner (v2)
Takes a single full-episode audio file (e.g. downloaded from Fish Audio Ethan) plus a list
of scene texts, runs local faster-whisper word-level transcription, aligns every exact script
word to its millisecond [start, end] timestamps using sequence matching, and writes:
  - <ep_dir>/<slug>.wav (44.1 kHz mono PCM, optionally gently sped up if speed != 1.0)
  - <ep_dir>/<slug>.mp3 (192 kbps archival narration)
  - <ep_dir>/audio_timings.json (exact schema used by render_video.py & audit_video.py)
"""
import difflib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def norm_tok(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def align_narration(
    raw_audio_path: Path,
    scenes: list,
    out_wav_path: Path,
    out_mp3_path: Path,
    out_timings_path: Path,
    voice_label: str = "Fish Audio — Ethan (@Fish Official)",
    speed: float = 1.0,
    model_size: str = "base.en",
):
    """
    `scenes`: list of {"id": "scene_01", "text": "..."}
    """
    # 1. Trim leading/trailing silence and convert to 44.1 kHz mono WAV (optionally adjusting speed)
    af_filters = [
        "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB",
        "areverse",
        "silenceremove=start_periods=1:start_silence=0.08:start_threshold=-45dB",
        "areverse",
    ]
    if abs(speed - 1.0) > 0.005:
        af_filters.append(f"atempo={speed:.3f}")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(raw_audio_path),
            "-af",
            ",".join(af_filters),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(out_wav_path),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(out_wav_path),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(out_mp3_path),
        ],
        check=True,
    )
    total_dur = probe_duration(out_wav_path)

    # 2. Decode 16 kHz mono float32 directly via ffmpeg (avoids PyAV compatibility issues)
    pcm16k = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(out_wav_path),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-",
        ]
    )
    audio_16k = np.frombuffer(pcm16k, dtype=np.int16).astype(np.float32) / 32768.0

    # 3. Extract word-level timestamps via local faster-whisper
    print(f"Running faster-whisper ({model_size}) word alignment on {out_wav_path.name} ({total_dur:.2f}s)...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_16k, language="en", word_timestamps=True, vad_filter=False)
    asr_words = []
    for seg in segments:
        if not seg.words:
            continue
        for w in seg.words:
            tok = w.word.strip()
            if tok:
                asr_words.append(
                    {
                        "raw": tok,
                        "norm": norm_tok(tok),
                        "start": float(w.start),
                        "end": float(w.end),
                    }
                )
    print(f"ASR detected {len(asr_words)} words.")

    # 3. Tokenize exact script words while keeping scene ownership
    script_tokens = []
    for sc_idx, sc in enumerate(scenes):
        for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9',.\-]*", sc["text"]):
            clean = raw.strip(".,;:\"'")
            if clean:
                script_tokens.append(
                    {
                        "scene_idx": sc_idx,
                        "text": clean,
                        "norm": norm_tok(clean),
                    }
                )

    # 4. Align script tokens -> ASR word timestamps via SequenceMatcher + monotonic interpolation
    s_norms = [t["norm"] for t in script_tokens]
    a_norms = [w["norm"] for w in asr_words]
    matcher = difflib.SequenceMatcher(None, s_norms, a_norms, autojunk=False)

    aligned = [None] * len(script_tokens)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                aligned[i1 + k] = (asr_words[j1 + k]["start"], asr_words[j1 + k]["end"])
        elif tag == "replace":
            if j2 > j1:
                t_a = asr_words[j1]["start"]
                t_b = asr_words[j2 - 1]["end"]
                cnt = i2 - i1
                span = max(0.05, t_b - t_a)
                for k in range(cnt):
                    aligned[i1 + k] = (t_a + span * (k / cnt), t_a + span * ((k + 1) / cnt))

    # Fill any remaining unaligned tokens by smooth interpolation between neighbors
    n_tok = len(aligned)
    for idx in range(n_tok):
        if aligned[idx] is None:
            prev_t = 0.0
            for p in range(idx - 1, -1, -1):
                if aligned[p] is not None:
                    prev_t = aligned[p][1]
                    break
            next_t = total_dur
            next_i = n_tok
            for q in range(idx + 1, n_tok):
                if aligned[q] is not None:
                    next_t = aligned[q][0]
                    next_i = q
                    break
            gap_cnt = next_i - idx
            step = max(0.04, (next_t - prev_t) / max(1, gap_cnt))
            aligned[idx] = (prev_t, min(next_t, prev_t + step))

    # 5. Build per-scene timeline with clean contiguous boundaries
    scene_word_lists = [[] for _ in scenes]
    all_words = []
    for tok, (ws, we) in zip(script_tokens, aligned):
        ws = max(0.0, min(total_dur - 0.02, ws))
        we = max(ws + 0.03, min(total_dur, we))
        entry = {"text": tok["text"], "start": round(ws, 3), "end": round(we, 3)}
        scene_word_lists[tok["scene_idx"]].append(entry)
        all_words.append(entry)

    timeline = []
    for i, sc in enumerate(scenes):
        sw = scene_word_lists[i]
        speech_end = sw[-1]["end"] if sw else (timeline[-1]["end_sec"] if timeline else 0.0)
        if i == 0:
            s_start = 0.0
        else:
            s_start = timeline[-1]["end_sec"]

        if i < len(scenes) - 1:
            next_first = scene_word_lists[i + 1][0]["start"] if scene_word_lists[i + 1] else speech_end + 0.15
            # Place scene cut cleanly right before next scene's first word (max 0.12s lead-in)
            s_end = max(speech_end + 0.04, next_first - 0.06)
            s_end = min(s_end, next_first)
        else:
            s_end = total_dur

        timeline.append(
            {
                "id": sc["id"],
                "text": sc["text"],
                "start_sec": round(s_start, 3),
                "speech_end_sec": round(speech_end, 3),
                "end_sec": round(s_end, 3),
                "words": sw,
            }
        )

    out_meta = {
        "voice": voice_label,
        "total_duration_sec": round(total_dur, 3),
        "scenes": timeline,
        "words": all_words,
    }
    with open(out_timings_path, "w", encoding="utf-8") as f:
        json.dump(out_meta, f, indent=2)

    print(f"Saved {out_timings_path} ({total_dur:.2f}s, {len(all_words)} aligned words):")
    for sc in timeline:
        print(f"  {sc['id']}: {sc['start_sec']:6.2f}s -> {sc['end_sec']:6.2f}s ({sc['end_sec']-sc['start_sec']:.2f}s)")
    return out_meta


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python align_audio.py <raw_audio> <episode_dir> [slug] [speed]")
        sys.exit(1)
    raw_p = Path(sys.argv[1])
    ep_d = Path(sys.argv[2])
    slug = sys.argv[3] if len(sys.argv) > 3 else ep_d.name
    spd = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    lines = [ln.strip() for ln in (ep_d / "script_en.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    sc_list = [{"id": f"scene_{i+1:02d}", "text": txt} for i, txt in enumerate(lines)]
    align_narration(
        raw_p,
        sc_list,
        ep_d / f"{slug}.wav",
        ep_d / f"{slug}.mp3",
        ep_d / "audio_timings.json",
        speed=spd,
    )
