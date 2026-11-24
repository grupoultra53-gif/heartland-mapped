"""
Reusable 44.1 kHz Procedural Situational Foley, Subtle Documentary Acoustic Bed
with Auto-Ducking, & Cinematic Sound Effects Library (v2).
"""
import numpy as np
from scipy.signal import butter, lfilter

SR = 44100


def bandpass(data, lowcut, highcut, fs=SR, order=3):
    nyq = 0.5 * fs
    low = max(0.001, min(lowcut / nyq, 0.99))
    high = max(low + 0.001, min(highcut / nyq, 0.999))
    b, a = butter(order, [low, high], btype="band")
    return lfilter(b, a, data)


def lowpass(data, cutoff, fs=SR, order=3):
    nyq = 0.5 * fs
    c = max(0.001, min(cutoff / nyq, 0.99))
    b, a = butter(order, c, btype="low")
    return lfilter(b, a, data)


def add_sound(buf, start_sec, sound_arr, gain=1.0):
    idx = int(start_sec * SR)
    if idx < 0 or idx >= len(buf):
        return
    end = min(len(buf), idx + len(sound_arr))
    seg_len = end - idx
    if seg_len > 0:
        buf[idx:end] += sound_arr[:seg_len] * gain


def generate_documentary_bed(duration_sec: float, bpm: float = 96.0, seed: int = 42) -> np.ndarray:
    """
    Warm, low-fatigue Heartland acoustic documentary underscore bed (v2).
    Fills inter-phrase silence gaps cleanly (preventing 15-28 dB dead holes)
    without harsh synths or vocal-masking frequencies:
      - Warm upright-bass pizzicato notes (low-passed < 420 Hz)
      - Gentle warm acoustic folk pluck harmony (I - V - vi - IV in D major, < 2.2 kHz)
      - Soft brushed percussion pulse on off-beats
    """
    rng = np.random.default_rng(seed)
    n = int(np.ceil(duration_sec * SR))
    buf = np.zeros(n, dtype=np.float32)

    beat_dur = 60.0 / bpm
    # Warm Americana/Heartland D-major chord progression: D, A, Bm, G (root Hz, fifth Hz, third Hz)
    chords = [
        (73.42, 146.83, 220.00, 293.66),  # D
        (110.00, 164.81, 220.00, 277.18),  # A
        (123.47, 185.00, 246.94, 293.66),  # Bm
        (98.00, 146.83, 196.00, 246.94),   # G
    ]

    total_beats = int(duration_sec / beat_dur) + 2
    for b in range(total_beats):
        t0 = b * beat_dur
        chord = chords[(b // 4) % len(chords)]
        pos_in_bar = b % 4

        # 1) Warm woody upright bass pluck on beats 0 and 2
        if pos_in_bar in (0, 2):
            bass_f = chord[0] if pos_in_bar == 0 else chord[1] * 0.5
            bn = int(min(beat_dur * 1.4, 0.85) * SR)
            bt = np.linspace(0, bn / SR, bn, endpoint=False)
            bass = (
                np.sin(2 * np.pi * bass_f * bt) * 0.72
                + np.sin(2 * np.pi * bass_f * 2.0 * bt) * 0.24 * np.exp(-bt * 5.0)
                + np.sin(2 * np.pi * bass_f * 3.0 * bt) * 0.08 * np.exp(-bt * 9.0)
            ) * np.exp(-bt * 3.4)
            attack = min(int(0.015 * SR), bn)
            bass[:attack] *= np.linspace(0, 1, attack)
            add_sound(buf, t0, bass.astype(np.float32), gain=0.46)

        # 2) Subtle warm acoustic guitar / folk harp arpeggio notes on every beat
        note_f = chord[1 + (pos_in_bar % 3)]
        pn = int(min(beat_dur * 1.15, 0.72) * SR)
        pt = np.linspace(0, pn / SR, pn, endpoint=False)
        pluck = (
            np.sin(2 * np.pi * note_f * pt) * 0.65
            + np.sin(2 * np.pi * note_f * 2.0 * pt) * 0.22 * np.exp(-pt * 7.5)
        ) * np.exp(-pt * 4.8)
        att = min(int(0.012 * SR), pn)
        pluck[:att] *= np.linspace(0, 1, att)
        add_sound(buf, t0, pluck.astype(np.float32), gain=0.22 if pos_in_bar % 2 == 0 else 0.16)

        # 3) Soft brushed percussion whisper on beats 1 and 3 (and gentle half-beat swing)
        if pos_in_bar in (1, 3):
            sn = int(0.14 * SR)
            st = np.linspace(0, 0.14, sn, endpoint=False)
            brush = bandpass(rng.normal(0, 1, sn), 900, 3200) * np.exp(-st * 24.0)
            add_sound(buf, t0, brush.astype(np.float32), gain=0.14)

    # Continuous warm Americana cello/harmonium chord pad (follows D -> A -> Bm -> G)
    # Keeps RMS floor velvety and consistent across inter-phrase pauses (never dipping into dead holes)
    bar_dur = beat_dur * 4.0
    pad_buf = np.zeros(n, dtype=np.float32)
    total_bars = int(duration_sec / bar_dur) + 2
    for bar_i in range(total_bars):
        bt0 = bar_i * bar_dur
        ch = chords[bar_i % len(chords)]
        bn = int((bar_dur + 0.12) * SR)
        bt = np.linspace(0, bn / SR, bn, endpoint=False)
        env = np.ones(bn, dtype=np.float32)
        fade = min(int(0.08 * SR), bn // 4)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        chord_tone = (
            np.sin(2 * np.pi * ch[1] * bt) * 0.19
            + np.sin(2 * np.pi * ch[2] * bt) * 0.14
            + np.sin(2 * np.pi * ch[3] * bt) * 0.08
        ) * (0.90 + 0.10 * np.sin(2 * np.pi * 0.55 * bt)) * env
        add_sound(pad_buf, bt0, chord_tone.astype(np.float32), gain=1.0)
    buf += pad_buf

    # Warm documentary EQ: keep cleanly beneath narration clarity band
    buf = lowpass(buf, 2200).astype(np.float32)
    peak = float(np.max(np.abs(buf)) + 1e-9)
    return buf / peak


def mix_voice_foley_and_bed(
    voice: np.ndarray,
    foley_buf: np.ndarray,
    words: list,
    bpm: float = 96.0,
    seed: int = 42,
    voice_gain: float = 0.96,
    foley_gain: float = 0.56,
    bed_under_speech: float = 0.15,
    bed_in_pauses: float = 0.44,
) -> np.ndarray:
    """
    Mixes foreground voiceover + situational foley + auto-ducked warm documentary bed
    so speech stays crystal clear while inter-phrase pauses drop only ~6-8 dB (never 25+ dB).
    """
    n = len(voice)
    dur = n / SR
    bed = generate_documentary_bed(dur, bpm=bpm, seed=seed)[:n]

    # Build fast-release broadcast voice-activity envelope from timed word boundaries
    active = np.zeros(n, dtype=np.float32)
    pad = int(0.015 * SR)
    for w in words:
        a = max(0, int(w["start"] * SR) - pad)
        b = min(n, int(w["end"] * SR) + pad)
        active[a:b] = 1.0

    # Responsive ~45ms broadcast ducking curve so even short 0.18s inter-phrase pauses fill smoothly
    env_smooth = lowpass(active, 8.5, fs=SR, order=2)
    env_smooth = np.clip(env_smooth, 0.0, 1.0)
    bed_gain_curve = bed_in_pauses * (1.0 - env_smooth) + bed_under_speech * env_smooth

    # Normalize bed RMS relative to voice RMS so target pause drop lands cleanly around 6-7 dB
    speech_idx = active > 0.5
    voice_rms = float(np.sqrt(np.mean(voice[speech_idx] ** 2) + 1e-9)) if np.any(speech_idx) else 0.15
    bed_rms = float(np.sqrt(np.mean(bed ** 2) + 1e-9))
    bed_scaled = bed * (voice_rms / max(1e-6, bed_rms)) * bed_gain_curve

    max_f = float(np.max(np.abs(foley_buf)))
    if max_f > 0.95:
        foley_buf = foley_buf / max_f * 0.92

    mixed = voice * voice_gain + foley_buf * foley_gain + bed_scaled
    peak = float(np.max(np.abs(mixed)))
    if peak > 0.96:
        mixed = mixed / peak * 0.96
    return mixed


def foley_camera_whoosh(duration=0.45, low_f=90, high_f=520):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    mid = n // 2
    swept = np.concatenate([
        bandpass(noise[:mid], low_f, (low_f + high_f) // 2),
        bandpass(noise[mid:], (low_f + high_f) // 2, high_f),
    ])
    sub_f = np.linspace(low_f * 0.8, high_f * 0.4, n)
    sub = np.sin(2 * np.pi * np.cumsum(sub_f) / SR) * 0.4
    env = np.sin(np.pi * (t / duration)) ** 1.6
    return (swept * 0.8 + sub) * env


def foley_punch_zoom(duration=0.16):
    """Crisp short kinetic pop/whoosh for mid-scene close-up snap cuts."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = bandpass(np.random.normal(0, 1, n), 300, 1800)
    sweep = np.sin(2 * np.pi * np.cumsum(np.linspace(180, 420, n)) / SR) * 0.35
    env = np.sin(np.pi * (t / duration)) ** 1.4
    return (noise * 0.55 + sweep) * env * 0.72


def foley_type_click():
    """Subtle crisp keyboard/tap tick for the animated comment panel."""
    n = int(0.045 * SR)
    t = np.linspace(0, 0.045, n, endpoint=False)
    click = bandpass(np.random.normal(0, 1, n), 1400, 5200) * np.exp(-t * 90.0)
    pop = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 65.0) * 0.35
    return (click * 0.7 + pop) * 0.65


def foley_pawn_bounce():
    n = int(0.28 * SR)
    t = np.linspace(0, 0.28, n, endpoint=False)
    f_sweep = np.linspace(190, 68, n)
    wood = np.sin(2 * np.pi * np.cumsum(f_sweep) / SR) * np.exp(-t * 18.0)
    click = bandpass(np.random.normal(0, 1, n), 400, 1800) * np.exp(-t * 35.0) * 0.4
    return wood + click


def foley_cork_pop():
    n = int(0.09 * SR)
    t = np.linspace(0, 0.09, n, endpoint=False)
    freqs = np.linspace(280, 690, n)
    tone = np.sin(2 * np.pi * np.cumsum(freqs) / SR)
    return tone * np.sin(np.pi * (t / 0.09)) * np.exp(-t * 16.0)


def foley_parchment_brush(duration=0.55):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    tex = bandpass(np.random.normal(0, 1, n), 900, 5200)
    env = np.sin(np.pi * (t / duration)) ** 1.2 * (0.7 + 0.3 * np.sin(2 * np.pi * 14 * t))
    return tex * env * 0.45


def foley_sword_unsheathe(duration=0.60):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    slide = bandpass(np.random.normal(0, 1, n), 2200, 7800) * np.exp(-t * 10.0) * 0.5
    ring = (
        np.sin(2 * np.pi * 2680 * t) * 0.45
        + np.sin(2 * np.pi * 4120 * t) * 0.30
        + np.sin(2 * np.pi * 5890 * t) * 0.20
    ) * np.exp(-t * 5.2)
    ring[: int(0.03 * SR)] *= np.linspace(0, 1, int(0.03 * SR))
    return slide + ring


def foley_sword_clash(pitch_mult=1.0):
    n = int(0.42 * SR)
    t = np.linspace(0, 0.42, n, endpoint=False)
    clang = (
        np.sin(2 * np.pi * 1420 * pitch_mult * t) * 0.5
        + np.sin(2 * np.pi * 2380 * pitch_mult * t) * 0.4
        + np.sin(2 * np.pi * 3690 * pitch_mult * t) * 0.3
        + np.sin(2 * np.pi * 5110 * pitch_mult * t) * 0.2
    ) * np.exp(-t * 8.5)
    hit = bandpass(np.random.normal(0, 1, n), 500, 5500) * np.exp(-t * 26.0) * 0.8
    thump = lowpass(np.random.normal(0, 1, n), 240) * np.exp(-t * 20.0) * 0.6
    return clang * 0.45 + hit + thump


def foley_tape_rewind(duration=0.58):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    whirr_f = np.linspace(420, 1950, n) + 180 * np.sin(2 * np.pi * 22 * t)
    whirr = np.sin(2 * np.pi * np.cumsum(whirr_f) / SR) * 0.35
    hiss = bandpass(np.random.normal(0, 1, n), 1200, 6500) * 0.45
    out = (whirr + hiss) * (np.sin(np.pi * (t / duration)) ** 0.6)
    clunk_n = int(0.04 * SR)
    out[-clunk_n:] += lowpass(np.random.normal(0, 1, clunk_n), 600) * 0.8
    return out


def foley_ocean_and_ship(duration=5.4):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    surf = bandpass(np.random.normal(0, 1, n), 180, 1600) * (0.45 + 0.45 * np.sin(2 * np.pi * 0.35 * t))
    creak = np.zeros(n)
    for c_t in [0.6, 1.8, 3.0, 4.2]:
        idx = int(c_t * SR)
        cn = int(0.35 * SR)
        if idx + cn < n:
            ct = np.linspace(0, 0.35, cn, endpoint=False)
            cf = np.linspace(310, 210, cn) + 25 * np.sin(2 * np.pi * 18 * ct)
            creak[idx : idx + cn] = np.sin(2 * np.pi * np.cumsum(cf) / SR) * np.sin(np.pi * ct / 0.35) * 0.22
    return surf * 0.25 + creak


def foley_war_horn(duration=1.3, base_f=146.83):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    horn = sum(np.sin(2 * np.pi * base_f * k * t) * amp for k, amp in [(1, 0.55), (2, 0.45), (3, 0.30), (4, 0.18), (5, 0.10)])
    return horn * (np.sin(np.pi * (t / duration)) ** 1.3 * np.exp(-t * 0.8)) * 0.45


def foley_arrow_swish():
    n = int(0.18 * SR)
    t = np.linspace(0, 0.18, n, endpoint=False)
    noise = bandpass(np.random.normal(0, 1, n), 1200, 6200)
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(1400, 480, n)) / SR) * 0.35
    return (noise * 0.7 + tone) * (np.sin(np.pi * (t / 0.18)) ** 1.5)


def foley_jaw_drop_clatter():
    n = int(0.55 * SR)
    t = np.linspace(0, 0.55, n, endpoint=False)
    drop = np.sin(2 * np.pi * np.cumsum(np.linspace(620, 145, n)) / SR) * np.exp(-t * 6.5) * 0.5
    for b_t, b_f in [(0.18, 240), (0.28, 290), (0.36, 330)]:
        idx = int(b_t * SR)
        bn = int(0.06 * SR)
        if idx + bn < n:
            bt = np.linspace(0, 0.06, bn, endpoint=False)
            drop[idx : idx + bn] += np.sin(2 * np.pi * b_f * bt) * np.exp(-bt * 45.0) * 0.45
    return drop


def foley_desert_march(duration=4.2):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    wind = bandpass(np.random.normal(0, 1, n), 250, 1400) * (0.4 + 0.35 * np.sin(2 * np.pi * 0.45 * t)) * 0.28
    boots = np.zeros(n)
    for s_i in range(int(duration / 0.42)):
        idx = int(s_i * 0.42 * SR)
        sn = int(0.11 * SR)
        if idx + sn < n:
            st = np.linspace(0, 0.11, sn, endpoint=False)
            crunch = bandpass(np.random.normal(0, 1, sn), 180, 2400) * np.exp(-st * 22.0)
            thud = np.sin(2 * np.pi * 95 * st) * np.exp(-st * 28.0) * 0.5
            boots[idx : idx + sn] += (crunch * 0.7 + thud) * 0.55
    return wind + boots


def foley_somber_bell(duration=2.8, f0=196.0):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    bell = (
        np.sin(2 * np.pi * f0 * t) * 0.6
        + np.sin(2 * np.pi * f0 * 1.18 * t) * 0.35 * np.exp(-t * 2.5)
        + np.sin(2 * np.pi * f0 * 1.50 * t) * 0.25 * np.exp(-t * 1.8)
        + np.sin(2 * np.pi * f0 * 2.00 * t) * 0.20 * np.exp(-t * 3.0)
    ) * np.exp(-t * 1.25)
    strike = lowpass(np.random.normal(0, 1, n), 500) * np.exp(-t * 30.0) * 0.4
    return (bell + strike) * 0.50


def foley_map_crack_and_tear(duration=1.1):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    rumble = lowpass(np.random.normal(0, 1, n), 180) * np.sin(np.pi * t / duration) * 0.5
    rip = bandpass(np.random.normal(0, 1, n), 700, 5200) * (0.5 + 0.5 * (np.sin(2 * np.pi * 42 * t) > 0))
    return rumble + rip * np.exp(-((t - 0.55) ** 2) / 0.08) * 0.65


def foley_celesta_chime(freq=1046.5, duration=0.45):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, endpoint=False)
    return (
        np.sin(2 * np.pi * freq * t) * 0.65
        + np.sin(2 * np.pi * freq * 2.0 * t) * 0.25 * np.exp(-t * 10.0)
        + np.sin(2 * np.pi * freq * 3.0 * t) * 0.10 * np.exp(-t * 16.0)
    ) * np.exp(-t * 5.5)
