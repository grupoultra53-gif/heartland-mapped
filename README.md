# Heartland Mapped — Historical Map Animation Project

Vertical `9:16` 2.5D animated historical shorts focused on the US Midwest / Heartland (`50+` audience on Facebook Reels & YouTube Shorts).

## Quick Setup on Any Computer

1. Clone the repository and open the folder as a **Project / Workspace** in Antigravity:
   ```powershell
   git clone https://github.com/grupoultra53-gif/heartland-mapped.git
   ```
2. Make sure **Python 3.12+** and **FFmpeg** are installed (`winget install Python.Python.3.12 Gyan.FFmpeg` on Windows).
3. Create the virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
4. Render Episode 1 (or any new episode):
   ```powershell
   .\.venv\Scripts\python.exe episodes\ep01_toledo_war\render_video.py
   ```

## Sync Workflow (GitHub + Google Drive)
- **GitHub (`https://github.com/grupoultra53-gif/heartland-mapped`):** syncs skills, scripts, configs, keyframes, narration `.mp3`, and storyboards across computers (`git pull` before starting, `git add` / `git commit` / `git push` when done).
- **Google Drive (`grupoultra53@gmail.com` → folder `Heartland Mapped`, ID `1ge1IlbHw1N47j0BwXcVT79lCZCbi8kXw`):** stores rendered `.mp4` videos (excluded from Git via `.gitignore`). Use the Antigravity `gdrive` plugin to upload/update episode `.mp4` exports directly to that folder.

## Folder Structure
- `.agents/skills/historical-map-animation/` — Installed Antigravity skill (`SKILL.md`, `engine_25d.py`, `foley_mixer.py`, `render_episode_v2.py`, `align_audio.py`, `audit_video.py`, `style_sheet.md`, `prompt_templates.md`)
- `episodes/ep01_toledo_war/` — Episode 1 (*The Toledo War, 1835*): script, keyframes, audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep02_chicago_river_reversal/` — Episode 2 (*The Day Chicago Reversed a River, 1900*): script, keyframes, audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep03_minnesota_northwest_angle/` — Episode 3 (*Why Minnesota Has That Weird Bump on the Map — The Northwest Angle*): script, keyframes, audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep04_honey_war/` — Episode 4 (*The Honey War, 1839 — Iowa vs. Missouri*): script, keyframes, audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep05_carter_lake/` — Episode 5 (*Carter Lake — The Iowa Town Trapped Inside Nebraska, 1877*, Fish Audio S2.1 Pro Ethan): script, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep06_kentucky_bend/` — Episode 6 (*The Kentucky Bend, 1812*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep07_missouri_bootheel/` — Episode 7 (*The Missouri Bootheel, 1821*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep08_raising_chicago/` — Episode 8 (*Raising Chicago Out of the Mud, 1856*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep09_peshtigo_fire/` — Episode 9 (*The Great Peshtigo Fire, 1871*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep10_mississippi_backwards/` — Episode 10 (*The Night the Mississippi River Flowed Backwards, 1811–1812*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep11_edmund_fitzgerald/` — Episode 11 (*The Edmund Fitzgerald & Lake Superior's Deadliest Storm, 1975*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep12_mackinac_bridge/` — Episode 12 (*How the Mackinac Bridge Ended 20-Mile Ferry Lines, 1957*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `episodes/ep13_black_sunday_1935/` — Episode 13 (*Black Sunday: The Day Daylight Vanished on the Plains, 1935*, Fish Audio S2.1 Pro Ethan): `episode_spec.json`, keyframes, aligned audio, renderer, storyboard, `POSTING_KIT.txt` (final `.mp4` stored in Google Drive)
- `scripts/ingest_archive.py`, `scripts/render_longform.py`, `scripts/audit_longform.py`, `scripts/build_thumbnails.py` — 16:9 Webdoc Long-Form Engine (`1920×1080 @ 24 FPS`, parallel scene rendering with SHA256 cache, Public Domain / CC-BY license verification, `-14 LUFS` 2-pass mastering, `.srt` export, 15-rule audit + QA contact sheets)
- `assets/maps/` — Reusable `16:9` Master Midwest Relief Map (`master_midwest_map_16x9.jpg`) and archival studio parchment backdrop (`parchment_bg_16x9.jpg`)
- `longform/lf01_midwest_border_fights/` — Longform 01 (*5 Midwest Border Fights That Almost Started Real Wars*, `10:17`, **15/15 PASS**, Drive ready for Fri 27/11/2026)
- `longform/lf02_chicago_peshtigo_1871/` — Longform 02 (*The Night Two Fires Burned the Midwest: Chicago and Peshtigo, 1871*, `8:18`, **15/15 PASS**, Drive ready for Tue 01/12/2026)
- `SERIES_ROADMAP.md` — 30-Episode Season 1 daily Shorts calendar + Tuesday/Friday `16:9` Webdoc roadmap
- `RETENTION_LOG.md` — 48h YouTube Shorts & Facebook Reels A/B performance tracker
