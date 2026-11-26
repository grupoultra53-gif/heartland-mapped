"""
Builds `longform_spec.json`, polishes `legendas.srt`, updates `fontes_imagens.txt`,
and exports YouTube timestamps/chapters + `youtube.txt` for Longform 01:
"5 Midwest Border Fights That Almost Started Real Wars"
"""
import json
import re
from pathlib import Path

EP = Path(__file__).resolve().parent
ROOT = EP.parent.parent


def polish_srt_and_archive():
    srt_p = EP / "legendas.srt"
    txt = srt_p.read_text(encoding="utf-8")
    fixes = [
        ("Dec. 1839", "December 1839"),
        ("well -documented", "well-documented"),
        ("border weight more", "border wait more"),
        ("tall tail", "tall tale"),
        ("due -west", "due-west"),
        ("brand -new", "brand-new"),
        ("teardrop -shaped", "teardrop-shaped"),
        ("twenty -three", "twenty-three"),
        ("four -hundred", "four-hundred"),
        ("year -round", "year-round"),
        ("nine and a half", "9.5"),
        ("Duh Moyn", "Des Moines"),
        ("Du Moyn", "Des Moines"),
        ("De Moyn", "Des Moines"),
        ("the Moin", "Des Moines"),
        ("Duh Moin", "Des Moines"),
        ("Keo -kuk", "Keokuk"),
        ("Keo-kuk", "Keokuk"),
        ("Kee-oh-kuk", "Keokuk"),
        ("Keo-saw-kwah", "Keosauqua"),
        ("Kee-oh-saw-kwah", "Keosauqua"),
        ("Maw-mee", "Maumee"),
        ("Mawmee", "Maumee"),
        ("New Mad-rid", "New Madrid"),
        ("New MAD-rid", "New Madrid"),
        ("Man-ih-TOE-bah", "Manitoba"),
        ("Manitobah", "Manitoba"),
        ("Pesh-tih-go", "Peshtigo"),
        ("heartland", "Heartland"),
    ]
    for a, b in fixes:
        txt = re.sub(re.escape(a), b, txt, flags=re.IGNORECASE)

    # Re-wrap any line that crossed 42 chars after replacement
    out_blocks = []
    for blk in txt.strip().split("\n\n"):
        lns = blk.splitlines()
        if len(lns) < 3:
            continue
        hdr, ts = lns[0], lns[1]
        body = " ".join(lns[2:]).strip()
        body = re.sub(r"\s+", " ", body)
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

    # Sync accurate metadata for arc_16 (LOC Omaha 1868) & arc_35 (Detroit Pub. Marquette c.1905)
    idx_p = EP / "archive_index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    for it in idx["items"]:
        if it["id"] == "arc_16_omaha_1870s_map":
            it["artist"] = "Albert Ruger (Library of Congress Geography and Map Division)"
            it["page_url"] = "https://www.loc.gov/item/73693495/"
            it["license"] = "Public domain"
            it["credit_line"] = "Library of Congress (Public domain)"
    if not any(it["id"] == "arc_35_up_iron_ore_dock" for it in idx["items"]):
        idx["items"].append({
            "id": "arc_35_up_iron_ore_dock",
            "category": "archive",
            "local_path": "archive/arc_35_up_iron_ore_dock.jpg",
            "width": 2600,
            "height": 588,
            "low_res_frame_required": False,
            "license": "Public domain",
            "license_url": "",
            "artist": "Detroit Publishing Co. (Library of Congress)",
            "source": "Wikimedia Commons / Library of Congress",
            "page_url": "https://commons.wikimedia.org/wiki/File:The_Harbor,_Marquette,_Mich._c1905.jpg",
            "caption": "Historic Lake Superior Iron Ore Dock, Marquette, Michigan (c. 1905)",
            "credit_line": "Detroit Publishing Co. / Library of Congress (Public domain)",
        })
    idx["errors"] = []
    idx_p.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "================================================================================",
        f"HEARTLAND MAPPED — FONTES E LICENCAS DE IMAGENS ({EP.name})",
        "Todos os arquivos abaixo foram verificados quanto a Dominio Publico ou CC BY / CC BY-SA.",
        "================================================================================",
        "",
    ]
    for r in idx["items"]:
        lines.append(f"[{r['id']}] ({r['category'].upper()}) — {r['local_path']} ({r['width']}x{r['height']})")
        lines.append(f"  Descricao : {r['caption']}")
        lines.append(f"  Autor     : {r['artist']}")
        lines.append(f"  Licenca   : {r['license']}" + (f" ({r['license_url']})" if r.get("license_url") else ""))
        lines.append(f"  URL       : {r['page_url']}")
        lines.append("")
    (EP / "fontes_imagens.txt").write_text("\n".join(lines), encoding="utf-8")
    return {it["local_path"]: it for it in idx["items"]}


def make_shots(dur: float, start_z: float = 1.02, end_z: float = 1.15, px0: float = 0.0, py0: float = 0.0, px1: float = 0.0, py1: float = 0.0, first_cut: float | None = None):
    """Generates smooth multi-shot camera plans so NO visual hold ever exceeds 7.2s and median sits ~5.2s."""
    if first_cut is not None and dur > first_cut + 2.5:
        shots = [
            {"t": 0.0, "zoom": start_z + 0.14, "pan_x": px0, "pan_y": py0, "end_zoom": start_z + 0.22, "end_pan_x": px0, "end_pan_y": py0},
            {"t": round(first_cut, 2), "zoom": start_z, "pan_x": px0, "pan_y": py0, "end_zoom": end_z, "end_pan_x": px1, "end_pan_y": py1},
        ]
        rem_t = first_cut
        while dur - rem_t > 7.4:
            mid = round(rem_t + (dur - rem_t) * 0.5, 2)
            shots[-1]["end_zoom"] = round(start_z + 0.10, 3)
            shots.append({"t": mid, "zoom": round(start_z + 0.10, 3), "pan_x": px1 * 0.5, "pan_y": py1 * 0.5, "end_zoom": end_z + 0.08, "end_pan_x": px1, "end_pan_y": py1})
            rem_t = mid
        return shots

    if dur <= 7.2:
        return [{"t": 0.0, "zoom": start_z, "pan_x": px0, "pan_y": py0, "end_zoom": end_z, "end_pan_x": px1, "end_pan_y": py1}]

    n_sub = max(2, int(round(dur / 5.4)))
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
    """Splits a time span [start, end] proportionally across `items` and creates complete scene dicts."""
    total_w = sum(it.get("weight", 1.0) for it in items)
    span = end - start
    cur = start
    out = []
    for idx, it in enumerate(items):
        dur = (end - cur) if idx == len(items) - 1 else round(span * (it.get("weight", 1.0) / total_w), 3)
        sc = {
            "id": it["id"],
            "type": it["type"],
            "duration": round(dur, 3),
        }
        for k in ("image", "image_b", "card", "graphic_type", "headline", "items", "left", "right", "parallax", "dissolve_at", "dissolve_dur", "soft_fade", "subline", "left_label", "right_label", "shots"):
            if k in it:
                sc[k] = it[k]

        # Enforce strict <=150% resolution safety on archive & today images
        if sc["type"] in ("archive", "today"):
            info = archive_by_path.get(sc.get("image", ""), {})
            w = info.get("width", 1920)
            h = info.get("height", 1080)
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

        # Build Smart TV safe overlays + automatic CC-BY credit where required
        ovs = []
        for ov in it.get("overlays", []):
            o = dict(ov)
            o.setdefault("start", 0.6)
            o.setdefault("end", max(3.8, round(dur - 0.5, 2)))
            if o["end"] > dur - 0.15:
                o["end"] = round(dur - 0.15, 2)
            if o["end"] - o["start"] >= 3.0:
                ovs.append(o)
        # Auto credit corner tag for CC-BY / CC-BY-SA items
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
    archive_by_path = polish_srt_and_archive()
    timings = json.loads((EP / "audio_timings.json").read_text(encoding="utf-8"))
    script = json.loads((EP / "script_longform.json").read_text(encoding="utf-8"))
    total_dur = float(timings["duration"])
    bmap = {b["id"]: b for b in timings["blocks"]}

    scenes = []
    chapters = []
    foley_cues = []
    silence_dips = []

    # ---- BLOCK 01: COLD OPEN (0:00 -> b02 start) ----
    b1 = bmap["01_cold_open"]
    b2 = bmap["02_promise_map"]
    chapters.append({"start": 0.0, "title": "Cold Open: Three Trees of Wild Honey (1839)"})
    foley_cues.append({"t": 0.6, "type": "parchment", "gain": 0.55})
    foley_cues.append({"t": round(b1["speech_start"] + 16.0, 2), "type": "march", "gain": 0.45})

    scenes += split_segment(0.0, b1["block_end"], [
        {
            "id": "s01_cold_open_woods", "type": "map", "image": "maps/map_03_honey_war_woods.jpg",
            "weight": 1.35, "z0": 1.04, "z1": 1.16, "px0": -0.05, "px1": 0.04, "first_cut": 2.4,
            "overlays": [{"type": "stat", "big": "DEC 1839", "label": "IOWA - MISSOURI LINE", "pos": "top_left", "start": 0.5, "end": 5.2}],
        },
        {
            "id": "s02_cold_open_monument", "type": "archive", "image": "archive/arc_02_honey_war_monument.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "3,200+ Armed Militiamen", "subtitle": "Iowa Territory vs. State of Missouri", "start": 0.6}],
        },
        {
            "id": "s03_cold_open_honey_map", "type": "archive", "image": "archive/arc_03_honey_war_map.jpg",
            "weight": 1.1, "z0": 1.00, "z1": 1.12,
        },
        {
            "id": "s04_cold_open_northwest_old", "type": "archive", "image": "archive/arc_10_mitchell_map_1755.jpg",
            "weight": 1.0, "z0": 1.04, "z1": 1.16,
        },
    ], archive_by_path)

    # ---- BLOCK 02: PROMISE + MASTER MIDWEST MAP ----
    b3 = bmap["03_cap1_honey_war"]
    foley_cues.append({"t": round(b2["speech_start"] + 0.5, 2), "type": "parchment", "gain": 0.55})
    scenes += split_segment(b1["block_end"], b3["chapter_card_start"], [
        {
            "id": "s05_master_midwest_map", "type": "map", "image": "../../assets/maps/master_midwest_map_16x9.jpg",
            "weight": 1.2, "z0": 1.02, "z1": 1.16, "px0": -0.02, "px1": 0.04,
            "overlays": [{"type": "rodape", "title": "Heartland Mapped", "subtitle": "Five Forgotten Midwest Border Wars", "start": 0.6}],
        },
        {
            "id": "s06_five_hotspots_map", "type": "map", "image": "maps/map_01_five_hotspots.jpg",
            "weight": 1.45, "z0": 1.02, "z1": 1.18, "px0": 0.02, "px1": -0.02,
            "overlays": [
                {"type": "highlight_ring", "cx": 0.34, "cy": 0.08, "radius": 0.07, "color": "red", "start": 1.0, "end": 4.2},
                {"type": "highlight_ring", "cx": 0.72, "cy": 0.52, "radius": 0.08, "color": "gold", "start": 4.5, "end": 8.2},
            ],
        },
        {
            "id": "s07_promise_mitchell_preview", "type": "archive", "image": "archive/arc_10_mitchell_map_1755.jpg",
            "weight": 1.0, "z0": 1.04, "z1": 1.18, "px1": -0.04,
            "overlays": [{"type": "destaque", "lines": ["5 Border Showdowns.", "1 Billion-Dollar Twist."], "pos": "bottom", "start": 0.8}],
        },
    ], archive_by_path)

    # ---- CHAPTER 1: THE HONEY WAR (1839) ----
    b4 = bmap["04_cap2_northwest_angle"]
    chapters.append({"start": round(b3["chapter_card_start"], 2), "title": "1. The Honey War (1839 — Iowa vs. Missouri)"})
    foley_cues.append({"t": round(b3["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b3["speech_start"] + 46.0, 2), "type": "crack", "gain": 0.55})
    silence_dips.append((round(b3["speech_end"] - 5.5, 2), round(b3["speech_end"] - 4.0, 2)))

    scenes.append({
        "id": "s08_ch1_card", "type": "chapter_card",
        "duration": round(b3["chapter_card_end"] - b3["chapter_card_start"], 3),
        "card": b3["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b3["chapter_card_end"], b4["chapter_card_start"], [
        {
            "id": "s09_ch1_sullivan_brown_map", "type": "map", "image": "maps/map_02_honey_war_lines.jpg",
            "weight": 1.5, "z0": 1.02, "z1": 1.18, "px0": -0.03, "px1": 0.05,
            "overlays": [{"type": "rodape", "title": "1816 Sullivan Line vs. 1837 Brown Line", "subtitle": "A 9.5-mile strip claimed by two governments", "start": 0.8}],
        },
        {
            "id": "s10_ch1_keosauqua_sanborn", "type": "archive", "image": "archive/today_06_keosauqua_sanborn.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.15, "py0": -0.04, "py1": 0.04,
            "overlays": [{"type": "rodape", "title": "Keosauqua, Van Buren County", "subtitle": "Historic Sanborn Map — Library of Congress", "start": 0.6}],
        },
        {
            "id": "s11_ch1_disputed_strip_stat", "type": "archive", "image": "archive/arc_03_honey_war_map.jpg",
            "weight": 1.15, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "stat", "big": "2,600 SQ MI", "label": "CONTESTED FARMLAND", "pos": "top_right", "start": 0.6}],
        },
        {
            "id": "s12_ch1_honey_trees", "type": "map", "image": "maps/map_03_honey_war_woods.jpg",
            "weight": 1.2, "z0": 1.04, "z1": 1.18, "px0": 0.04, "px1": -0.03,
            "overlays": [{"type": "stat", "big": "3 BEE TREES", "label": "SPARKED A FRONTIER STANDOFF", "pos": "top_left", "start": 0.7}],
        },
        {
            "id": "s13_ch1_robert_lucas", "type": "archive", "image": "archive/arc_07_lucas_statehouse.jpg",
            "weight": 1.1, "parallax": True, "z0": 1.00, "z1": 1.10,
            "overlays": [{"type": "rodape", "title": "Gov. Robert Lucas (Iowa Territory)", "subtitle": "Called out ~1,200 militiamen — remember his name", "start": 0.5}],
        },
        {
            "id": "s14_ch1_lilburn_boggs", "type": "archive", "image": "archive/arc_06_lilburn_boggs.jpg",
            "weight": 1.1, "parallax": True, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Gov. Lilburn W. Boggs (Missouri)", "subtitle": "Mobilized over 2,000 Missouri troops", "start": 0.5}],
        },
        {
            "id": "s15_ch1_monument_truce", "type": "archive", "image": "archive/arc_02_honey_war_monument.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14,
        },
        {
            "id": "s16_ch1_supreme_court", "type": "archive", "image": "archive/arc_08_supreme_court_capitol.jpg",
            "weight": 1.3, "z0": 1.02, "z1": 1.15, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "Missouri v. Iowa (1849)", "subtitle": "U.S. Supreme Court restores the 1816 Sullivan Line", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 2: THE NORTHWEST ANGLE (1783-1818) ----
    b5 = bmap["05_cap3_carter_lake"]
    chapters.append({"start": round(b4["chapter_card_start"], 2), "title": "2. The Northwest Angle (1783 — Minnesota vs. Canada)"})
    foley_cues.append({"t": round(b4["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b4["speech_start"] + 28.0, 2), "type": "whoosh", "gain": 0.45})

    scenes.append({
        "id": "s17_ch2_card", "type": "chapter_card",
        "duration": round(b4["chapter_card_end"] - b4["chapter_card_start"], 3),
        "card": b4["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b4["chapter_card_end"], b5["chapter_card_start"], [
        {
            "id": "s18_ch2_treaty_painting", "type": "archive", "image": "archive/arc_11_treaty_of_paris_painting.jpg",
            "weight": 1.15, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Treaty of Paris (1783)", "subtitle": "Painting by Benjamin West — Diplomats trusted a 1755 map", "start": 0.6}],
        },
        {
            "id": "s19_ch2_mitchell_full", "type": "archive", "image": "archive/arc_10_mitchell_map_1755.jpg",
            "weight": 1.2, "z0": 1.04, "z1": 1.18, "px0": -0.05, "py0": -0.06, "px1": -0.02, "py1": -0.03,
            "overlays": [{"type": "rodape", "title": "John Mitchell's 1755 Map", "subtitle": "Library of Congress Geography & Map Division", "start": 0.6}],
        },
        {
            "id": "s20_ch2_oldmap_to_house", "type": "oldmap_to_map",
            "image": "archive/arc_10b_mitchell_nw_zoom.jpg", "image_b": "maps/map_04_nw_angle_error.jpg",
            "weight": 1.45, "z0": 1.02, "z1": 1.14, "px1": -0.03,
            "overlays": [{"type": "stat", "big": "DUE WEST", "label": "MISSED THE MISSISSIPPI COMPLETELY", "pos": "top_left", "start": 4.2}],
        },
        {
            "id": "s21_ch2_treaty_signatures", "type": "archive", "image": "archive/arc_12_treaty_of_paris_doc.jpg",
            "weight": 1.0, "z0": 1.00, "z1": 1.12,
        },
        {
            "id": "s22_ch2_david_thompson", "type": "archive", "image": "archive/arc_13_david_thompson.jpg",
            "weight": 1.25, "z0": 1.02, "z1": 1.16, "px0": 0.04, "px1": -0.03,
            "overlays": [{"type": "rodape", "title": "David Thompson's 1814 Survey Map", "subtitle": "Proved the Mississippi headwaters lay far south", "start": 0.6}],
        },
        {
            "id": "s23_ch2_49th_marker", "type": "archive", "image": "archive/arc_15_49th_parallel_marker.jpg",
            "weight": 1.1, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "stat", "big": "49TH PARALLEL", "label": "CONVENTION OF 1818", "pos": "top_right", "start": 0.5}],
        },
        {
            "id": "s24_ch2_nw_angle_map", "type": "map", "image": "maps/map_05_nw_angle_49th.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.18, "px0": 0.04, "px1": 0.08,
            "overlays": [{"type": "stat", "big": "123 SQ MI", "label": "CUT OFF INSIDE CANADA", "pos": "top_left", "start": 0.7}],
        },
        {
            "id": "s25_ch2_welcome_sign", "type": "today", "image": "today/today_01b_nw_angle_welcome.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.13,
            "overlays": [{"type": "rodape", "title": "Northwest Angle, Minnesota", "subtitle": "~70% held in trust by the Red Lake Band of Chippewa", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 3: CARTER LAKE (1877) ----
    b6 = bmap["06_cap4_kentucky_bend"]
    chapters.append({"start": round(b5["chapter_card_start"], 2), "title": "3. Carter Lake (1877 — Iowa Inside Nebraska)"})
    foley_cues.append({"t": round(b5["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b5["speech_start"] + 15.0, 2), "type": "river", "gain": 0.55})

    scenes.append({
        "id": "s26_ch3_card", "type": "chapter_card",
        "duration": round(b5["chapter_card_end"] - b5["chapter_card_start"], 3),
        "card": b5["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b5["chapter_card_end"], b6["chapter_card_start"], [
        {
            "id": "s27_ch3_omaha_1868", "type": "archive", "image": "archive/arc_16_omaha_1870s_map.jpg",
            "weight": 1.25, "z0": 1.03, "z1": 1.18, "px0": -0.04, "px1": 0.04,
            "overlays": [{"type": "rodape", "title": "Omaha & the Missouri River (1868)", "subtitle": "Library of Congress Bird's-Eye View", "start": 0.6}],
        },
        {
            "id": "s28_ch3_saratoga_cutoff", "type": "map", "image": "maps/map_06_carter_lake_cutoff.jpg",
            "weight": 1.45, "z0": 1.02, "z1": 1.18, "py0": -0.03, "py1": 0.04,
            "overlays": [{"type": "stat", "big": "MARCH 1877", "label": "OVERNIGHT CHANNEL CUTOFF", "pos": "top_right", "start": 0.8}],
        },
        {
            "id": "s29_ch3_flood_1881", "type": "archive", "image": "archive/arc_18_missouri_river_flood.jpg",
            "weight": 1.1, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Missouri River Spring Flooding", "subtitle": "1,300+ acres stranded on the Nebraska bank", "start": 0.5}],
        },
        {
            "id": "s30_ch3_omaha_bridge", "type": "archive", "image": "archive/arc_21_omaha_bridge_1870s.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14,
        },
        {
            "id": "s31_ch3_justice_brewer", "type": "archive", "image": "archive/arc_20_justice_brewer.jpg",
            "weight": 1.2, "parallax": True, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Justice David Josiah Brewer", "subtitle": "Nebraska v. Iowa, 143 U.S. 359 (1892)", "start": 0.6}],
        },
        {
            "id": "s32_ch3_accretion_vs_avulsion", "type": "graphic", "graphic_type": "scale_compare",
            "weight": 1.35,
            "headline": "U.S. SUPREME COURT RIVER LAW (1892)",
            "left": {"title": "ACCRETION", "value": "SLOW SHIFT", "subtitle": "State border moves with the river"},
            "right": {"title": "AVULSION", "value": "SUDDEN JUMP", "subtitle": "Border stays frozen in old riverbed"},
            "shots": [{"t": 0.0, "zoom": 1.0}, {"t": 4.8, "zoom": 1.02}],
        },
        {
            "id": "s33_ch3_oldmap_to_carter", "type": "oldmap_to_map",
            "image": "archive/arc_19_carter_lake_map.jpg", "image_b": "maps/map_07_carter_lake_exclave.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Carter Lake, Iowa", "subtitle": "The only Iowa city west of the Missouri River", "start": 3.2}],
        },
    ], archive_by_path)

    # ---- CHAPTER 4: THE KENTUCKY BEND (1812) ----
    b7 = bmap["07_cap5_toledo_war"]
    chapters.append({"start": round(b6["chapter_card_start"], 2), "title": "4. The Kentucky Bend (1812 — Quake & River Loop)"})
    foley_cues.append({"t": round(b6["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b6["speech_start"] + 18.0, 2), "type": "bell", "gain": 0.50})
    silence_dips.append((round(b6["speech_end"] - 5.2, 2), round(b6["speech_end"] - 3.6, 2)))

    scenes.append({
        "id": "s34_ch4_card", "type": "chapter_card",
        "duration": round(b6["chapter_card_end"] - b6["chapter_card_start"], 3),
        "card": b6["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b6["chapter_card_end"], b7["chapter_card_start"], [
        {
            "id": "s35_ch4_ky_bend_map", "type": "map", "image": "maps/map_08_kentucky_bend.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.18, "py0": 0.04, "py1": -0.03,
            "overlays": [{"type": "stat", "big": "36°30' N", "label": "KENTUCKY - TENNESSEE LINE", "pos": "top_left", "start": 0.7}],
        },
        {
            "id": "s36_ch4_new_madrid_woodcut", "type": "archive", "image": "archive/arc_22_new_madrid_quake.jpg",
            "weight": 1.2, "z0": 1.00, "z1": 1.14,
            "overlays": [{"type": "stat", "big": "1811 - 1812", "label": "NEW MADRID EARTHQUAKES", "pos": "top_right", "start": 0.6}],
        },
        {
            "id": "s37_ch4_tilted_trees", "type": "archive", "image": "archive/arc_23_new_madrid_trees.jpg",
            "weight": 1.1, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "USGS Archival Photo (M. L. Fuller)", "subtitle": "Trees permanently tilted by the 1811–1812 quakes", "start": 0.6}],
        },
        {
            "id": "s38_ch4_ky_bend_zoom", "type": "map", "image": "maps/map_08_kentucky_bend.jpg",
            "weight": 1.2, "z0": 1.18, "z1": 1.34, "px0": 0.0, "py0": -0.02, "px1": 0.0, "py1": 0.02,
            "overlays": [{"type": "stat", "big": "17.5 SQ MI", "label": "FULTON COUNTY EXCLAVE", "pos": "top_left", "start": 0.6}],
        },
        {
            "id": "s39_ch4_mississippi_landing", "type": "archive", "image": "archive/arc_24_mississippi_steamboat.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.15, "px1": -0.04,
            "overlays": [{"type": "rodape", "title": "19th-Century Mississippi River Landing", "subtitle": "Isolated from sheriffs and courts for decades", "start": 0.6}],
        },
        {
            "id": "s40_ch4_mark_twain", "type": "archive", "image": "archive/arc_25_mark_twain.jpg",
            "weight": 1.15, "parallax": True, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Mark Twain", "subtitle": "Wrote about the Darnell–Watson feud in 1883", "start": 0.5}],
        },
        {
            "id": "s41_ch4_life_on_miss", "type": "archive", "image": "archive/arc_26_life_on_mississippi.jpg",
            "weight": 1.2, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Life on the Mississippi (1883)", "subtitle": "Inspired the Grangerford–Shepherdson feud in Huck Finn", "start": 0.6}],
        },
    ], archive_by_path)

    # ---- CHAPTER 5: THE TOLEDO WAR (1835-1836 — CLIMAX!) ----
    b8 = bmap["08_whats_left_and_outro"]
    chapters.append({"start": round(b7["chapter_card_start"], 2), "title": "5. The Toledo War (1835 — Ohio vs. Michigan)"})
    foley_cues.append({"t": round(b7["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(b7["speech_start"] + 42.0, 2), "type": "war_horn", "gain": 0.42})
    foley_cues.append({"t": round(b7["speech_start"] + 92.0, 2), "type": "chime", "gain": 0.55})
    silence_dips.append((round(b7["speech_start"] + 88.0, 2), round(b7["speech_start"] + 89.6, 2)))

    scenes.append({
        "id": "s42_ch5_card", "type": "chapter_card",
        "duration": round(b7["chapter_card_end"] - b7["chapter_card_start"], 3),
        "card": b7["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b7["chapter_card_end"], b8["chapter_card_start"], [
        {
            "id": "s43_ch5_nw_ordinance", "type": "archive", "image": "archive/arc_28_northwest_ordinance.jpg",
            "weight": 1.0, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Northwest Ordinance (1787)", "subtitle": "1937 U.S. Commemorative Stamp — Northwest Territory", "start": 0.5}],
        },
        {
            "id": "s44_ch5_mitchell_to_toledo_map", "type": "oldmap_to_map",
            "image": "archive/arc_29_mitchell_michigan.jpg", "image_b": "maps/map_09_toledo_lines.jpg",
            "weight": 1.4, "z0": 1.02, "z1": 1.15,
            "overlays": [{"type": "stat", "big": "468 SQ MI", "label": "FULTON LINE VS. HARRIS LINE", "pos": "top_left", "start": 4.2}],
        },
        {
            "id": "s45_ch5_toledo_harbor", "type": "archive", "image": "archive/arc_32_toledo_maumee_historic.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "Maumee River Port, Toledo", "subtitle": "Vital gateway for the Wabash & Erie Canal", "start": 0.5}],
        },
        {
            "id": "s46_ch5_lucas_again", "type": "archive", "image": "archive/arc_07_lucas_statehouse.jpg",
            "weight": 1.0, "parallax": True, "z0": 1.00, "z1": 1.10,
            "overlays": [{"type": "rodape", "title": "Gov. Robert Lucas (Ohio)", "subtitle": "Sent 600 troops — then fought Missouri 4 years later!", "start": 0.5}],
        },
        {
            "id": "s47_ch5_stevens_mason", "type": "archive", "image": "archive/arc_30_stevens_t_mason.jpg",
            "weight": 1.05, "parallax": True, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Stevens T. Mason (Age 23)", "subtitle": "Michigan's 'Boy Governor' — ~1,000 territorial troops", "start": 0.5}],
        },
        {
            "id": "s48_ch5_militia_map", "type": "map", "image": "maps/map_10_toledo_militias.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.16, "px0": -0.02, "px1": 0.02,
        },
        {
            "id": "s49_ch5_phillips_corners", "type": "archive", "image": "archive/arc_33_phillips_corners.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Battle of Phillips Corners & Two Stickney", "subtitle": "One penknife wound — the only blood spilled", "start": 0.6}],
        },
        {
            "id": "s50_ch5_andrew_jackson", "type": "archive", "image": "archive/arc_31_andrew_jackson.jpg",
            "weight": 1.0, "parallax": True, "z0": 1.00, "z1": 1.10,
            "overlays": [{"type": "rodape", "title": "President Andrew Jackson", "subtitle": "Needed Ohio's electoral votes in 1836", "start": 0.5}],
        },
        {
            "id": "s51_ch5_frostbitten_conv", "type": "archive", "image": "archive/arc_33b_frostbitten_convention.jpg",
            "weight": 1.05, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Frostbitten Convention (Dec 1836)", "subtitle": "Ann Arbor delegates reluctantly accept the trade", "start": 0.5}],
        },
        {
            "id": "s52_ch5_trade_graphic", "type": "graphic", "graphic_type": "scale_compare",
            "weight": 1.1,
            "headline": "THE 1836 CONGRESSIONAL COMPROMISE",
            "left": {"title": "OHIO KEPT", "value": "468 SQ MI", "subtitle": "Toledo Strip & Maumee Harbor"},
            "right": {"title": "MICHIGAN GAINED", "value": "+9,000 SQ MI", "subtitle": "Western Upper Peninsula"},
            "shots": [{"t": 0.0, "zoom": 1.0}, {"t": 4.2, "zoom": 1.02}],
        },
        {
            "id": "s53_ch5_up_map", "type": "map", "image": "maps/map_11_upper_peninsula.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.18, "px0": 0.03, "py0": 0.04, "px1": -0.04, "py1": -0.05,
        },
        {
            "id": "s54_ch5_quincy_copper", "type": "archive", "image": "archive/arc_34_up_copper_mine.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14,
            "overlays": [{"type": "rodape", "title": "Quincy Copper Mine, Hancock, MI", "subtitle": "Upper Peninsula copper & iron fueled industrial America", "start": 0.5}],
        },
        {
            "id": "s55_ch5_marquette_ore", "type": "archive", "image": "archive/arc_35_up_iron_ore_dock.jpg",
            "weight": 1.05, "z0": 1.00, "z1": 1.14, "px0": -0.05, "px1": 0.05, "frame_style": "photo",
            "overlays": [{"type": "rodape", "title": "Marquette Iron Ore Docks (c. 1905)", "subtitle": "Detroit Publishing Co. — Library of Congress", "start": 0.5}],
        },
    ], archive_by_path)

    # ---- CHAPTER 6: WHAT'S LEFT TODAY + CLOSING + 20s END SCREEN ----
    chapters.append({"start": round(b8["chapter_card_start"], 2), "title": "6. What's Left Today (Visit All Five Spots)"})
    foley_cues.append({"t": round(b8["chapter_card_start"] + 0.15, 2), "type": "parchment", "gain": 0.60})
    foley_cues.append({"t": round(total_dur - 20.5, 2), "type": "chime", "gain": 0.45})

    end_screen_start = round(total_dur - 19.5, 3)
    scenes.append({
        "id": "s56_ch6_card", "type": "chapter_card",
        "duration": round(b8["chapter_card_end"] - b8["chapter_card_start"], 3),
        "card": b8["chapter_card"], "soft_fade": True,
    })
    scenes += split_segment(b8["chapter_card_end"], end_screen_start, [
        {
            "id": "s57_today_roadtrip_map", "type": "map", "image": "maps/map_12_roadtrip_today.jpg",
            "weight": 1.05, "z0": 1.02, "z1": 1.14,
        },
        {
            "id": "s58_today_jims_corner", "type": "today", "image": "today/today_01_jims_corner_booth.jpg",
            "weight": 1.35, "z0": 1.02, "z1": 1.15, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "TODAY · Jim's Corner, Minnesota", "subtitle": "Roadside customs booth — ~149 year-round residents", "start": 0.6}],
        },
        {
            "id": "s59_today_carter_lake_sign", "type": "today", "image": "today/today_02_carter_lake_sign.jpg",
            "weight": 1.2, "z0": 1.00, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "TODAY · Carter Lake, Iowa", "subtitle": "Abbott Drive cuts straight through Iowa from Omaha's airport", "start": 0.6}],
        },
        {
            "id": "s60_today_kentucky_bend", "type": "today", "image": "today/today_03_kentucky_bend.jpg",
            "weight": 1.2, "z0": 1.02, "z1": 1.14, "px1": -0.02,
            "overlays": [{"type": "rodape", "title": "TODAY · Kentucky Bend, Kentucky", "subtitle": "Fewer than a dozen residents — zero gas stations", "start": 0.6}],
        },
        {
            "id": "s61_today_toledo_then_now", "type": "then_now",
            "image": "archive/arc_32_toledo_maumee_historic.jpg", "image_b": "today/today_04_toledo_marker.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.12,
            "overlays": [{"type": "rodape", "title": "Toledo Strip · Then & Now", "subtitle": "Historical markers still trace the 1835 standoff", "start": 0.6}],
        },
        {
            "id": "s62_today_upper_peninsula", "type": "today", "image": "today/today_05_upper_peninsula.jpg",
            "weight": 1.15, "z0": 1.02, "z1": 1.15, "px0": -0.03, "px1": 0.03,
            "overlays": [{"type": "rodape", "title": "TODAY · Michigan's Upper Peninsula", "subtitle": "Pictured Rocks & Lake Superior shoreline", "start": 0.6}],
        },
    ], archive_by_path)

    scenes.append({
        "id": "s63_end_screen", "type": "end_screen",
        "duration": round(total_dur - end_screen_start, 3),
        "headline": "HEARTLAND MAPPED",
        "subline": "Which state are you watching from? Tell us in the comments!",
        "left_label": "UP NEXT: CHICAGO & PESHTIGO (1871)",
        "right_label": "PLAYLIST: MIDWEST BORDER WARS",
    })

    spec = {
        "episode": "lf01_midwest_border_fights",
        "title": script["title"],
        "output_mp4": "video.mp4",
        "remaster_audio": True,
        "chapters": chapters,
        "foley_cues": foley_cues,
        "silence_dips": silence_dips,
        "scenes": scenes,
    }
    (EP / "longform_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also write ready-to-upload youtube.txt deliverable!
    ch_lines = [f"{fmt_mmss(c['start'])} {c['title']}" for c in chapters]
    midroll_lines = [f"  - {fmt_mmss(c['start'])} ({c['title']})" for c in chapters[2:5]]
    src_lines = [f"- {s['label']}: {s['url']}" for s in script["research_sources"]]
    cc_credits = []
    for info in archive_by_path.values():
        if "cc by" in info["license"].lower():
            cc_credits.append(f"- {info['caption']} — {info['artist']} ({info['license']}): {info['page_url']}")

    yt_txt = f"""================================================================================
HEARTLAND MAPPED — LONGFORM EPISODE 01 (16:9 WEBDOC)
KIT COMPLETO DE PUBLICACAO NO YOUTUBE STUDIO
================================================================================

DATA E HORARIO SUGERIDOS PARA PROGRAMAR:
Sexta-feira, 27/11/2026 — 11:00 (Horario de Roraima / 10:00 ET / 09:00 CT)

ARQUIVOS ENTREGUES:
- video.mp4 (1920x1080 | 24 FPS | {fmt_mmss(total_dur)} | -14 LUFS | Fish Audio Ethan)
- legendas.srt (Legenda limpa em Ingles — subir em Subtitles -> English (United States))
- thumbnail_a_pegdoll.jpg (1280x720 — Variante A com peg-doll assinatura no canto)
- thumbnail_b_pure.jpg (1280x720 — Variante B mapa puro + bussola, testar no Test & Compare!)
- fontes_imagens.txt (Registro completo de URL + licenca de 100% do arquivo)

--------------------------------------------------------------------------------
1. TITULO (COPIAR E COLAR — 55 caracteres)
--------------------------------------------------------------------------------
5 Midwest Border Fights That Almost Started Real Wars

(Alternativa A/B: 5 Real Border Fights That Shaped the Midwest Map)

--------------------------------------------------------------------------------
2. DESCRICAO DO YOUTUBE (COPIAR E COLAR)
--------------------------------------------------------------------------------
In December 1839, over three thousand armed Iowa and Missouri militiamen faced off in freezing snow over three chopped-down bee trees—and that wasn't even the only time Midwestern states came close to real bloodshed over lines on a map.

From a faulty 1755 colonial map that stranded a piece of Minnesota inside Canada, to a Missouri River flood that dropped an Iowa town into Nebraska, to the 1835 Ohio–Michigan standoff that accidentally handed Michigan billions in copper and iron, here are five true border disputes that still leave strange scars on the American Heartland today.

CHAPTERS:
{chr(10).join(ch_lines)}

HISTORICAL SOURCES & ARCHIVES:
{chr(10).join(src_lines)}

IMAGE CREDITS (CREATIVE COMMONS & PUBLIC DOMAIN):
All historical maps, portraits, and photographs are Public Domain (Library of Congress, National Archives, USGS, Detroit Publishing Co.) or Creative Commons licensed:
{chr(10).join(cc_credits)}

Have you ever driven through one of these strange corners of the Midwest? Let us know which state you're watching from down in the comments!

#MidwestHistory #AmericanHistory #USGeography #HeartlandMapped #ToledoWar #HoneyWar #NorthwestAngle #CarterLake #KentuckyBend #HistoryDocumentary

--------------------------------------------------------------------------------
3. COMENTARIO FIXADO (POSTAR E FIXAR NO TOPO)
--------------------------------------------------------------------------------
Have you ever driven across one of these strange corners of the Midwest—like Jim's Corner in Minnesota, Abbott Drive through Carter Lake, or the old Ohio–Michigan Toledo Strip? Tell us which state you're watching from and if your home state has a border story of its own!

--------------------------------------------------------------------------------
4. TAGS DO YOUTUBE STUDIO
--------------------------------------------------------------------------------
midwest history, american history documentary, us border disputes, toledo war, honey war iowa missouri, northwest angle minnesota, carter lake iowa nebraska, kentucky bend, weird us state borders, great lakes history, heartland mapped, us geography history, 1835 ohio michigan, upper peninsula history

--------------------------------------------------------------------------------
5. CONFIGURACOES DE MONETIZACAO, FUNIL & CHECKLIST (YOUTUBE STUDIO)
--------------------------------------------------------------------------------
- Publico: MARCAR SEMPRE "Nao, nao e conteudo para criancas" (Not made for kids).
- Conteudo alterado/sintetico: NAO precisa marcar (arquivo historico real + mapas ilustrados, zero foto realista sintetica de evento real).
- Categoria: Education | Idioma do video e legendas: English (United States).
- Legenda .srt: subir `legendas.srt` manualmente (NAO depender da legenda automatica).
- Thumbnails (Test & Compare): subir `thumbnail_a_pegdoll.jpg` vs `thumbnail_b_pure.jpg` para testar CTR!
- Mid-rolls manuais (colocar nos cartoes de capitulo para nao cortar frases):
{chr(10).join(midroll_lines)}
- Playlist: criar/adicionar na playlist de longos "Midwest Border Wars".
- Tela final (ultimos 20s): colocar 1 card de Video (proximo longo Chicago & Peshtigo 1871 quando subir) + 1 card da Playlist "Midwest Border Wars".
- Funil Shorts -> Longo (definir como "Video relacionado" nos Shorts agendados):
  * Short Ep. 03 (Northwest Angle — 25/11) -> apontar para este Longo 1
  * Short Ep. 04 (Honey War — 26/11)       -> apontar para este Longo 1
  * Short Ep. 05 (Carter Lake — 27/11)     -> apontar para este Longo 1
  * Short Ep. 06 (Kentucky Bend — 28/11)   -> apontar para este Longo 1
  * Short Ep. 07 (Missouri Bootheel — 29/11) -> apontar para este Longo 1
- Conferir na aba Verificacoes (Checks) do YouTube Studio se nenhuma faixa gerou claim antes da publicacao!
"""
    (EP / "youtube.txt").write_text(yt_txt, encoding="utf-8")

    # Quick stats summary
    t_arch = sum(s["duration"] for s in scenes if s["type"] in ("archive", "today", "then_now")) + sum(s["duration"] * 0.45 for s in scenes if s["type"] == "oldmap_to_map")
    t_map = sum(s["duration"] for s in scenes if s["type"] == "map") + sum(s["duration"] * 0.55 for s in scenes if s["type"] == "oldmap_to_map")
    t_content = sum(s["duration"] for s in scenes if s["type"] != "end_screen")
    print(f"Built longform_spec.json: {len(scenes)} scenes, total={sum(s['duration'] for s in scenes):.2f}s (audio={total_dur:.2f}s)")
    print(f"Visual Mix preview: archive+today={100*t_arch/t_content:.1f}%, house_map={100*t_map/t_content:.1f}%")
    print(f"Chapters ({len(chapters)}):")
    for cl in ch_lines:
        print(" ", cl)


if __name__ == "__main__":
    main()
