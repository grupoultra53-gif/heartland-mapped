"""
Generate documentary-style English voiceover (northwest_angle.mp3) and exact
per-scene + word-level timestamps using edge-tts + ffmpeg.
"""
import asyncio
import json
import subprocess
from pathlib import Path
import edge_tts

EP_DIR = Path(__file__).resolve().parent
SEG_DIR = EP_DIR / "audio_segments"
SEG_DIR.mkdir(parents=True, exist_ok=True)

VOICE = "en-US-ChristopherNeural"
RATE = "+6%"
PITCH = "-1Hz"

SCENES = [
    {
        "id": "scene_01",
        "pause_after": 0.25,
        "text": "Ever notice that weird little bump on top of Minnesota? You literally have to drive through Canada to reach it... thanks to one terrible map.",
    },
    {
        "id": "scene_02",
        "pause_after": 0.35,
        "text": "Wait... let's rewind.",
    },
    {
        "id": "scene_03",
        "pause_after": 0.20,
        "text": "In 1783, American and British diplomats met in Paris to draw the new border between the U.S. and Canada.",
    },
    {
        "id": "scene_04",
        "pause_after": 0.20,
        "text": "Using a faulty 1755 map, they drew the border straight west from Lake of the Woods to meet the Mississippi River.",
    },
    {
        "id": "scene_05",
        "pause_after": 0.20,
        "text": "When real surveyors hiked north, they hit two snags: the Mississippi started way south... and the lake hid fourteen thousand islands.",
    },
    {
        "id": "scene_06",
        "pause_after": 0.20,
        "text": "In 1818, both sides set the border along the 49th parallel, dropping a straight line south from the lake's northwest corner.",
    },
    {
        "id": "scene_07",
        "pause_after": 0.22,
        "text": "Problem: that corner hid inside a northern bay. Dropping the line south accidentally sliced off 123 square miles... cut off by water.",
    },
    {
        "id": "scene_08",
        "pause_after": 0.20,
        "text": "A chunk of Minnesota was stranded above Canada: reachable only by boat, plane, or a forty-mile drive through another country.",
    },
    {
        "id": "scene_09",
        "pause_after": 0.22,
        "text": "In 1997, angry over Canadian fishing rules, locals even petitioned Congress to leave the U.S. and join Canada before a deal cooled things down.",
    },
    {
        "id": "scene_10",
        "pause_after": 0.20,
        "text": "Today, about a hundred Minnesotans still live there: checking in at a lonely border kiosk, or driving right across the frozen lake in winter.",
    },
    {
        "id": "scene_11",
        "pause_after": 0.20,
        "text": "That old map blunder created the northernmost point of the lower forty-eight, and America's favorite geography quirk.",
    },
    {
        "id": "scene_12",
        "pause_after": 0.55,
        "text": "So be honest... should the U.S. and Canada finally clean up the border, or should Minnesota keep its famous bump forever?",
    },
]


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


async def generate_segment(scene_id: str, text: str, out_mp3: Path):
    communicate = edge_tts.Communicate(
        text, voice=VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary"
    )
    words = []
    with open(out_mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {
                        "text": chunk["text"],
                        "offset_sec": chunk["offset"] / 10_000_000.0,
                        "duration_sec": chunk["duration"] / 10_000_000.0,
                    }
                )
    return words


async def main():
    timeline = []
    all_words = []
    concat_parts = []
    cursor = 0.0

    for sc in SCENES:
        mp3_path = SEG_DIR / f"{sc['id']}.mp3"
        wav_path = SEG_DIR / f"{sc['id']}.wav"
        words = await generate_segment(sc["id"], sc["text"], mp3_path)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(mp3_path),
                "-af",
                "areverse,silenceremove=start_periods=1:start_threshold=-42dB,areverse",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(wav_path),
            ],
            check=True,
        )
        dur = probe_duration(wav_path)
        pause = sc["pause_after"]

        sil_path = SEG_DIR / f"{sc['id']}_sil.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                f"{pause:.3f}",
                str(sil_path),
            ],
            check=True,
        )

        scene_words = []
        for w in words:
            w_abs = {
                "text": w["text"],
                "start": round(cursor + w["offset_sec"], 3),
                "end": round(cursor + w["offset_sec"] + w["duration_sec"], 3),
            }
            scene_words.append(w_abs)
            all_words.append(w_abs)

        timeline.append(
            {
                "id": sc["id"],
                "text": sc["text"],
                "start_sec": round(cursor, 3),
                "speech_end_sec": round(cursor + dur, 3),
                "end_sec": round(cursor + dur + pause, 3),
                "words": scene_words,
            }
        )
        concat_parts.append(wav_path)
        concat_parts.append(sil_path)
        cursor += dur + pause

    concat_list = SEG_DIR / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in concat_parts:
            f.write(f"file '{p.as_posix()}'\n")

    master_wav = EP_DIR / "northwest_angle.wav"
    master_mp3 = EP_DIR / "northwest_angle.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "pcm_s16le",
            str(master_wav),
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
            str(master_wav),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(master_mp3),
        ],
        check=True,
    )

    total_dur = probe_duration(master_wav)
    out_meta = {
        "voice": VOICE,
        "total_duration_sec": round(total_dur, 3),
        "scenes": timeline,
        "words": all_words,
    }
    with open(EP_DIR / "audio_timings.json", "w", encoding="utf-8") as f:
        json.dump(out_meta, f, indent=2)

    print(f"Generated {master_mp3} ({total_dur:.2f}s) with {len(all_words)} timed words.")
    for sc in timeline:
        print(f"  {sc['id']}: {sc['start_sec']:6.2f}s -> {sc['end_sec']:6.2f}s ({sc['end_sec']-sc['start_sec']:.2f}s)")


if __name__ == "__main__":
    asyncio.run(main())
