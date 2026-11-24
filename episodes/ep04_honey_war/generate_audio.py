"""
Generate documentary-style English voiceover (honey_war.mp3) and exact
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
        "text": "In 1839, Iowa and Missouri called up thousands of armed militiamen and nearly went to war... over three honey trees.",
    },
    {
        "id": "scene_02",
        "pause_after": 0.35,
        "text": "Wait... let's rewind.",
    },
    {
        "id": "scene_03",
        "pause_after": 0.20,
        "text": "In 1816, surveyors drew Missouri's northern border straight east from the rapids of the Des Moines River.",
    },
    {
        "id": "scene_04",
        "pause_after": 0.20,
        "text": "Twenty years later, Missouri claimed they'd used the wrong rapids, and pushed the border nine miles north: claiming 2,600 square miles of Iowa farmland.",
    },
    {
        "id": "scene_05",
        "pause_after": 0.22,
        "text": "When Missouri sent a sheriff to collect taxes, Iowa's governor—the very same fiery leader from Ohio's Toledo War—had him arrested on the spot.",
    },
    {
        "id": "scene_06",
        "pause_after": 0.20,
        "text": "Then came the breaking point: a Missouri farmer snuck across the line and chopped down three hollow bee trees to steal the honey.",
    },
    {
        "id": "scene_07",
        "pause_after": 0.20,
        "text": "Furious Iowans fined him a dollar fifty, newspapers dubbed it the Honey War, and both governors ordered their militias to march.",
    },
    {
        "id": "scene_08",
        "pause_after": 0.22,
        "text": "Over a thousand Iowans marched south in freezing December armed with rusty muskets, pitchforks, frying pans, and even a sausage stuffer.",
    },
    {
        "id": "scene_09",
        "pause_after": 0.20,
        "text": "Shivering in the bitter cold, both sides realized nobody wanted to die over honey, and marched right back home without firing a single shot.",
    },
    {
        "id": "scene_10",
        "pause_after": 0.22,
        "text": "Ten years later, the U.S. Supreme Court unanimously sided with Iowa, restoring the original 1816 border with permanent iron posts.",
    },
    {
        "id": "scene_11",
        "pause_after": 0.20,
        "text": "Not one drop of blood was ever spilled, making the Honey War the sweetest standoff in American history.",
    },
    {
        "id": "scene_12",
        "pause_after": 0.55,
        "text": "Zero casualties, three bee trees lost. So be honest... if your neighbor stole your honey trees, would you call out the militia too?",
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

    master_wav = EP_DIR / "honey_war.wav"
    master_mp3 = EP_DIR / "honey_war.mp3"
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
