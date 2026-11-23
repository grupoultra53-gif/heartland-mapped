"""
Generate documentary-style English voiceover (chicago_river.mp3) and exact
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
        "text": "In 1900, Chicago pulled off a jaw-dropping engineering stunt: they forced an entire river to flow backwards... straight toward St. Louis.",
    },
    {
        "id": "scene_02",
        "pause_after": 0.35,
        "text": "Wait... let's rewind.",
    },
    {
        "id": "scene_03",
        "pause_after": 0.20,
        "text": "By the 1880s, booming Chicago dumped its waste into the Chicago River... which flowed straight into Lake Michigan.",
    },
    {
        "id": "scene_04",
        "pause_after": 0.22,
        "text": "The problem? Lake Michigan was Chicago's drinking water. After a massive 1885 storm, deadly disease swept the city.",
    },
    {
        "id": "scene_05",
        "pause_after": 0.20,
        "text": "So engineers hatched a wild plan: dig a 28-mile canal deep enough to reverse gravity and drain the lake south.",
    },
    {
        "id": "scene_06",
        "pause_after": 0.20,
        "text": "For eight years, crews blasted through solid limestone, inventing excavation methods later used on the Panama Canal.",
    },
    {
        "id": "scene_07",
        "pause_after": 0.20,
        "text": "Downriver in Missouri, St. Louis realized Chicago's waste was heading straight for them, and raced to court to stop it.",
    },
    {
        "id": "scene_08",
        "pause_after": 0.24,
        "text": "Chicago didn't wait. Before dawn on January 2nd, 1900, officials quietly snuck out in the freezing dark and blasted open the final dam.",
    },
    {
        "id": "scene_09",
        "pause_after": 0.22,
        "text": "Lake Michigan rushed inland, and for the first time ever, the Chicago River flowed backwards.",
    },
    {
        "id": "scene_10",
        "pause_after": 0.22,
        "text": "Missouri sued Illinois all the way to the Supreme Court... and lost. The justices ruled St. Louis couldn't prove Chicago caused its illness.",
    },
    {
        "id": "scene_11",
        "pause_after": 0.22,
        "text": "Today, the river still flows backwards: hailed as an engineering wonder, and dyed bright green every St. Patrick's Day.",
    },
    {
        "id": "scene_12",
        "pause_after": 0.55,
        "text": "It saved Chicago and fueled a legendary Midwest rivalry. So be honest... pure engineering genius, or the dirtiest trick ever played on St. Louis?",
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

        # Convert segment to 44.1kHz mono WAV and trim only trailing silence
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

    master_wav = EP_DIR / "chicago_river.wav"
    master_mp3 = EP_DIR / "chicago_river.mp3"
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
