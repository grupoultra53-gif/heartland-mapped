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

## Workflow Steps (v2 Retention-Optimized Pipeline)

### Step 1: Analyze Input Audio or Script and Plan ~55-65s Escalating Pacing

1. Target **55 to 66 seconds** total runtime (~165-190 spoken words) for maximum YouTube Shorts & Facebook Reels completion (`> 90%` avg view duration).
2. Open with a **punchy question or twist hook** that matches the video title and first spoken line, followed by a brief VHS Rewind transition (`<< REW`) into the chronological starting year card.
3. Structure the middle in **escalating beats of historical absurdity** (~10-12 scenes, ~85% Mode A 3D Relief Map / ~15% Mode B 2.5D Ground Diorama), with **ZERO mid-roll subscribe requests**.
4. End with a **1-word comment CTA** (e.g., `BUMP`, `HONEY`) paired with an animated comment panel and a **grammatically & visually seamless loop** that flows right back into Frame 0 / Line 1.

### Step 2: Generate Consistent 9:16 Keyframe Visuals

1. Generate all 10-12 vertical `9:16` scene keyframes using `references/prompt_templates.md` (and reuse the first accurate state-map keyframe as geographic reference for all remaining map scenes so state silhouettes stay 100% consistent).
2. Ensure every character follows the Chibi Peg-Doll specification (legless pawn base, 1:2 head-to-body ratio, two black dot eyes, no nose, simple line mouth, thin black stick arms with white-gloved hands).
3. Exclude bottom subtitle text from base keyframe images (keep bottom 25% clear).

### Step 3: Rig Independent 2.5D Sprites, Multi-Shot Close-Ups, Frame 0 Hook & Comment Panel

Import `scripts/engine_25d.py` to render at `720x1280` and `30 FPS`:

1. **Frame 0 Hook (`t=0.0s`)**: Never leave Scene 01 characters hidden at `scale=0` on Frame 0 (`pop_delay=0.0` for focal characters) and start Frame 0 in a **punchy close-up (`zoom >= 1.75x`)** on the expressive character/prop before snapping out to the wide map.
2. **Multi-Shot Word-Synced Rhythm (`eval_shot_camera`)**: Use 2-4 sub-shots per scene alternating wide maps with tight character/prop reaction close-ups (`zoom 1.85x-2.4x`) snapped directly to punchline words — hitting **7.5-12 visual jumps per 10s** and **>= 25% close-up time** (lively yet comfortable for 50+ viewers).
3. **Sprite Rigging**: Call GrabCut / `extract_sprite_and_inpaint_bg` (protecting adjacent map labels via `exclude_rects`) and animate characters independently with `paste_moving_sprite`.
4. **Animated 1-Word Comment Panel & Seamless Loop**: In the final ~3.5s of Scene 12, display `draw_animated_comment_panel` (typing the 1-word CTA + 2 funny in-character historical replies), shift subtitles cleanly above the panel, and end with a `0.32s` whip-cut back to Scene 01 Frame 0.

### Step 4: Mix Voiceover, Situational Foley & Auto-Ducked Warm Documentary Bed

Import `scripts/foley_mixer.py` (`mix_voice_foley_and_bed`):

- Combine foreground narration (`96%`) + crisp situational foley (whooshes, punch-zoom ticks, bounces, gavel slams, axe chops, etc.) + a subtle **warm acoustic documentary bed** (`generate_documentary_bed`) with **automatic voice-activity ducking** (`-16 dB` under speech, lifting to `-7 dB` in pauses) so inter-phrase gaps stay alive (`<= 8.5 dB` drop, zero `-28 dB` dead holes) without irritating synth loops.

### Step 5: Audit, Mux, and Deliver Output Files

1. Pipe `30 FPS` RGB frames and mixed WAV audio into `ffmpeg` (`libx264 -preset fast -crf 19 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart -shortest`) to produce the final `.mp4`.
2. **Run Mandatory Self-Audit (`scripts/audit_video.py <episode_dir>`)** and inspect rendered QA frames (`qa_scene_00_hook.jpg`, close-ups, comment panel, final loop frame) to confirm all v2 retention targets pass (`Duration 50-72s`, `>= 7.5 jumps/10s`, `>= 25% close-up`, `Frame 0 PASS`, `Audio gap <= 8.5 dB`, `Comment Panel + Loop`).
3. Generate the companion `STORYBOARD_AND_SFX.md` and plain-text `POSTING_KIT.txt` inside the episode folder (Facebook Reels caption, YouTube Shorts title & description, pinned comment, cover suggestion, publishing checklist, and Google Drive link).
4. Keep rendered `.mp4` videos out of Git (`*.mp4` is gitignored) and upload/update them in the **Heartland Mapped** Google Drive folder (`1ge1IlbHw1N47j0BwXcVT79lCZCbi8kXw`, account `grupoultra53@gmail.com`) via `gdrive mutate upload` / `gdrive mutate update`. Sync code, keyframes, audio `.mp3`, `audit_report.json`, storyboards, and `POSTING_KIT.txt` via GitHub (`https://github.com/grupoultra53-gif/heartland-mapped`).

## Gotchas

- **Static Cropping vs. True 2.5D Movement**: Always extract moving characters, ships, and props onto separate RGBA layers and inpaint the map behind them so they move independently of the camera.
- **Repetitive Audio Fatigue**: Avoid continuous background synth loops or pitched character chatter beeps. Use clean silence between situational foley hits.
- **Caption Clutter**: Keep lower-third subtitles to 2-4 words per card and overhead head callouts under 4 words.
