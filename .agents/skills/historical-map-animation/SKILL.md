---
name: historical-map-animation
description: Create vertical 9:16 2.5D historical map animation videos and storyboards with chibi peg-doll characters, 3D relief maps, dynamic camera movements, independent character motion, overhead thought callouts, and situational foley sound effects. Use whenever the user provides a historical topic, title, script, or voiceover audio and asks to generate an animated history short or map animation video.
allowed-tools: image_gen default_api google
---
# Historical Map Animation

Create engaging vertical (`9:16`, `720x1280`, `30 FPS`) 2.5D animated history shorts featuring cute 2D chibi peg-doll characters over 3D shaded topographic relief maps, complete with independent sprite motion, 2.5D camera movements, overhead head callouts, and situational foley sound design.

## When to Use

- The user provides a voiceover audio file, script, or historical title and wants an animated history video in the chibi map animation style.
- The user references the Historical Map Animation style (3D parchment relief maps, flat colored territory overlays, legless pawn-shaped chibi characters, or *OverSimplified*-style visual gags).
- The user wants a synchronized vertical `.mp4` animation and production storyboard generated from narration audio.

## Bundled Resources

- `references/style_sheet.md` - Complete visual style guide, color hex palette, Dual Environment Modes (Mode A 3D Relief Map vs. Mode B 2.5D Ground Diorama), and chibi peg-doll anatomy rules.
- `references/prompt_templates.md` - Master image generation prompt templates for Mode A and Mode B scenes plus storyboard layout templates.
- `scripts/engine_25d.py` - Reusable 30 FPS 2.5D multi-layer compositor with OpenCV Telea background map inpainting (`extract_sprite_and_inpaint_bg`), independent sprite motion (`paste_moving_sprite`), overhead head callouts (`draw_overhead_message`), and virtual 2.5D camera with whip-pan motion blur (`apply_25d_camera`).
- `scripts/foley_mixer.py` - Reusable 44.1 kHz procedural foley and cinematic sound effects library (`foley_camera_whoosh`, `foley_pawn_bounce`, `foley_cork_pop`, `foley_parchment_brush`, `foley_sword_unsheathe`, `foley_sword_clash`, `foley_tape_rewind`, `foley_ocean_and_ship`, `foley_war_horn`, `foley_arrow_swish`, `foley_jaw_drop_clatter`, `foley_river_and_cheer`, `foley_desert_march`, `foley_coins_and_checkmarks`, `foley_somber_bell`, `foley_goblet_spill`, `foley_map_crack_and_tear`, `foley_celesta_chime`).
- `assets/scene_config_example.json` - Example scene timeline schema mapping audio timestamps to camera trajectories, sprite rigs, overhead head messages, and situational foley cues.

## Workflow Steps

### Step 1: Analyze Input Audio or Script and Plan 4-6 Second Scene Pacing

1. Measure the exact voiceover duration with `ffprobe` (or write a 60-90s script if only a title is provided).
2. Break the narration into 10-14 visual scenes so a new visual cut or camera movement occurs every 4 to 6 seconds.
3. Open with a 6-10 second Cold Open Hook showing the wildest twist, followed by a VHS Rewind transition (`◀◀◀` + scanlines) into the chronological starting year card.
4. Consult `references/style_sheet.md` and `references/prompt_templates.md` to design ~85% Mode A (Top-Down 3D Relief Map) scenes and ~15% Mode B (Ground-Level 2.5D Cutout Diorama) action scenes.

### Step 2: Generate Consistent 9:16 Keyframe Visuals

1. Generate all 10-14 vertical `9:16` scene keyframes using the templates in `references/prompt_templates.md`.
2. Ensure every character follows the Chibi Peg-Doll specification (legless pawn base, 1:2 head-to-body ratio, two black dot eyes, no nose, simple line mouth, thin black stick arms with white-gloved hands).
3. Exclude bottom subtitle text from the base keyframe images so lower-third captions and overhead head callouts can be animated cleanly by the compositor.

### Step 3: Rig Independent 2.5D Moving Sprites and Virtual Camera

Import or adapt `scripts/engine_25d.py` to render the video at `720x1280` and `30 FPS`:

1. Call `extract_sprite_and_inpaint_bg` on key characters, ships, thought clouds, and props so the background map is cleanly filled behind them via `cv2.inpaint(..., cv2.INPAINT_TELEA)`.
2. Animate the extracted sprites independently over the background using `paste_moving_sprite`:
   - Spring-bounce pop-ins (`0.0 -> 1.15 -> 1.0`) when characters, city icons, gold piles, or signs appear.
   - Physical travel across the map (ships sailing across water with animated white wake arcs, attackers lunging forward while defenders recoil and shudder, multi-plane parallax desert marches with rising dust puffs, and generals pulling outward in opposite directions).
3. Use `draw_overhead_message` to pop compact 2-4 word thought clouds or badges above characters' heads where needed. Exclude mouth-flapping lip-sync and long dialogue boxes.
4. Use `apply_25d_camera` to animate cubic smoothstep zoom/pan trajectories, subtle perspective tilt, battle camera shake, and whip-pan directional motion blur on scene cuts.

### Step 4: Synthesize Situational Foley Sound Effects

Import or adapt `scripts/foley_mixer.py` to mix the voiceover (`96%` gain) with 100% scene-specific foley (`72%` gain):

- Never use a continuous looping background synth pluck or robotic character voice beeps.
- Trigger situational foley synced to the exact visual action on screen (camera whooshes, pawn bounces, cork pops, parchment chalk brushes, tape rewind scrub, ocean waves and hull creaks, bronze war horns, arrow swishes, steel sword clashes, marching gravel boots, jaw-drop clatter, coin clinks, somber bells, and map tearing).

### Step 5: Mux and Deliver Output Files

1. Pipe the `30 FPS` RGB frames and mixed WAV audio into `ffmpeg` (`libx264 -preset fast -crf 19 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest`) to produce the final `.mp4` animation.
2. Generate the companion Markdown Storyboard and SFX Cue Sheet.
3. Keep rendered `.mp4` videos out of Git (`*.mp4` is gitignored) and upload/update them in the **Heartland Mapped** Google Drive folder (`1ge1IlbHw1N47j0BwXcVT79lCZCbi8kXw`, account `grupoultra53@gmail.com`) using the `gdrive` CLI (`gdrive mutate upload <video.mp4> --parent 1ge1IlbHw1N47j0BwXcVT79lCZCbi8kXw`, or `gdrive mutate update <file_id> <video.mp4>` when replacing an existing render). Sync scripts, configs, keyframes, voiceover audio, and storyboards via GitHub (`https://github.com/grupoultra53-gif/heartland-mapped`).

## Gotchas

- **Static Cropping vs. True 2.5D Movement**: Always extract moving characters, ships, and props onto separate RGBA layers and inpaint the map behind them so they move independently of the camera.
- **Repetitive Audio Fatigue**: Avoid continuous background synth loops or pitched character chatter beeps. Use clean silence between situational foley hits.
- **Caption Clutter**: Keep lower-third subtitles to 2-4 words per card and overhead head callouts under 4 words.
