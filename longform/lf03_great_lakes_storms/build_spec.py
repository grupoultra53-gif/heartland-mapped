"""
Builds `longform_spec.json`, polishes `legendas.srt`, renders 2 Test & Compare thumbnails,
and exports `youtube.txt` for Longform 03:
"The Great Lakes Storms That Swallowed Ships: 1913 and the Edmund Fitzgerald"
"""
import json
import re
import sys
from pathlib import Path
from PIL import Image, ImageEnhance

EP = Path(__file__).resolve().parent
ROOT = EP.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_thumbnails as bt  # noqa: E402


def polish_srt():
    srt_p = EP / "legendas.srt"
    txt = srt_p.read_text(encoding="utf-8")
    fixes = [
        ("Reh-JYE-nah", "Regina"),
        ("Reh-jye-nah", "Regina"),
        ("Reh Jye Nah", "Regina"),
        ("Rejaina", "Regina"),
        ("TACK-uh-nite", "taconite"),
        ("Tack-uh-nite", "taconite"),
        ("tack-uh-nite", "taconite"),
        ("Taconite", "taconite"),
        ("Mc-SOR-lee", "McSorley"),
        ("McSorly", "McSorley"),
        ("McSorely", "McSorley"),
        ("CARE-uh-boo", "Caribou"),
        ("White Fish", "Whitefish"),
        ("low -pressure", "low-pressure"),
        ("hurricane -force", "hurricane-force"),
        ("ship -to-shore", "ship-to-shore"),
        ("iron -ore", "iron-ore"),
        ("cold -water", "cold-water"),
        ("load -line", "load-line"),
        ("pre -November", "pre-November"),
        ("real -time", "real-time"),
        ("two -hundred-pound", "two-hundred-pound"),
        ("brand -new", "brand-new"),
        ("moisture -rich", "moisture-rich"),
        ("still -warm", "still-warm"),
        ("heartland", "Heartland"),
    ]
    for a, b in fixes:
        txt = re.sub(re.escape(a), b, txt, flags=re.IGNORECASE)

    out_blocks = []
    for blk in txt.strip().split("\n\n"):
        lns = blk.splitlines()
        if len(lns) < 3:
            continue
        hdr, ts = lns[0], lns[1]
        body = re.sub(r"\s+", " ", " ".join(lns[2:]).strip())
        if len(body) <= 42:
            wrapped = [body]
        else:
            mid = len(body) // 2
            best = None
            for i, ch in enumerate(body):
                if ch == " " and i <= 42 and (len(body) - i - 1) <= 42:
                    if best is None or abs(i - mid) < abs(best - mid):
                        best = i
            if best is None:
                best = body.rfind(" ", 0, 42)
                if best <= 0:
                    best = 42
            wrapped = [body[:best].strip(), body[best:].strip()[:42]]
        out_blocks.append(f"{hdr}\n{ts}\n" + "\n".join(wrapped) + "\n")
    srt_p.write_text("\n".join(out_blocks), encoding="utf-8")


def make_shots(dur: float, start_z: float = 1.02, end_z: float = 1.15, px0: float = 0.0, py0: float = 0.0, px1: float = 0.0, py1: float = 0.0, first_cut: float | None = None):
    if first_cut is not None and dur > first_cut + 2.5:
        shots = [
            {"t": 0.0, "zoom": start_z + 0.14, "pan_x": px0, "pan_y": py0, "end_zoom": start_z + 0.22, "end_pan_x": px0, "end_pan_y": py0},
            {"t": round(first_cut, 2), "zoom": start_z, "pan_x": px0, "pan_y": py0, "end_zoom": end_z, "end_pan_x": px1, "end_pan_y": py1},
        ]
        rem_t = first_cut
        while dur - rem_t > 7.2:
            mid = round(rem_t + (dur - rem_t) * 0.5, 2)
            shots[-1]["end_zoom"] = round(start_z + 0.10, 3)
            shots.append({"t": mid, "zoom": round(start_z + 0.10, 3), "pan_x": px1 * 0.5, "pan_y": py1 * 0.5, "end_zoom": end_z + 0.08, "end_pan_x": px1, "end_pan_y": py1})
            rem_t = mid
        return shots
    if dur <= 7.2:
        return [{"t": 0.0, "zoom": start_z, "pan_x": px0, "pan_y": py0, "end_zoom": end_z, "end_pan_x": px1, "end_pan_y": py1}]
    n_sub = max(2, int(round(dur / 5.2)))
    step = dur / n_sub
    shots = []
    for i in range(n_sub):
        t0 = round(i * step, 2)
        if i % 2 == 0:
            z0, z1 = start_z, min(1.22, start_z + 0.12)
            ax0, ay0, ax1, ay1 = px0, py0, px1 * 0.6, py1 * 0.6
        else:
            z0, z1 = min(1.26, start_z + 0.14), min(1.36, end_z + 0.14)
            ax0, ay0, ax1, ay1 = px1 * 0.5, py1 * 0.5, px1, py1
        shots.append({"t": t0, "zoom": round(z0, 3), "pan_x": round(ax0, 3), "pan_y": round(ay0, 3), "end_zoom": round(z1, 3), "end_pan_x": round(ax1, 3), "end_pan_y": round(ay1, 3)})
    return shots


def split_segment(start: float, end: float, items: list[dict], archive_by_path: dict) -> list[dict]:
    total_w = sum(it.get("weight", 1.0) for it in items)
    span = end - start
    cur = start
    out = []
    for idx, it in enumerate(items):
        dur = (end - cur) if idx == len(items) - 1 else round(span * (it.get("weight", 1.0) / total_w), 3)
        sc = {"id": it["id"], "type": it["type"], "duration": round(dur, 3)}
        for k in ("image", "image_b", "label_a", "label_b", "intentional_callback", "card", "graphic_type", "headline", "items", "left", "right", "parallax", "dissolve_at", "dissolve_dur", "soft_fade", "subline", "left_label", "right_label", "shots"):
            if k in it:
                sc[k] = it[k]
        if sc["type"] in ("archive", "today"):
            info = archive_by_path.get(sc.get("image", ""), {})
            w, h = info.get("width", 1920), info.get("height", 1080)
            if "frame_style" in it:
                sc["frame_style"] = it["frame_style"]
            elif w >= 1500 and (w / float(max(1, h))) >= 1.38:
                sc["frame_style"] = "fullbleed"
            else:
                sc["frame_style"] = "photo"
        elif sc["type"] in ("oldmap_to_map", "then_now"):
            info_a = archive_by_path.get(sc.get("image", ""), {})
            sc["frame_style_a"] = "fullbleed" if (info_a.get("width", 0) >= 1500 and info_a.get("width", 0) / float(max(1, info_a.get("height", 1))) >= 1.35) else "photo"
            if sc["type"] == "then_now":
                info_b = archive_by_path.get(sc.get("image_b", ""), {})
                sc["frame_style_b"] = "fullbleed" if (info_b.get("width", 0) >= 1500 and info_b.get("width", 0) / float(max(1, info_b.get("height", 1))) >= 1.35) else "photo"
            sc.setdefault("dissolve_at", round(dur * 0.48, 2))
            sc.setdefault("dissolve_dur", 1.25)

        if sc["type"] not in ("chapter_card", "graphic", "end_screen"):
            sc["shots"] = make_shots(
                dur,
                start_z=it.get("z0", 1.02),
                end_z=it.get("z1", 1.15),
                px0=it.get("px0", 0.0),
                py0=it.get("py0", 0.0),
                px1=it.get("px1", 0.0),
                py1=it.get("py1", 0.0),
                first_cut=it.get("first_cut"),
            )
        elif sc["type"] == "graphic" and "shots" not in sc:
            # Ensure graphic scenes NEVER exceed 7.5s static hold
            if dur > 14.5:
                s1 = round(dur / 3.0, 2)
                s2 = round(2.0 * dur / 3.0, 2)
                sc["shots"] = [{"t": 0.0, "zoom": 1.0}, {"t": s1, "zoom": 1.02}, {"t": s2, "zoom": 1.04}]
            elif dur > 7.4:
                mid = round(dur * 0.5, 2)
                sc["shots"] = [{"t": 0.0, "zoom": 1.0}, {"t": mid, "zoom": 1.025}]

        ovs = []
        for ov in it.get("overlays", []):
            o = dict(ov)
            o.setdefault("start", 0.6)
            o.setdefault("end", max(3.8, round(dur - 0.5, 2)))
            if o["end"] > dur - 0.15:
                o["end"] = round(dur - 0.15, 2)
            if o["end"] - o["start"] >= 3.0:
                ovs.append(o)
        if sc["type"] in ("archive", "today"):
            info = archive_by_path.get(sc.get("image", ""), {})
            lic = info.get("license", "")
            if "cc by" in lic.lower():
                artist_short = info.get("artist", "Wikimedia Commons").split(",")[0][:28].strip()
                ovs.append({"type": "credit", "text": f"Photo: {artist_short} ({lic})", "start": 0.4, "end": round(dur - 0.3, 2)})
        if ovs:
            sc["overlays"] = ovs

        out.append(sc)
        cur += dur
    return out


def fmt_mmss(sec: float) -> str:
    s = int(round(sec))
    return f"{s // 60}:{s % 60:02d}"


def build_lf03_thumbnails():
    lines = [
        ("SHIPS", (255, 252, 242)),
        ("SWALLOWED", (255, 206, 46)),
        ("WHOLE", (255, 252, 242)),
    ]
    bt.build_thumb(EP / "thumb_a_base.jpg", EP / "thumbnail_a_map.jpg", lines, badge="1913 & 1975")

    # Variant B: dramatic dark-graded real archival Edmund Fitzgerald photo (shifted right for left text)
    src = Image.open(EP / "archive" / "arc_02_fitzgerald_1971.jpg").convert("RGB")
    w, h = src.size
    # Scale to 720p height and compose right-weighted on storm-slate canvas
    scale = 720.0 / float(h)
    nw = int(round(w * scale))
    resized = src.resize((nw, 720), Image.Resampling.LANCZOS)
    resized = ImageEnhance.Contrast(resized).enhance(1.22)
    resized = ImageEnhance.Color(resized).enhance(0.88)
    canvas = Image.new("RGB", (1280, 720), (14, 22, 32))
    paste_x = max(0, 1280 - nw + 60)
    canvas.paste(resized, (paste_x, 0))
    # Smoothly blend left edge into dark storm indigo
    px = canvas.load()
    fade_start = max(0, paste_x - 20)
    fade_end = min(1280, paste_x + 260)
    for x in range(fade_start, fade_end):
        t = (x - fade_start) / float(max(1, fade_end - fade_start))
        t = t * t * (3.0 - 2.0 * t)
        for y in range(720):
            r, g, b = px[x, y]
            px[x, y] = (
                int(14 * (1 - t) + r * t),
                int(22 * (1 - t) + g * t),
                int(32 * (1 - t) + b * t),
            )
    b_base = EP / "thumb_b_archive_base.jpg"
    canvas.save(b_base, quality=95)
    bt.build_thumb(b_base, EP / "thumbnail_b_archive.jpg", lines, badge="1913 & 1975")


def main():
    build_lf03_thumbnails()
    if not (EP / "audio_timings.json").exists():
        print("Thumbnails built! Waiting for Ethan audio + --audio-only to build longform_spec.json.")
        return

    polish_srt()
    idx = json.loads((EP / "archive_index.json").read_text(encoding="utf-8"))
    archive_by_path = {it["local_path"]: it for it in idx["items"]}
    timings = json.loads((EP / "audio_timings.json").read_text(encoding="utf-8"))
    script = json.loads((EP / "script_longform.json").read_text(encoding="utf-8"))
    total_dur = float(timings["duration"])
    bmap = {b["id"]: b for b in timings["blocks"]}

    scenes = []
    chapters = []
    foley_cues = []
    silence_dips = []

    # ---- BLOCK 01: COLD OPEN (0:00 -> b02) ----
    b1 = bmap["01_cold_open"]
    b2 = bmap["02_promise_map"]
    chapters.append({"start": 0.0, "title": "Cold Open: 'We Are Holding Our Own' (Nov 10, 1975)"})
    foley_cues.append({"t": 0.6, "type": "fire_crackle", "gain": 0.25})
    foley_cues.append({"t": round(b1["speech_start"] + 15.0, 2), "type": "bell", "gain": 0.48})
    silence_dips.append((round(b1["speech_end"] - 4.5, 2), round(b1["speech_end"] - 3.0, 2)))

    scenes += split_segment(0.0, b1["block_end"], [
        {
            "id": "s01_cold_open_whitefish_storm", "type": "map", "image": "maps/map_05_whitefish_final_miles.jpg",
            "weight": 1.35, "z0": 1.04, "z1": 1.18, "px0": -0.04, "px1": 0.05, "first_cut": 2.4,
            "overlays": [{"type": "stat", "big": "NOV 10, 1975", "label": "LAKE SUPERIOR · 7:10 PM", "pos": "top_left", "start": 0.5, "end": 5.2}],
        },
        {
            "id": "s02_cold_open_fitzgerald_usace", "type": "archive", "image": "archive/arc_01_edmund_fitzgerald_usace.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.14, "px0": 0.03, "px1": -0.03,
            "overlays": [{"type": "rodape", "title": "SS Edmund Fitzgerald (729 ft)", "subtitle": "29 crew lost in 530 feet of freezing water", "start": 0.6}],
        },
        {
            "id": "s03_cold_open_waves", "type": "archive", "image": "archive/arc_03_superior_waves_1.jpg",
            "weight": 1.10, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "destaque", "lines": ["\"We are holding our own.\""], "attribution": "Last radio call — 7:10 PM", "pos": "bottom", "start": 0.7}],
        },
    ], archive_by_path)

    # ---- BLOCK 02: PROMISE + GREAT LAKES STORM BELT ----
    b3 = bmap["03_cap1_november_witch"]
    foley_cues.append({"t": round(b2["speech_start"] + 0.5, 2), "type": "parchment", "gain": 0.52})
    scenes += split_segment(b1["block_end"], b3["chapter_card_start"], [
        {
            "id": "s04_promise_price_1913", "type": "archive", "image": "archive/arc_10_price_upside_down.jpg",
            "frame_style": "photo",
            "weight": 1.20, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "stat", "big": "250+ LOST", "label": "1913 WHITE HURRICANE · 12 SHIPS SUNK", "pos": "top_left", "start": 0.5}],
        },
        {
            "id": "s05_promise_storm_belt_map", "type": "map", "image": "maps/map_01_great_lakes_storm_belt.jpg",
            "weight": 1.45, "z0": 1.02, "z1": 1.16, "px0": -0.03, "px1": 0.04,
            "overlays": [{"type": "rodape", "title": "Heartland Mapped", "subtitle": "Why the Great Lakes Turn Deadly Every November", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 1: THE NOVEMBER WITCH ----
    b4 = bmap["04_cap2_white_hurricane_1913"]
    chapters.append({"start": round(b3["chapter_card_start"], 2), "title": "1. The November Witch (Why Freshwater Acts Like an Ocean)"})
    foley_cues.append({"t": round(b3["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.58})

    scenes.append({
        "id": "s06_ch1_card", "type": "chapter_card",
        "duration": round(b3["chapter_card_end"] - b3["chapter_card_start"], 3),
        "card": b3["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b3["chapter_card_end"], b4["chapter_card_start"], [
        {
            "id": "s07_ch1_waves_north_shore", "type": "archive", "image": "archive/arc_04_superior_waves_2.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.16, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "Inland Freshwater Seas", "subtitle": "Lake Superior holds 10% of the world's surface fresh water", "start": 0.6}],
        },
        {
            "id": "s08_ch1_weather_engine_map", "type": "map", "image": "maps/map_01_great_lakes_storm_belt.jpg",
            "intentional_callback": True,
            "weight": 1.40, "z0": 1.04, "z1": 1.20, "px0": 0.03, "px1": -0.03,
            "overlays": [
                {"type": "highlight_ring", "cx": 0.54, "cy": 0.52, "radius": 0.16, "color": "red", "start": 1.2, "end": 5.5},
                {"type": "rodape", "title": "The 'November Witch'", "subtitle": "Arctic cold fronts collide with warm Gulf air over warm lakes", "start": 0.8},
            ],
        },
        {
            "id": "s09_ch1_wave_physics_diagram", "type": "map", "image": "maps/map_02_wave_mechanics_diagram.jpg",
            "weight": 1.55, "z0": 1.00, "z1": 1.12, "py0": -0.03, "py1": 0.03,
            "overlays": [{"type": "stat", "big": "8 - 10 SEC", "label": "STEEP WAVE PERIOD SLAMS FREIGHTER DECKS", "pos": "top_right", "start": 0.7}],
        },
        {
            "id": "s10_ch1_ore_dock_race", "type": "archive", "image": "archive/arc_06_duluth_ore_dock.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14, "px0": -0.03, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "Duluth–Superior Iron Ore Docks", "subtitle": "Late-autumn shipping rush before winter ice closes the locks", "start": 0.6}],
        },
        {
            "id": "s11_ch1_soo_locks_1904", "type": "archive", "image": "archive/arc_05_soo_locks_1904.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Soo Locks Shipping Bottleneck (1904)", "subtitle": "Steel carriers pushed straight into November gales", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 2: THE WHITE HURRICANE (1913) ----
    b5 = bmap["05_cap3_edmund_fitzgerald_1975"]
    chapters.append({"start": round(b4["chapter_card_start"], 2), "title": "2. The White Hurricane (November 7–10, 1913)"})
    foley_cues.append({"t": round(b4["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b4["speech_start"] + 28.0, 2), "type": "whoosh", "gain": 0.45})
    silence_dips.append((round(b4["speech_end"] - 5.2, 2), round(b4["speech_end"] - 3.6, 2)))

    scenes.append({
        "id": "s12_ch2_card", "type": "chapter_card",
        "duration": round(b4["chapter_card_end"] - b4["chapter_card_start"], 3),
        "card": b4["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b4["chapter_card_end"], b5["chapter_card_start"], [
        {
            "id": "s13_ch2_1913_oldmap_to_huron", "type": "oldmap_to_map",
            "image": "archive/arc_07_1913_weather_map.jpg", "image_b": "maps/map_03_1913_white_hurricane_map.jpg",
            "weight": 1.55, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "stat", "big": "90 MPH", "label": "BLACK SUNDAY · NOV 9, 1913", "pos": "top_left", "start": 0.7}],
        },
        {
            "id": "s14_ch2_huron_winter", "type": "archive", "image": "archive/arc_12_lake_huron_winter.jpg",
            "frame_style": "photo",
            "weight": 1.15, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "35-Foot Waves & 22 Inches of Snow", "subtitle": "Blinding blizzard paralyzed Cleveland and severed telegraph lines", "start": 0.6}],
        },
        {
            "id": "s15_ch2_1913_shipwrecks_map", "type": "archive", "image": "archive/arc_08_1913_shipwrecks_map.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.16, "px0": -0.02, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "12 Ships Sunk · 19 Driven Ashore", "subtitle": "Lake Huron alone swallowed 8 freighters with zero survivors", "start": 0.6}],
        },
        {
            "id": "s16_ch2_charles_s_price_hull", "type": "archive", "image": "archive/arc_09_charles_s_price_hull.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.15, "px0": 0.03, "px1": -0.03,
            "overlays": [{"type": "rodape", "title": "SS Charles S. Price (524 ft)", "subtitle": "Modern steel ore carrier — all 28 crewmen lost", "start": 0.6}],
        },
        {
            "id": "s17_ch2_price_upside_down_pair", "type": "composite_pair",
            "image": "archive/arc_10_price_upside_down.jpg", "image_b": "archive/arc_11_lightship_82.jpg",
            "label_a": "SS Charles S. Price — Floating Upside Down", "label_b": "U.S. Lightship No. 82 — Raised After 1913",
            "weight": 1.65, "z0": 1.00, "z1": 1.08,
            "overlays": [{"type": "rodape", "title": "The 'Mystery Ship' of Lake Huron", "subtitle": "Capsized hull floated off Port Huron before sinking completely", "start": 0.6}],
        },
        {
            "id": "s18_ch2_huron_map_regina", "type": "map", "image": "maps/map_03_1913_white_hurricane_map.jpg",
            "intentional_callback": True,
            "weight": 1.35, "z0": 1.08, "z1": 1.24, "px0": 0.04, "py0": 0.08, "px1": 0.06, "py1": 0.14,
            "overlays": [{"type": "rodape", "title": "Price & Regina — Mystery Solved by Divers", "subtitle": "No collision damage: both ships foundered in the same deadly waters", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 3: THE EDMUND FITZGERALD (NOV 10, 1975) ----
    b6 = bmap["06_cap4_reforms_and_today"]
    chapters.append({"start": round(b5["chapter_card_start"], 2), "title": "3. The SS Edmund Fitzgerald (November 10, 1975)"})
    foley_cues.append({"t": round(b5["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b5["speech_start"] + 78.0, 2), "type": "bell", "gain": 0.55})
    silence_dips.append((round(b5["speech_end"] - 5.5, 2), round(b5["speech_end"] - 3.8, 2)))

    scenes.append({
        "id": "s19_ch3_card", "type": "chapter_card",
        "duration": round(b5["chapter_card_end"] - b5["chapter_card_start"], 3),
        "card": b5["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b5["chapter_card_end"], b6["chapter_card_start"], [
        {
            "id": "s20_ch3_fitzgerald_1971", "type": "archive", "image": "archive/arc_02_fitzgerald_1971.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.16, "px0": -0.03, "px1": 0.04,
            "overlays": [{"type": "rodape", "title": "SS Edmund Fitzgerald — Launched 1958", "subtitle": "729 feet long · 'Queen of the Great Lakes'", "start": 0.6}],
        },
        {
            "id": "s21_ch3_anderson_dock", "type": "archive", "image": "archive/arc_14_anderson_ore_dock.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "26,000+ Tons of Taconite Iron Ore", "subtitle": "Departed Superior, WI on Nov 9 with SS Arthur M. Anderson trailing", "start": 0.6}],
        },
        {
            "id": "s22_ch3_fitzgerald_route_map", "type": "map", "image": "maps/map_04_fitzgerald_route_1975.jpg",
            "weight": 1.55, "z0": 1.02, "z1": 1.18, "px0": -0.05, "px1": 0.06,
            "overlays": [
                {"type": "stat", "big": "70+ MPH", "label": "NORTHERN SHELTER ROUTE · NOV 10, 1975", "pos": "top_left", "start": 0.6},
                {"type": "rodape", "title": "Hugging Ontario's Shore Toward Whitefish Bay", "subtitle": "Capt. Ernest McSorley reported listing, topside damage & failed radar", "start": 1.0},
            ],
        },
        {
            "id": "s23_ch3_arthur_m_anderson", "type": "archive", "image": "archive/arc_13_arthur_m_anderson.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "rodape", "title": "SS Arthur M. Anderson", "subtitle": "Guided the blinded Fitzgerald by radar after Whitefish Point light failed", "start": 0.6}],
        },
        {
            "id": "s24_ch3_whitefish_final_miles", "type": "map", "image": "maps/map_05_whitefish_final_miles.jpg",
            "intentional_callback": True,
            "weight": 1.50, "z0": 1.04, "z1": 1.20, "px0": -0.02, "px1": 0.05,
            "overlays": [
                {"type": "highlight_ring", "cx": 0.62, "cy": 0.42, "radius": 0.09, "color": "red", "start": 1.5, "end": 6.5},
                {"type": "rodape", "title": "7:10 PM — Vanished From Radar", "subtitle": "17 miles NW of Whitefish Point · No SOS, no lifeboats launched", "start": 0.8},
            ],
        },
        {
            "id": "s25_ch3_storm_comparison_graphic", "type": "graphic", "graphic_type": "scale_compare",
            "weight": 1.25,
            "headline": "TWO NOVEMBER DISASTERS COMPARED",
            "left": {"title": "WHITE HURRICANE (1913)", "value": "250+ DEAD", "subtitle": "12 ships sunk · 90 mph winds"},
            "right": {"title": "EDMUND FITZGERALD (1975)", "value": "29 CREW LOST", "subtitle": "729 ft hull · 530 ft underwater"},
        },
        {
            "id": "s26_ch3_fitzgerald_usace_tribute", "type": "archive", "image": "archive/arc_01_edmund_fitzgerald_usace.jpg",
            "weight": 1.25, "z0": 1.04, "z1": 1.16,
            "overlays": [{"type": "rodape", "title": "Coast Guard Investigation (1977)", "subtitle": "Hatch cover flooding, shoaling & rogue waves remain debated today", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 4: WHAT CHANGED & WHAT'S LEFT TODAY ----
    chapters.append({"start": round(b6["chapter_card_start"], 2), "title": "4. 50 Years of Safety & What's Left Today"})
    foley_cues.append({"t": round(b6["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.55})
    foley_cues.append({"t": round(b6["speech_start"] + 4.5, 2), "type": "bell", "gain": 0.52})
    end_screen_start = round(total_dur - 19.5, 3)

    scenes.append({
        "id": "s27_ch4_card", "type": "chapter_card",
        "duration": round(b6["chapter_card_end"] - b6["chapter_card_start"], 3),
        "card": b6["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b6["chapter_card_end"], end_screen_start, [
        {
            "id": "s28_ch4_mariners_church", "type": "today", "image": "today/today_01_mariners_church.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Mariners' Church — Detroit, Michigan", "subtitle": "Tolled its bell 29 times on November 11, 1975", "start": 0.6}],
        },
        {
            "id": "s29_ch4_uscg_noaa_buoy", "type": "archive", "image": "archive/arc_15_uscg_noaa_buoy.jpg",
            "weight": 1.20, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Sweeping Post-1975 Coast Guard Reforms", "subtitle": "Stricter load lines, pre-November hatch checks & NOAA weather buoys", "start": 0.6}],
        },
        {
            "id": "s30_ch4_safety_pair", "type": "composite_pair",
            "image": "archive/arc_16_immersion_suit.jpg", "image_b": "archive/arc_17_uscg_noaa_buoy_2.jpg",
            "label_a": "Cold-Water Survival Suits", "label_b": "U.S. Coast Guard & NOAA Data",
            "weight": 1.25, "z0": 1.00, "z1": 1.08,
            "overlays": [{"type": "rodape", "title": "50 Years Without a Lost Freighter", "subtitle": "Zero major commercial lakers sunk since November 1975", "start": 0.6}],
        },
        {
            "id": "s31_ch4_soo_locks_today", "type": "today", "image": "today/today_06_soo_locks_modern.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "stat", "big": "0 LOST", "label": "MAJOR COMMERCIAL LAKERS SINCE 1975", "pos": "top_left", "start": 0.5}],
        },
        {
            "id": "s32_today_memorials_map", "type": "map", "image": "maps/map_06_great_lakes_memorials_today.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Three Historic Shores You Can Still Visit", "subtitle": "Whitefish Point (MI) · Split Rock (MN) · Mariners' Church (Detroit)", "start": 0.6}],
        },
        {
            "id": "s33_today_whitefish_bell_pair", "type": "composite_pair",
            "image": "today/today_03_fitzgerald_bell.jpg", "image_b": "today/today_04_shipwreck_museum.jpg",
            "label_a": "Original 200-lb Bell (1995)", "label_b": "Whitefish Point Museum, MI",
            "weight": 1.40, "z0": 1.00, "z1": 1.08,
            "overlays": [{"type": "rodape", "title": "TODAY · Great Lakes Shipwreck Museum", "subtitle": "Whitefish Point, Michigan — Original bell preserved in honor of the 29", "start": 0.6}],
        },
        {
            "id": "s34_today_split_rock", "type": "today", "image": "today/today_05_split_rock.jpg",
            "weight": 1.30, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "rodape", "title": "TODAY · Split Rock Lighthouse, Minnesota", "subtitle": "Beacon still lights every November 10 in silent tribute", "start": 0.6}],
        },
    ], archive_by_path)

    scenes.append({
        "id": "s35_end_screen", "type": "end_screen",
        "duration": round(total_dur - end_screen_start, 3),
        "headline": "HEARTLAND MAPPED",
        "subline": "Have you visited Whitefish Point or Split Rock? Tell us which state you're from!",
        "left_label": "WATCH NEXT: CHICAGO & PESHTIGO 1871",
        "right_label": "PLAYLIST: HEARTLAND DISASTERS",
    })

    spec = {
        "episode": "lf03_great_lakes_storms",
        "title": script["title"],
        "output_mp4": "video.mp4",
        "remaster_audio": False,
        "chapters": chapters,
        "foley_cues": foley_cues,
        "silence_dips": silence_dips,
        "scenes": scenes,
    }
    (EP / "longform_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    # Export complete youtube.txt deliverable (2 manual mid-rolls at Ch 3 & Ch 4!)
    ch_lines = [f"{fmt_mmss(c['start'])} {c['title']}" for c in chapters]
    midroll_lines = [f"  - {fmt_mmss(c['start'])} ({c['title']})" for c in chapters[3:5]]
    src_lines = [f"- {s['label']}: {s['url']}" for s in script["research_sources"]]
    cc_credits = [f"- {info['caption']} — {info['artist']} ({info['license']}): {info['page_url']}" for info in archive_by_path.values() if "cc by" in info["license"].lower()]

    yt_txt = f"""================================================================================
HEARTLAND MAPPED — LONGFORM EPISODE 03 (16:9 WEBDOC)
KIT COMPLETO DE PUBLICACAO NO YOUTUBE STUDIO
================================================================================

DATA E HORARIO SUGERIDOS PARA PROGRAMAR:
Sexta-feira, 04/12/2026 — 11:00 (Horario de Roraima / 10:00 ET / 09:00 CT)

PASTA COMPLETA NO GOOGLE DRIVE:
https://drive.google.com/drive/folders/1-xa4RaQONS9EzyvmWOqjyJnf6TcPopnJ
(Video MP4 direto: https://drive.google.com/file/d/1lx5iln9f8_c0Ii0KQvH4YQzrZFX9zUi-/view?usp=drivesdk)

ARQUIVOS ENTREGUES:
- video.mp4 (1920x1080 | 24 FPS | {fmt_mmss(total_dur)} | -14 LUFS | Fish Audio Ethan)
- legendas.srt (Legenda limpa em Ingles — subir em Subtitles -> English (United States))
- thumbnail_a_map.jpg (1280x720 — Variante A mapa ilustrado + vortice nos Grandes Lagos)
- thumbnail_b_archive.jpg (1280x720 — Variante B foto historica real do SS Edmund Fitzgerald, testar no Test & Compare!)
- fontes_imagens.txt & fontes_musica.txt (Registro completo de licencas — 2 trilhas novas!)

--------------------------------------------------------------------------------
1. TITULO (COPIAR E COLAR — 74 caracteres)
--------------------------------------------------------------------------------
The Great Lakes Storms That Swallowed Ships: 1913 and the Edmund Fitzgerald

(Alternativa A/B: Why the Great Lakes Swallowed Ships: 1913 & The Edmund Fitzgerald)

--------------------------------------------------------------------------------
2. DESCRICAO DO YOUTUBE (COPIAR E COLAR)
--------------------------------------------------------------------------------
On the night of November 10, 1975, seventeen miles short of shelter at Whitefish Bay, the 729-foot ore freighter SS Edmund Fitzgerald radioed one calm sentence—"We are holding our own"—before vanishing from Lake Superior without a distress call.

Yet as haunting as 1975 was, it wasn't even the deadliest November storm to sweep the Great Lakes. Sixty-two years earlier, the 1913 White Hurricane sank twelve major ships and claimed over 250 lives in a single weekend. In this documentary, we explore why inland freshwater lakes behave like ruthless oceans every autumn—and how sweeping U.S. Coast Guard safety reforms since 1975 have prevented a single major commercial Great Lakes freighter from sinking in fifty years.

CHAPTERS:
{chr(10).join(ch_lines)}

HISTORICAL SOURCES & ARCHIVES:
{chr(10).join(src_lines)}

IMAGE CREDITS (CREATIVE COMMONS & PUBLIC DOMAIN):
All historical photographs, synoptic charts, and memorial photography are Public Domain (NOAA, U.S. Army Corps of Engineers, U.S. Coast Guard, U.S. EPA) or Creative Commons licensed:
{chr(10).join(cc_credits)}

Have you ever watched a November gale roll off Lake Superior or Lake Huron—or visited Whitefish Point, Split Rock Lighthouse, or Mariners' Church in Detroit? Tell us which Great Lakes state or province you're watching from down in the comments!

#GreatLakes #EdmundFitzgerald #MidwestHistory #WhiteHurricane1913 #LakeSuperior #MichiganHistory #MinnesotaHistory #AmericanHistory #HeartlandMapped #MaritimeHistory

--------------------------------------------------------------------------------
3. COMENTARIO FIXADO (POSTAR E FIXAR NO TOPO)
--------------------------------------------------------------------------------
Have you ever stood along Lake Superior or Lake Huron during a November gale—or visited the Great Lakes Shipwreck Museum at Whitefish Point or Split Rock Lighthouse? Tell us which state or province you're watching from!

--------------------------------------------------------------------------------
4. TAGS DO YOUTUBE STUDIO
--------------------------------------------------------------------------------
edmund fitzgerald, great lakes storm of 1913, white hurricane 1913, lake superior shipwrecks, great lakes history, ss charles s price, arthur m anderson, whitefish point shipwreck museum, split rock lighthouse, mariners church detroit, gales of november, midwest history documentary, heartland mapped, michigan history, minnesota history

--------------------------------------------------------------------------------
5. CONFIGURACOES DE MONETIZACAO, FUNIL & CHECKLIST (YOUTUBE STUDIO)
--------------------------------------------------------------------------------
- Publico: MARCAR SEMPRE "Nao, nao e conteudo para criancas" (Not made for kids).
- Conteudo alterado/sintetico: NAO precisa marcar (arquivo historico real + mapas ilustrados).
- Categoria: Education | Idioma do video e legendas: English (United States).
- Legenda .srt: subir `legendas.srt` manualmente.
- Thumbnails (Test & Compare): subir `thumbnail_a_map.jpg` vs `thumbnail_b_archive.jpg`!
- Mid-rolls manuais (apenas 2, nos cartoes de capitulo >= 4 min):
{chr(10).join(midroll_lines)}
- Playlist: adicionar na playlist de longos "Heartland Disasters".
- Tela final (ultimos 20s): apontar card esquerdo para o Longo 2 ("Chicago & Peshtigo 1871") + card direito para a playlist "Heartland Disasters".
- Funil Shorts -> Longo (definir como "Video relacionado" no YouTube Studio):
  * Short Ep. 11 (Edmund Fitzgerald — Qui 03/12) -> apontar direto para este Longo 3!
  * Short Ep. 12 (Mackinac Bridge — Sex 04/12)   -> tambem pode apontar para este Longo 3!
- Conferir na aba Verificacoes (Checks) do YouTube Studio antes de programar (Avisos: —).
"""
    (EP / "youtube.txt").write_text(yt_txt, encoding="utf-8")

    t_arch = sum(s["duration"] for s in scenes if s["type"] in ("archive", "today", "then_now", "composite_pair")) + sum(s["duration"] * 0.45 for s in scenes if s["type"] == "oldmap_to_map")
    t_map = sum(s["duration"] for s in scenes if s["type"] == "map") + sum(s["duration"] * 0.55 for s in scenes if s["type"] == "oldmap_to_map")
    t_content = sum(s["duration"] for s in scenes if s["type"] != "end_screen")
    print(f"Built Longo 3 spec: {len(scenes)} scenes, total={sum(s['duration'] for s in scenes):.2f}s (audio={total_dur:.2f}s)")
    print(f"Visual Mix preview: archive+today={100*t_arch/t_content:.1f}%, house_map={100*t_map/t_content:.1f}%")
    print(f"Chapters ({len(chapters)}):")
    for cl in ch_lines:
        print(" ", cl)


if __name__ == "__main__":
    main()
