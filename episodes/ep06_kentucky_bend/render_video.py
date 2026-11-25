"""Episode 06: The Kentucky Bend (1812) — Wrapper for Universal v2 Renderer."""
import sys
from pathlib import Path

EP_DIR = Path(__file__).resolve().parent
SKILL_SCRIPTS = EP_DIR.parent.parent / ".agents" / "skills" / "historical-map-animation" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import render_episode_v2

if __name__ == "__main__":
    render_episode_v2.render_episode(EP_DIR)
