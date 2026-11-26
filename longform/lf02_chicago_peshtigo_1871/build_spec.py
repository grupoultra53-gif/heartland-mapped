"""
Builds `longform_spec.json`, polishes `legendas.srt`, renders 2 Test & Compare thumbnails,
and exports `youtube.txt` for Longform 02:
"The Night Two Fires Burned the Midwest: Chicago and Peshtigo, 1871"
"""
import json
import re
import sys
from pathlib import Path

EP = Path(__file__).resolve().parent
ROOT = EP.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_thumbnails as bt  # noqa: E402


def polish_srt():
    srt_p = EP / "legendas.srt"
    txt = srt_p.read_text(encoding="utf-8")
    fixes = [
        ("Pesh-tih-go", "Peshtigo"),
        ("Peshtihgo", "Peshtigo"),
        ("Peshti go", "Peshtigo"),
        ("Pesh tigo", "Peshtigo"),
        ("Duh-KOH-ven", "DeKoven"),
        ("Duh-Koh-ven", "DeKoven"),
        ("DuKoven", "DeKoven"),
        ("De Koven", "DeKoven"),
        ("Man-iss-TEE", "Manistee"),
        ("Man-iss-tee", "Manistee"),
        ("Mare-ih-NET", "Marinette"),
        ("Mare-ih-net", "Marinette"),
        ("Pair-NAN", "Pernin"),
        ("Pair-nan", "Pernin"),
        ("Parnan", "Pernin"),
        ("well -known", "well-known"),
        ("clear -cutting", "clear-cutting"),
        ("low -pressure", "low-pressure"),
        ("bone -dry", "bone-dry"),
        ("multi -state", "multi-state"),
        ("brick -and-stone", "brick-and-stone"),
        ("steel -framed", "steel-framed"),
        ("cream -limestone", "cream-limestone"),
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
        for k in ("image", "image_b", "card", "graphic_type", "headline", "items", "left", "right", "parallax", "dissolve_at", "dissolve_dur", "soft_fade", "subline", "left_label", "right_label", "shots"):
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
            sc["shots"] = make_shots(dur, start_z=it.get("z0", 1.02), end_z=it.get("z1", 1.15), px0=it.get("px0", 0.0), py0=it.get("py0", 0.0), px1=it.get("px1", 0.0), py1=it.get("py1", 0.0), first_cut=it.get("first_cut"))
        elif sc["type"] == "graphic" and "shots" not in sc and dur > 7.5:
            sc["shots"] = [{"t": 0.0, "zoom": 1.0}, {"t": round(dur * 0.48, 2), "zoom": 1.02}]

        ovs = []
        for ov in it.get("overlays", []):
            o = dict(ov)
            o.setdefault("start", 0.6)
            o.setdefault("end", max(3.6, round(dur - 0.4, 2)))
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


def main():
    polish_srt()
    idx = json.loads((EP / "archive_index.json").read_text(encoding="utf-8"))
    archive_by_path = {it["local_path"]: it for it in idx["items"]}
    timings = json.loads((EP / "audio_timings.json").read_text(encoding="utf-8"))
    script = json.loads((EP / "script_longform.json").read_text(encoding="utf-8"))
    total_dur = float(timings["duration"])
    bmap = {b["id"]: b for b in timings["blocks"]}

    # Build 2 high-CTR Test & Compare thumbnails (1280x720)
    lines = [
        ("FORGOTTEN", (255, 252, 242)),
        ("1871", (255, 214, 42)),
        ("INFERNO", (255, 252, 242)),
    ]
    if (EP / "thumb_map_base.jpg").exists():
        bt.build_thumb(EP / "thumb_map_base.jpg", EP / "thumbnail_a_map.jpg", lines, badge="OCT 8, 1871")
    if (EP / "archive" / "arc_05_chicago_currier_ives.jpg").exists():
        bt.build_thumb(EP / "archive" / "arc_05_chicago_currier_ives.jpg", EP / "thumbnail_b_archive.jpg", lines, badge="OCT 8, 1871")

    scenes = []
    chapters = []
    foley_cues = []
    silence_dips = []

    b1 = bmap["01_cold_open"]
    b2 = bmap["02_promise_map"]
    b3 = bmap["03_cap1_tinderbox"]
    b4 = bmap["04_cap2_chicago_burns"]
    b5 = bmap["05_cap3_peshtigo_firestorm"]
    b6 = bmap["06_cap4_why_forgotten"]
    b7 = bmap["07_whats_left_and_outro"]

    # ---- BLOCK 01: COLD OPEN ----
    chapters.append({"start": 0.0, "title": "Cold Open: 9:00 PM in Peshtigo, Wisconsin (1871)"})
    foley_cues.append({"t": 0.5, "type": "bell", "gain": 0.45})
    foley_cues.append({"t": 18.0, "type": "fire", "gain": 0.55})

    scenes += split_segment(0.0, b1["block_end"], [
        {
            "id": "s01_cold_open_peshtigo_map", "type": "map", "image": "maps/map_04_peshtigo_firestorm.jpg",
            "weight": 1.3, "z0": 1.04, "z1": 1.18, "first_cut": 2.4,
            "overlays": [{"type": "stat", "big": "OCT 8, 1871", "label": "PESHTIGO, WISCONSIN · 9:00 PM", "pos": "top_left", "start": 0.5}],
        },
        {
            "id": "s02_cold_open_river_refuge", "type": "archive", "image": "archive/arc_01_peshtigo_river_refuge.jpg",
            "weight": 1.35, "z0": 1.00, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Refuge in the Peshtigo River", "subtitle": "1871 eyewitness engraving — Wisconsin Historical Society", "start": 0.6}],
        },
        {
            "id": "s03_cold_open_chicago_flames", "type": "archive", "image": "archive/arc_05_chicago_currier_ives.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.16, "px1": -0.04,
            "overlays": [{"type": "rodape", "title": "250 Miles South: Chicago", "subtitle": "Currier & Ives (1871) — Same night, different legacy", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- BLOCK 02: PROMISE + REGIONAL FIRE MAP ----
    foley_cues.append({"t": round(b2["speech_start"] + 0.5, 2), "type": "parchment", "gain": 0.55})
    scenes += split_segment(b1["block_end"], b3["chapter_card_start"], [
        {
            "id": "s04_promise_oleary", "type": "archive", "image": "archive/arc_10_oleary_cow.jpg",
            "weight": 1.0, "z0": 1.02, "z1": 1.14,
        },
        {
            "id": "s05_promise_lake_michigan_fires", "type": "map", "image": "maps/map_01_lake_michigan_fires.jpg",
            "weight": 1.65, "z0": 1.02, "z1": 1.16, "px0": -0.02, "px1": 0.03,
            "overlays": [
                {"type": "stat", "big": "1,200 - 2,500", "label": "ESTIMATED LIVES LOST AT PESHTIGO", "pos": "top_left", "start": 0.7, "end": 6.5},
                {"type": "rodape", "title": "Five Towns Burned on One Sunday Night", "subtitle": "Peshtigo, Chicago, Holland, Manistee & Port Huron", "start": 7.0},
            ],
        },
        {
            "id": "s06_promise_peshtigo_ruins", "type": "archive", "image": "archive/arc_02_peshtigo_ruins.jpg",
            "weight": 1.1, "z0": 1.00, "z1": 1.12,
        },
    ], archive_by_path)

    # ---- CHAPTER 1: A REGIONAL TINDERBOX ----
    chapters.append({"start": round(b3["chapter_card_start"], 2), "title": "1. A Regional Tinderbox (Summer 1871)"})
    foley_cues.append({"t": round(b3["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b3["speech_start"] + 58.0, 2), "type": "whoosh", "gain": 0.50})

    scenes.append({
        "id": "s07_ch1_card", "type": "chapter_card",
        "duration": round(b3["chapter_card_end"] - b3["chapter_card_start"], 3),
        "card": b3["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b3["chapter_card_end"], b4["chapter_card_start"], [
        {
            "id": "s08_ch1_master_midwest", "type": "map", "image": "../../assets/maps/master_midwest_map_16x9.jpg",
            "weight": 1.15, "z0": 1.08, "z1": 1.24, "px0": 0.05, "py0": -0.05, "px1": 0.12, "py1": -0.08,
            "overlays": [{"type": "stat", "big": "25% RAINFALL", "label": "SEVERE SUMMER DROUGHT OF 1871", "pos": "top_left", "start": 0.6}],
        },
        {
            "id": "s09_ch1_pine_logging", "type": "archive", "image": "archive/arc_14_logging_wisconsin.jpg",
            "weight": 1.2, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Logging Slash Piled 10 Feet Deep", "subtitle": "Dried white-pine branches carpeted northern Wisconsin", "start": 0.6}],
        },
        {
            "id": "s10_ch1_peshtigo_lumber", "type": "archive", "image": "archive/arc_03_peshtigo_lumber.jpg",
            "weight": 1.1, "z0": 1.02, "z1": 1.14,
        },
        {
            "id": "s11_ch1_chicago_wood", "type": "archive", "image": "archive/arc_06_chicago_dekoven.jpg",
            "weight": 1.15, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "A City Built of Pine", "subtitle": "Two-thirds of 1871 Chicago was wooden construction", "start": 0.6}],
        },
        {
            "id": "s12_ch1_weather_front", "type": "map", "image": "maps/map_02_weather_front.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.16, "px0": -0.04, "px1": 0.05,
            "overlays": [{"type": "rodape", "title": "Sunday Afternoon, October 8, 1871", "subtitle": "A dry Plains cold front drove gale winds across Lake Michigan", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 2: CHICAGO IN FLAMES ----
    chapters.append({"start": round(b4["chapter_card_start"], 2), "title": "2. Chicago in Flames & The O'Leary Myth"})
    foley_cues.append({"t": round(b4["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b4["speech_start"] + 16.0, 2), "type": "fire", "gain": 0.52})
    silence_dips.append((round(b4["speech_end"] - 5.2, 2), round(b4["speech_end"] - 3.6, 2)))

    scenes.append({
        "id": "s13_ch2_card", "type": "chapter_card",
        "duration": round(b4["chapter_card_end"] - b4["chapter_card_start"], 3),
        "card": b4["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b4["chapter_card_end"], b5["chapter_card_start"], [
        {
            "id": "s14_ch2_dekoven_cottage", "type": "archive", "image": "archive/arc_06_chicago_dekoven.jpg",
            "weight": 1.1, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "rodape", "title": "137 DeKoven Street (9:00 PM)", "subtitle": "Patrick & Catherine O'Leary's barn — southwest Chicago", "start": 0.5}],
        },
        {
            "id": "s15_ch2_oldmap_to_burn", "type": "oldmap_to_map",
            "image": "archive/arc_09_chicago_fire_map.jpg", "image_b": "maps/map_03_chicago_burn.jpg",
            "weight": 1.45, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "stat", "big": "3.3 SQ MI", "label": "17,000+ BUILDINGS DESTROYED", "pos": "top_left", "start": 4.2}],
        },
        {
            "id": "s16_ch2_currier_ives", "type": "archive", "image": "archive/arc_05_chicago_currier_ives.jpg",
            "weight": 1.15, "z0": 1.04, "z1": 1.18, "px0": 0.04, "px1": -0.04,
            "overlays": [{"type": "stat", "big": "100,000", "label": "RESIDENTS LEFT HOMELESS", "pos": "top_right", "start": 0.6}],
        },
        {
            "id": "s17_ch2_chicago_ruins_1871", "type": "archive", "image": "archive/arc_16_chicago_ruins_loc.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "30 Hours of Fire · ~300 Lives Lost", "subtitle": "1871 Photograph — Library of Congress", "start": 0.5}],
        },
        {
            "id": "s18_ch2_water_tower_1886", "type": "archive", "image": "archive/arc_11_water_tower_1886.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Chicago Water Tower (1869)", "subtitle": "One of the few public landmarks left standing", "start": 0.5}],
        },
        {
            "id": "s19_ch2_oleary_exonerated", "type": "archive", "image": "archive/arc_10_oleary_cow.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Exonerated in 1997", "subtitle": "Reporter Michael Ahern admitted inventing the cow story in 1893", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 3: THE PESHTIGO FIRESTORM (CLIMAX!) ----
    chapters.append({"start": round(b5["chapter_card_start"], 2), "title": "3. The Peshtigo Firestorm (America's Deadliest Fire)"})
    foley_cues.append({"t": round(b5["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b5["speech_start"] + 22.0, 2), "type": "fire", "gain": 0.58})
    foley_cues.append({"t": round(b5["speech_start"] + 46.0, 2), "type": "river", "gain": 0.48})
    silence_dips.append((round(b5["speech_end"] - 5.0, 2), round(b5["speech_end"] - 3.4, 2)))

    scenes.append({
        "id": "s20_ch3_card", "type": "chapter_card",
        "duration": round(b5["chapter_card_end"] - b5["chapter_card_start"], 3),
        "card": b5["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b5["chapter_card_end"], b6["chapter_card_start"], [
        {
            "id": "s21_ch3_peshtigo_firestorm_map", "type": "map", "image": "maps/map_04_peshtigo_firestorm.jpg",
            "weight": 1.3, "z0": 1.02, "z1": 1.18,
            "overlays": [{"type": "stat", "big": "2,000°F+", "label": "HURRICANE-FORCE FIRE TORNADOES", "pos": "top_right", "start": 0.6}],
        },
        {
            "id": "s22_ch3_father_pernin_river", "type": "archive", "image": "archive/arc_01_peshtigo_river_refuge.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.16, "px0": -0.04, "px1": 0.04,
            "overlays": [{"type": "rodape", "title": "Father Peter Pernin's Eyewitness Account", "subtitle": "Hundreds fled into the icy Peshtigo River as embers rained down", "start": 0.6}],
        },
        {
            "id": "s23_ch3_peshtigo_ruins", "type": "archive", "image": "archive/arc_02_peshtigo_ruins.jpg",
            "weight": 1.15, "z0": 1.00, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Peshtigo at Dawn — October 9, 1871", "subtitle": "Entire lumber town reduced to white ash in under an hour", "start": 0.6}],
        },
        {
            "id": "s24_ch3_scale_graphic", "type": "graphic", "graphic_type": "scale_compare",
            "weight": 1.25,
            "headline": "OCTOBER 8, 1871 — TWO TRAGEDIES COMPARED",
            "left": {"title": "GREAT CHICAGO FIRE", "value": "~300 DEAD", "subtitle": "3.3 sq mi · 100,000 homeless"},
            "right": {"title": "PESHTIGO FIRESTORM", "value": "1,200 - 2,500", "subtitle": "1.2M acres · bigger than RI"},
            "shots": [{"t": 0.0, "zoom": 1.0}, {"t": 5.2, "zoom": 1.02}, {"t": 10.5, "zoom": 1.04}],
        },
        {
            "id": "s25_ch3_michigan_fires", "type": "today", "image": "today/arc_18_manistee_harbor.jpg",
            "weight": 0.95, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Across Lake Michigan: Holland & Manistee", "subtitle": "Michigan's Thumb & shoreline burned that exact same night", "start": 0.5}],
        },
        {
            "id": "s26_ch3_holland_mi", "type": "today", "image": "today/arc_19_holland_michigan.jpg",
            "weight": 0.95, "z0": 1.02, "z1": 1.14,
        },
    ], archive_by_path)

    # ---- CHAPTER 4: SILENCE ON THE WIRE ----
    chapters.append({"start": round(b6["chapter_card_start"], 2), "title": "4. Silence on the Wire: Why History Forgot"})
    foley_cues.append({"t": round(b6["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b6["speech_start"] + 42.0, 2), "type": "chime", "gain": 0.45})

    scenes.append({
        "id": "s27_ch4_card", "type": "chapter_card",
        "duration": round(b6["chapter_card_end"] - b6["chapter_card_start"], 3),
        "card": b6["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b6["chapter_card_end"], b7["chapter_card_start"], [
        {
            "id": "s28_ch4_telegraph_map", "type": "map", "image": "maps/map_05_telegraph_lines.jpg",
            "weight": 1.4, "z0": 1.02, "z1": 1.16,
            "overlays": [{"type": "rodape", "title": "Telegraphs vs. Burned Poles", "subtitle": "Chicago wired the world; Peshtigo went silent for days", "start": 0.6}],
        },
        {
            "id": "s29_ch4_telegraph_poles", "type": "archive", "image": "archive/arc_15_telegraph_1870s.jpg",
            "weight": 1.1, "z0": 1.00, "z1": 1.12,
        },
        {
            "id": "s30_ch4_gov_fairchild", "type": "archive", "image": "archive/arc_17_lucius_fairchild.jpg",
            "weight": 1.15, "parallax": True, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Gov. Lucius Fairchild (Wisconsin)", "subtitle": "State relief had already shipped south to Chicago", "start": 0.5}],
        },
        {
            "id": "s31_ch4_chicago_barnard", "type": "archive", "image": "archive/arc_07_chicago_barnard_ruins.jpg",
            "weight": 1.15, "z0": 1.00, "z1": 1.14, "px0": -0.05, "px1": 0.05, "frame_style": "photo",
            "overlays": [{"type": "rodape", "title": "George N. Barnard — Chicago Ruins (1871)", "subtitle": "New brick codes & skyscrapers rose from the ashes", "start": 0.5}],
        },
        {
            "id": "s32_ch4_white_city_1893", "type": "archive", "image": "archive/arc_13_white_city_1893.jpg",
            "weight": 1.05, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "1893 World's Columbian Exposition", "subtitle": "Chicago became a global symbol of renewal", "start": 0.5}],
        },
    ], archive_by_path)

    # ---- CHAPTER 5: WHAT'S LEFT TODAY + END SCREEN ----
    chapters.append({"start": round(b7["chapter_card_start"], 2), "title": "5. What's Left Today: Chicago to Peshtigo"})
    foley_cues.append({"t": round(b7["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(total_dur - 20.0, 2), "type": "bell", "gain": 0.42})

    end_screen_start = round(total_dur - 19.5, 3)
    scenes.append({
        "id": "s33_ch5_card", "type": "chapter_card",
        "duration": round(b7["chapter_card_end"] - b7["chapter_card_start"], 3),
        "card": b7["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b7["chapter_card_end"], end_screen_start, [
        {
            "id": "s34_today_drive_map", "type": "map", "image": "maps/map_06_drive_today.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14,
        },
        {
            "id": "s35_today_water_tower_then_now", "type": "then_now",
            "image": "archive/arc_11_water_tower_1886.jpg", "image_b": "today/today_01_chicago_water_tower.jpg",
            "weight": 1.25, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "TODAY · Chicago Water Tower", "subtitle": "Michigan Avenue — Survivor of October 1871", "start": 0.6}],
        },
        {
            "id": "s36_today_peshtigo_museum", "type": "today", "image": "today/today_02_peshtigo_museum_ext.jpg",
            "weight": 1.2, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "TODAY · Peshtigo Fire Museum, WI", "subtitle": "Housed in the first church rebuilt after 1871", "start": 0.6}],
        },
        {
            "id": "s37_today_peshtigo_sign", "type": "today", "image": "today/today_03_peshtigo_museum_sign.jpg",
            "weight": 1.2, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Peshtigo Fire Cemetery Memorial", "subtitle": "Mass grave of 350+ unidentified victims", "start": 0.6}],
        },
    ], archive_by_path)

    scenes.append({
        "id": "s38_end_screen", "type": "end_screen",
        "duration": round(total_dur - end_screen_start, 3),
        "headline": "HEARTLAND MAPPED",
        "subline": "Did you ever learn about the Peshtigo Fire? Tell us which state you're from!",
        "left_label": "WATCH NEXT: 5 MIDWEST BORDER FIGHTS",
        "right_label": "PLAYLIST: HEARTLAND DISASTERS",
    })

    spec = {
        "episode": "lf02_chicago_peshtigo_1871",
        "title": script["title"],
        "output_mp4": "video.mp4",
        "remaster_audio": False,
        "chapters": chapters,
        "foley_cues": foley_cues,
        "silence_dips": silence_dips,
        "scenes": scenes,
    }
    (EP / "longform_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    # Export complete youtube.txt deliverable
    ch_lines = [f"{fmt_mmss(c['start'])} {c['title']}" for c in chapters]
    midroll_lines = [f"  - {fmt_mmss(c['start'])} ({c['title']})" for c in chapters[2:5]]
    src_lines = [f"- {s['label']}: {s['url']}" for s in script["research_sources"]]
    cc_credits = [f"- {info['caption']} — {info['artist']} ({info['license']}): {info['page_url']}" for info in archive_by_path.values() if "cc by" in info["license"].lower()]

    yt_txt = f"""================================================================================
HEARTLAND MAPPED — LONGFORM EPISODE 02 (16:9 WEBDOC)
KIT COMPLETO DE PUBLICACAO NO YOUTUBE STUDIO
================================================================================

DATA E HORARIO SUGERIDOS PARA PROGRAMAR:
Terca-feira, 01/12/2026 — 11:00 (Horario de Roraima / 10:00 ET / 09:00 CT)

ARQUIVOS ENTREGUES:
- video.mp4 (1920x1080 | 24 FPS | {fmt_mmss(total_dur)} | -14 LUFS | Fish Audio Ethan)
- legendas.srt (Legenda limpa em Ingles — subir em Subtitles -> English (United States))
- thumbnail_a_map.jpg (1280x720 — Variante A mapa 2.5D do Lago Michigan em chamas)
- thumbnail_b_archive.jpg (1280x720 — Variante B gravura historica Currier & Ives 1871, testar no Test & Compare!)
- fontes_imagens.txt (Registro completo de URL + licenca de 100% do arquivo)

--------------------------------------------------------------------------------
1. TITULO (COPIAR E COLAR — 65 caracteres)
--------------------------------------------------------------------------------
The Night Two Fires Burned the Midwest: Chicago and Peshtigo, 1871

(Alternativa A/B: Why History Forgot America's Deadliest Fire (Peshtigo, 1871))

--------------------------------------------------------------------------------
2. DESCRICAO DO YOUTUBE (COPIAR E COLAR)
--------------------------------------------------------------------------------
On the night of October 8, 1871, every telegraph in America flashed news of the Great Chicago Fire—yet 250 miles north in Wisconsin, an even deadlier firestorm wiped out the town of Peshtigo and burned 1.2 million acres in a single night.

Driven by months of severe drought, ten-foot piles of logging slash, and one dry southwest weather front sweeping off the Great Plains, fires erupted simultaneously across Illinois, Wisconsin, and Michigan (leveling Holland and battering Manistee and Port Huron). Here is the full story of America's deadliest wildfire—and why the telegraph wire ensured history remembered only one city.

CHAPTERS:
{chr(10).join(ch_lines)}

HISTORICAL SOURCES & ARCHIVES:
{chr(10).join(src_lines)}

IMAGE CREDITS (CREATIVE COMMONS & PUBLIC DOMAIN):
All historical engravings, maps, and photographs are Public Domain (Library of Congress, Wisconsin Historical Society, Currier & Ives, George N. Barnard) or Creative Commons licensed:
{chr(10).join(cc_credits)}

Did you ever learn about the Peshtigo Fire in school, or do you have family roots in Wisconsin, Illinois, or Michigan? Tell us which state you're watching from down in the comments!

#MidwestHistory #PeshtigoFire #GreatChicagoFire #WisconsinHistory #ChicagoHistory #AmericanHistory #HeartlandMapped #1871 #HistoryDocumentary

--------------------------------------------------------------------------------
3. COMENTARIO FIXADO (POSTAR E FIXAR NO TOPO)
--------------------------------------------------------------------------------
Did you ever learn about the 1871 Peshtigo Fire in school, or have you visited the Peshtigo Fire Museum or Chicago's Water Tower? Tell us which state you're watching from down in the comments!

--------------------------------------------------------------------------------
4. TAGS DO YOUTUBE STUDIO
--------------------------------------------------------------------------------
peshtigo fire 1871, great chicago fire 1871, october 8 1871 fires, deadliest wildfire in american history, wisconsin history, chicago history documentary, midwest history, heartland mapped, great michigan fire 1871, father peter pernin, mrs olearys cow myth, chicago water tower, peshtigo fire museum

--------------------------------------------------------------------------------
5. CONFIGURACOES DE MONETIZACAO, FUNIL & CHECKLIST (YOUTUBE STUDIO)
--------------------------------------------------------------------------------
- Publico: MARCAR SEMPRE "Nao, nao e conteudo para criancas" (Not made for kids).
- Conteudo alterado/sintetico: NAO precisa marcar (arquivo historico real + mapas ilustrados).
- Categoria: Education | Idioma: English (United States).
- Legenda .srt: subir `legendas.srt` manualmente.
- Thumbnails (Test & Compare): subir `thumbnail_a_map.jpg` vs `thumbnail_b_archive.jpg`!
- Mid-rolls manuais (nos cartoes de capitulo):
{chr(10).join(midroll_lines)}
- Playlist: criar/adicionar na playlist de longos "Heartland Disasters".
- Tela final (ultimos 20s): apontar card esquerdo para o Longo 1 ("5 Midwest Border Fights") + card direito para a playlist "Heartland Disasters".
- Funil Shorts -> Longo (definir como "Video relacionado" no YouTube Studio):
  * Short Ep. 09 (Great Peshtigo Fire — Ter 01/12) -> apontar direto para este Longo 2!
  * Short Ep. 08 (Raising Chicago — Seg 30/11)     -> tambem pode apontar para este Longo 2!
- Conferir na aba Verificacoes (Checks) do YouTube Studio se nenhuma faixa gerou claim antes da publicacao!
"""
    (EP / "youtube.txt").write_text(yt_txt, encoding="utf-8")

    t_arch = sum(s["duration"] for s in scenes if s["type"] in ("archive", "today", "then_now")) + sum(s["duration"] * 0.45 for s in scenes if s["type"] == "oldmap_to_map")
    t_map = sum(s["duration"] for s in scenes if s["type"] == "map") + sum(s["duration"] * 0.55 for s in scenes if s["type"] == "oldmap_to_map")
    t_content = sum(s["duration"] for s in scenes if s["type"] != "end_screen")
    print(f"Built Longo 2 spec: {len(scenes)} scenes, total={sum(s['duration'] for s in scenes):.2f}s (audio={total_dur:.2f}s)")
    print(f"Visual Mix preview: archive+today={100*t_arch/t_content:.1f}%, house_map={100*t_map/t_content:.1f}%")


if __name__ == "__main__":
    main()
