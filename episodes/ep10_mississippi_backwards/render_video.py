"""Episode 10 renderer wrapper — calls universal render_episode_v2.py."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "historical-map-animation" / "scripts"))
from render_episode_v2 import render_episode

if __name__ == "__main__":
    render_episode(Path(__file__).resolve().parent)
