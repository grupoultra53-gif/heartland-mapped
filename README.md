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
- `.agents/skills/historical-map-animation/` — Installed Antigravity skill (`SKILL.md`, `engine_25d.py`, `foley_mixer.py`, `style_sheet.md`, `prompt_templates.md`)
- `episodes/ep01_toledo_war/` — Episode 1 (*The Toledo War, 1835*): script, keyframes, audio, renderer, storyboard (final `.mp4` stored in Google Drive)
- `episodes/ep02_chicago_river_reversal/` — Episode 2 (*The Day Chicago Reversed a River, 1900*): script, keyframes, audio, renderer, storyboard (final `.mp4` stored in Google Drive)
- `episodes/ep03_minnesota_northwest_angle/` — Episode 3 (*Why Minnesota Has That Weird Bump on the Map — The Northwest Angle*): script, keyframes, audio, renderer, storyboard (final `.mp4` stored in Google Drive)
