"""
Reusable 44.1 kHz Procedural Situational Foley & Cinematic Sound Effects Library.
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
