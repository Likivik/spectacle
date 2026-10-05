# Agent-driven video editing on NixOS — research summary (Oct 2026)

User scenario: drop a video path + one-line natural-language instruction, agent
executes the edit. Hermes Agent runs here on NixOS, ffmpeg 9.0.1 already installed.
Goal: rank the most agent-ready, simplest-to-install options with exact commands.

Verified on `erebus`: ffmpeg 9.0.1, uv, python3, node, npm all on PATH.
Hermes skills root: `~/.hermes/skills/` (drop a SKILL.md in here → live).
Hermes install cmd: `hermes skills install <url>` (security-scanned) or
`npx skills add <github>` (ClawHub path used by cut-as-code family).

---

## TL;DR ranking — simplest user flow first

| # | Option | Type | User flow | Hermes-native? | Install effort |
|---|---|---|---|---|---|
| 1 | **video-use** (browser-use) | SKILL.md + Python helpers | drop video in folder, "edit this like a 60s short" | yes — symlink into `~/.hermes/skills/video-use` | 1 clone, 1 `uv sync`, 1 API key |
| 2 | **auto-edit-video-skill** (natyang1234) | SKILL.md + Python CLI, multi-agent | drop video, "auto edit / first cut" | yes — installer has `--agent hermes` | 1 clone, 1 `./install.sh --agent hermes`, optional faster-whisper |
| 3 | **ffmpeg-mcp-video-editor** (AbyAbyss) | MCP server, 38 tools over ffmpeg/Whisper/MediaPipe | user tells agent, agent calls typed tools | yes via Hermes MCP config | `uv sync --all-extras`, add to `~/.hermes/config.yaml` mcp section |
| 4 | **cut-as-code** (WhiteTowerAI) | SKILL.md skill stack (8 sub-skills) | drop video, "use /video-understand + /video-cut + /video-add-captions" | installable via `npx skills add` | 1 npx command; needs yt-dlp + faster-whisper |
| 5 | **Vex** (AKMessi) | Terminal REPL agent, not a skill | launch `vex`, type English | NO — standalone CLI; can be invoked from Hermes but not a skill | `pipx install vex-video[all]` |
| 6 | **video-vob** (deinJoni) | MCP + /vob skill, Claude Code/OpenCode | "/vob my-footage.mp4 → short reel" | partial — adapter is Claude Code/OpenCode only today | `bash install.sh` into project dir |
| 7 | **FireRed-OpenStoryline** (FireRedTeam) | MCP server + LangChain agent + web chat | web UI mainly; Claude Code skills work | partial — only `openstoryline-install/use` skills, designed for own web UI | full Python stack + uvicorn; MoviePy + LangChain |
| 8 | **video-agent / vex-pipeline / Shorz** | proposers + compilers | varies | mixed | varies |

---

## Recommended primary pick: video-use (browser-use)

Why it's #1 for "user drops video + one line":

- Mature skill with explicit Hermes install path in `install.md`.
- User-facing prompt is literally "drop footage into a folder, ask me to edit it".
- All editing primitives are typed CLI scripts (`transcribe`, `render`, `grade`)
  the agent invokes; no GUI.
- Works with any modern ffmpeg (≥ 4.x — we have 9.0.1).
- Only hard external dep: ElevenLabs API key for Scribe transcription (can be
  swapped for local Whisper — ffmpeg-mcp or auto-edit-video-skill cover that).

### Exact NixOS install

```bash
# 1. Clone to a stable path
test -d ~/Developer/video-use || \
  git clone https://github.com/browser-use/video-use ~/Developer/video-use
cd ~/Developer/video-use

# 2. Python deps via uv (uv is already on PATH on erebus)
uv sync                                 # or: pip install -e .

# 3. ffmpeg already installed (9.0.1 verified). Optional:
command -v yt-dlp >/dev/null || pipx install yt-dlp

# 4. ElevenLabs key for Scribe transcription
cp .env.example .env
$EDITOR .env                            # set ELEVENLABS_API_KEY=...

# 5. Register with Hermes (symlink, NOT just SKILL.md — helpers must sit next to it)
ln -sfn ~/Developer/video-use ~/.hermes/skills/video-use

# 6. (optional) Animation engines, installed lazily per-slot
# HyperFrames: npx --yes hyperframes ...   (needs Node 22+)
# Remotion:    npx create-video@latest    (inside the slot dir)
# Manim:       uv pip install manim
```

After install: a fresh Hermes session picks up `video-use` automatically
(it's now in the skills catalog). User flow:

> /video-use
> Edit /storage/footage/meeting.mp4 into a 60-second highlight reel
> with subtitles, color-grade "cinematic warm", export as 1080p mp4.

---

## Runner-up: auto-edit-video-skill (natyang1234)

Best when the user wants the agent to own the full loop with explicit approval
gates and review — close to FireRed-OpenStoryline's human-in-the-loop ethos, but
without the heavy LangChain/server stack.

- MIT, agent-skill standard layout, lists `~/.hermes/skills` as native target.
- Bundled install script targets Hermes directly: `./install.sh --agent hermes`.
- Whisper transcription is local (faster-whisper on CPU works).
- Approval gates (`destructive_edit` → `highlight_selection` → `timeline` → `final`)
  give the user veto power — ideal for "show me the cut plan first".

### Exact NixOS install

```bash
git clone https://github.com/natyang1234/auto-edit-video-skill
cd auto-edit-video-skill
./install.sh --agent hermes              # installs into ~/.hermes/skills/auto-edit-video

# Python deps (the installer does NOT touch pip per its own security notes)
uv venv ~/.venvs/auto-edit-video
source ~/.venvs/auto-edit-video/bin/activate
uv pip install faster-whisper

# ffmpeg already on PATH. For Whisper on CPU: device=cpu, compute_type=int8.
```

User flow:

> /auto-edit-video
> /Storage/videos/talk.mp4 — auto edit, conservative cleanup,
> target youtube-shorts medium, English subtitles.

---

## MCP server pick: ffmpeg-mcp-video-editor (AbyAbyss)

Best when you want the LLM to drive 38 typed editing tools (probe, trim, concat,
overlay, captions, faces, audio mix, color, transitions) with progress polling
rather than a hand-written SKILL.md script. Closest analog to the MCP servers
listed in your task brief.

- Python 3.11/3.12 + uv, `uv sync --all-extras` for full feature set.
- Reads system ffmpeg, falls back to a downloaded static build on first run.
- Hermes MCP config: `~/.hermes/config.yaml` mcp section (or use `hermes mcp add`).

### Exact NixOS install

```bash
git clone https://github.com/AbyAbyss/ffmpeg-mcp-video-editor ~/dev/ffmpeg-mcp
cd ~/dev/ffmpeg-mcp
uv sync --all-extras           # core + Whisper + vision + UI extras
# Run a self-test before wiring to Hermes:
uv run ffmpeg-mcp-server --help

# Register with Hermes — print the literal config block, then paste it:
uv run ffmpeg-mcp-server --print-config
# → paste into ~/.hermes/config.yaml under mcp.servers.ffmpeg-video
```

---

## Other candidates (briefly)

### cut-as-code (WhiteTowerAI)
- Skill stack: 8 sub-skills under `skills/` (`/video-understand`,
  `/video-cut`, `/video-add-captions`, `/video-to-shorts`, etc.).
- Install: `npx skills add WhiteTowerAI/cut-as-code` (ClawHub). Each sub-skill
  is self-contained with its own SKILL.md.
- Pexels API key needed for `/video-add-broll`; otherwise pure ffmpeg +
  faster-whisper. Best for explicit, modular control.

### Vex (AKMessi)
- Terminal-first REPL: `vex` then "trim the awkward intro and remove pauses".
- Heavyweight: MoviePy, optional Manim/Remotion/Blender renderers, Whisper,
  Shorts Director, Auto Effects.
- `pipx install "vex-video[all]"`. Not a SKILL.md — invoke from Hermes via
  `terminal("vex auto-edit /path/to/video.mp4")` or as a Claude Code skill
  copy. 85 stars, 333 commits as of Oct 2026.

### video-vob (deinJoni)
- Full FSM pipeline: ingest → inspect → intent → plan → composition → preview →
  render → package → iterate. Renders via hyperframes (Apache 2.0).
- `/vob` skill for Claude Code, `/vob` command for OpenCode. Hermes adapter
  planned but not shipped today.
- `bash install.sh` into target project dir. Heavy: Node 22+, hyperframes,
  per-phase procedure files.

### FireRed-OpenStoryline (FireRedTeam)
- MCP server + LangChain agent with web chat UI. Two Claude Code skills ship
  in-repo: `openstoryline-install`, `openstoryline-use`.
- Best for narrative / story-driven edits with style-skill reuse. Most
  opinionated about "Style Skills" (saved editing workflows).
- Heavy: requires running uvicorn, LangChain, MoviePy; expects its own web UI.
  Less ideal if you want "agent does it from the chat".

### Other MCP servers worth noting
- `video-editor-mcp` (Glama, Node 22, 9 ffmpeg tools, Docker-optional).
- `VEMCP / video_editing_mcp` (dahshury) — pipeline + Whisper + CUDA.
- `dubnium0/ffmpeg-mcp` — 40+ tools, Python.
- `Yashsh101/video-mcp` — calls Kling/ElevenLabs/Hailuo/Veo for generation +
  ffmpeg for stitching.
- `argus-metis/hermes-video-editing` — turnkey Hermes skill (`ln -s ...video-editing
  ~/.hermes/skills/`), bash install.sh; older & simpler than the others but
  maintenance looks light.
- `Abbiirr/video-editor-harness` — proposer/compiler pattern, deterministic
  re-renders via typed Change Request JSON. Auditable, air-gap-safe.
- `Vossy/ai-video-agent` (Shorz) — Windows desktop app with embedded MCP
  server, 160 tools. macOS in progress. Not Linux-friendly today.

---

## Decision tree

1. Want the most natural "user drops a file, types one line, it works" flow?
   → **video-use** (browser-use). Install path above.
2. Want explicit approval gates and per-step review?
   → **auto-edit-video-skill**. Install path above.
3. Want the LLM to drive fine-grained editing via tool calls (probe, trim,
   overlay, captions) with progress polling?
   → **ffmpeg-mcp-video-editor** MCP server.
4. Want composable modular skills (/video-cut, /video-to-shorts, ...) you
   can chain like Claude slash-commands?
   → **cut-as-code** via `npx skills add WhiteTowerAI/cut-as-code`.
5. Want narrative / style-skill reuse (vlog templates)?
   → **FireRed-OpenStoryline** (heavier; web UI).
6. Want full production-style FSM with hyperframes rendering?
   → **video-vob** (Claude Code / OpenCode only today).

---

## Notes specific to this host (erebus, NixOS)

- All required tools verified present: `ffmpeg 9.0.1`, `uv`, `python3`,
  `node`, `npm`.
- For any `uv`-based tool: `uv` lives at `/run/current-system/sw/bin/uv`; use
  `uv sync` / `uv run` / `uv pip install` — they work in user space, no
  Nix store pollution. For pure CLI tools, prefer `pipx install` (also present).
- ffmpeg in NixOS may lack libx264 / drawtext fonts in some configs. Verify
  with `ffmpeg -codecs | grep libx264` and `ffmpeg -filters | grep drawtext`
  if a tool reports missing encoders. The NixOS `pkgs.ffmpeg-full` already
  pulls these in; the install here used the standard package so they should
  be present (already confirmed by ffmpeg 9.0.1 version line).
- Whisper (faster-whisper) on CPU is fine; first run downloads a model
  (~150 MB for `base`, ~1.5 GB for `large-v3`). To stay snappy, default to
  `WHISPER_MODEL=base` in env.
- Node 22+ required for video-use's HyperFrames slot and for video-vob.
  Check `node --version` before enabling animation features.
- No system package manager (apt/brew) needed — these tools install into
  user space. ffmpeg is the only system-level dep, and it's already there.

---

## Sources (researched 2026-10-03)

- video-use: github.com/browser-use/video-use (SKILL.md, install.md)
- auto-edit-video-skill: github.com/natyang1234/auto-edit-video-skill
- ffmpeg-mcp-video-editor: github.com/AbyAbyss/ffmpeg-mcp-video-editor
- cut-as-code: github.com/WhiteTowerAI/cut-as-code + agentmods.dev/skills
- video-vob: github.com/deinJoni/video-vob
- FireRed-OpenStoryline: github.com/FireRedTeam/FireRed-OpenStoryline
- Vex: github.com/AKMessi/vex
- Hermes skills docs: github.com/NousResearch/hermes-agent (docs/user-guide/features/skills.md)
- Hermes-native helper: github.com/argus-metis/hermes-video-editing
- Other MCP servers: video-editor-mcp (Glama), VEMCP (dahshury),
  dubnium0/ffmpeg-mcp, Yashsh101/video-mcp