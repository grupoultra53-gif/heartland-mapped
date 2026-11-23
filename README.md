# Heartland Mapped — Historical Map Animation Project

Vertical `9:16` 2.5D animated historical shorts focused on the US Midwest / Heartland (`50+` audience on Facebook Reels & YouTube Shorts).

## Quick Setup on Any Computer (Personal Laptop)

1. Open this `heartland-mapped` folder as a **Project / Workspace** in Antigravity.
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

## Folder Structure
- `.agents/skills/historical-map-animation/` — Installed Antigravity skill (`SKILL.md`, `engine_25d.py`, `foley_mixer.py`, `style_sheet.md`, `prompt_templates.md`)
- `episodes/ep01_toledo_war/` — Episode 1 (*The Toledo War, 1835*): script, keyframes, audio, renderer, storyboard, and final `.mp4`
