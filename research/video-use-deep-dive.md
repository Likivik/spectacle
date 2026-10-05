# `browser-use/video-use` — Deep-Dive for Hermes on NixOS

**Date:** 2026-10-03
**Repo:** <https://github.com/browser-use/video-use>
**Verdict for Hermes:** Active, opinionated, **not abandoned** — but comes with a
hard paid dependency (ElevenLabs Scribe) and a few landmines worth knowing about.

---

## 1. Repository snapshot

| Metric | Value | Source |
|---|---|---|
| Stars | **~23,200** (range 21,376 → 27,900 across snapshots Oct 2026) | github.com page header |
| Forks | **~2,660–3,300** | github.com page header / API |
| Watchers | matches stars | github.com |
| Open issues | **81** (web page) / **141** (REST API; the higher number is issue+PR combined) | github.com / `api.github.com/repos/browser-use/video-use` |
| Open PRs | 50+ | `…/issues?state=open` (PRs are issue-typed in the API count) |
| License | **MIT** | LICENSE file (added 2026-05-10, PR #32) |
| Default branch | `main` | API |
| Created | 2026-04-12 | API |
| Last commit on `main` | **2026-09-24** (`b8770638` — "render: phrase-aware captions, fail on missing subtitles; skill: sound, fonts, critic pass" #183) | API commits list |
| Last `pushed_at` | 2026-10-02T17:13Z | API |
| Last `updated_at` | 2026-10-03T01:00Z | API |
| Top contributors | gregpr07 (Gregor Žunič — browser-use co-founder) 9 commits, ShawnPana 4, sidorovanthon 2, antoinersx 2; ~8 named humans | API |
| Languages | Python 75.8%, HTML 23.1%, Shell 1.1% (per fork) | GitHub Languages API |
| Vendored sub-skill | `skills/manim-video/` | `api/.../contents/skills` |
| Discussions | **disabled** (`has_discussions: false`) — there is no GitHub Discussions tab; all conversation lives in Issues / PRs | API |

**Commit cadence** (most recent first, dates UTC):
- 2026-09-24 — `b877063` render/captions rework (PR #183)
- 2026-08-30 — `9575612` transcribe: `--audio-track` flag + silence guard (PR #134, three rounds of review)
- 2026-07-01 — `92c2b34` Merge PR #91 (README updates)
- 2026-05-10 — `507c215` Add MIT license (#32)
- 2026-04-23 — `fdf749c` Bump subtitle MarginV=90
- 2026-04-15 — three README what-it-does commits
- 2026-04-12 — rename to `video-use`, README hero

The rate is **~one substantive PR every 4–8 weeks**, with bursts of Claude-generated
PRs in late August / September. It's a slow-trickling, high-signal stream, not
abandoned but also not high-velocity.

**Verdict on "actively maintained":** Yes — Gregor Žunič (`gregpr07`) is the
browser-use co-founder and is the driving committer; commits ship on `main` in the
last 30 days. But it's a one-maintainer shop with light outside PRs (most merged
PRs are authored by `gregpr07` himself via Claude Code).

---

## 2. What's actually in the repo

Top-level layout (from `api/.../contents`):

```
browser-use/video-use/
├── README.md            5.6 KB   — overview, manual install, design principles
├── install.md           7.7 KB   — separate frontmatter'd skill ("video-use-install")
├── SKILL.md            26.1 KB   — the actual skill body (frontmatter + 12 hard rules + workflow)
├── LICENSE              1.1 KB   — MIT
├── helpers/             dir     — six Python scripts (see below)
├── skills/manim-video/  dir     — vendored sub-skill for Manim animations
├── poster.html         20.0 KB   — landing-page promo asset (committed, not for editing)
└── pyproject.toml      0.45 KB   — `name = "video-use"`, requires-python >= 3.10
```

**`helpers/`** (six scripts, `git log` per file):

| File | Size | Last commit | Purpose |
|---|---|---|---|
| `transcribe.py` | 8.0 KB | 2026-08-30 (#134) | Single-file ElevenLabs Scribe call; `--audio-track N`; refuses silent audio; **hardcoded `model_id="scribe_v1"`**; verbatim+diarize+word-level; cached by track-aware key |
| `transcribe_batch.py` | 4.0 KB | 2026-08-30 (#134) | 4-thread `ThreadPoolExecutor` parallel batch; shares `transcript_path()` resolver with single mode (review caught drift) |
| `pack_transcripts.py` | 7.2 KB | 2026-05-10 (#10) | `transcripts/*.json` → `takes_packed.md` (phrase-level, break on silence ≥ 0.5s); UTF-8 fix on Windows |
| `timeline_view.py` | 13.7 KB | 2026-04-12 | Filmstrip + waveform PNG for a `[start, end]` range; used by agent at decision points and in self-eval |
| `render.py` | 29.5 KB | 2026-09-24 (#183) | Per-segment extract → lossless `-c copy` concat → PTS-shifted overlays → subtitles LAST; `--preview`, `--build-subtitles`; phrase-aware caption chunking; loudnorm added in PR #183 batch |
| `grade.py` | 13.2 KB | 2026-04-12 | ASC-CDL-ish ffmpeg filter chain; presets `warm_cinematic`, `neutral_punch`, `none` + `--filter '<raw>'` |

**SKILL.md is the load-bearing artifact.** It contains:
- YAML frontmatter (`name: video-use`, a one-line `description:` trigger that
  Hermes's skill loader will key on)
- 7 design principles
- **12 Hard Rules** (non-negotiable, e.g. subtitles LAST, 30 ms audio fades,
  SRT must use output-timeline offsets, never cut inside a word, cache
  transcripts per source, parallel sub-agents for overlays)
- Directory layout, cold-start checklist
- The 8-step process (inventory → pre-scan → converse → propose → execute →
  preview → self-eval → iterate/persist)
- Cut craft, packed-transcript format, editor sub-agent brief template
- Color grade and subtitles guidance (with worked styles)
- Animation engine pick-list (HyperFrames, Remotion, Manim, PIL)
- EDL JSON schema
- `project.md` session memory format
- Anti-patterns list

**Helpers are called as plain CLI** — `python helpers/transcribe.py video.mp4`,
no console-script entry points. SKILL.md and helpers/ are siblings; the skill
must be symlinked as the whole directory, not just SKILL.md.

**`pyproject.toml`** (verbatim):

```toml
[project]
name = "video-use"
version = "0.1.0"
description = "Conversation-driven video editor skill for Claude Code"
license = { file = "LICENSE" }
requires-python = ">=3.10"
dependencies = [
    "requests",
    "librosa",
    "matplotlib",
    "pillow",
    "numpy",
]

[project.optional-dependencies]
animations = ["manim"]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
py-modules = []
```

There is **no `__init__.py`, no Python package**, no console script, no test
suite in the main package layout (`tests/` was added separately per PR #198).
`uv sync` / `pip install -e .` exists mostly for the dependency declaration.

---

## 3. Full dependency list and runtime requirements

### Python (hard)
- `requests`, `librosa`, `matplotlib`, `pillow`, `numpy` — declared in `pyproject.toml`
- `python>=3.10` (3.11 / 3.12 also work; PR #198 tests both)

### System binaries (hard)
- `ffmpeg` + `ffprobe` on `$PATH` — install.md says "any modern (≥ 4.x) build is enough". Practical note from FSR: **Homebrew's default ffmpeg may be missing the subtitles filter** in some configurations, breaking the burn-in step (a contributor-reported issue).
- `node` >= **22** only needed if the user actually triggers HyperFrames or Remotion animation slots. Manim is installed lazily.
- `uv` preferred (or `pip` works).

### External services (hard, paid)
- **ElevenLabs Scribe v1** — `https://api.elevenlabs.io/v1/speech-to-text`, model_id hardcoded to `scribe_v1`. The audio is uploaded (mono 16 kHz extracted by ffmpeg first); diarize + word-level timestamps + audio events requested.
  - Audio is sent to **ElevenLabs US storage** by default; regional residency and Zero Retention are **Enterprise-only**. `transcribe.py` does **not** pass the Zero Retention parameter.
  - **Pricing gotcha (verified by Future Stack Reviews):** the ElevenLabs public rate card prices **Scribe v2 ($0.22/hr) and Scribe v2 Realtime ($0.39/hr)** but **has no Scribe v1 line** at the time of FSR's snapshot. Hardcoding `scribe_v1` means pricing risk: a Scribe v1 request might silently fail or bill on an undocumented rate. "Ask ElevenLabs in writing what a scribe_v1 request currently does and bills" — FSR.
  - **Privacy landmine:** every video frame the LLM ever inspects via `timeline_view` is loaded into context; if your agent is a hosted model, that visual material is uploaded to that provider.

### Optional
- `yt-dlp` (pip or system) — for URL sources
- `manim` — `pip install manim` (animation engine; lazy)
- HyperFrames (`npx --yes hyperframes ...`) — Node 22+, lazy
- Remotion (`npx create-video@latest` or local install inside slot dir) — lazy
- PIL + NumPy — for PIL-based overlay cards (the launch video used this; no install needed if NumPy is already there)

### Resources
- `librosa` + `matplotlib` imports imply non-trivial memory; the helpers aren't
  GPU-heavy but `librosa.load()` on a 2-hour take is known to balloon RAM
  (PR #134 caught and fixed exactly this — `peak_dbfs` previously loaded the
  whole file; now scans in 64k-frame chunks).
- No Chromium, no Selenium, no headless browser — the name is misleading; the
  skill has nothing to do with browser automation despite living under
  `browser-use/video-use`.
- ffmpeg renders are CPU-bound; encoding time scales linearly with output duration × source resolution.

---

## 4. Exact user flow and what the agent runs

### Day 1 install (from `install.md`)

```bash
# 1. Clone (the install.md tells the AGENT to do this)
test -d ~/Developer/video-use || git clone https://github.com/browser-use/video-use ~/Developer/video-use
cd ~/Developer/video-use
git pull --ff-only

# 2. Python deps
command -v uv >/dev/null && uv sync || pip install -e .

# 3. ffmpeg + (optional) yt-dlp
command -v ffmpeg >/dev/null || sudo apt-get install -y ffmpeg   # Debian/Ubuntu
command -v yt-dlp  >/dev/null || pipx install yt-dlp              # optional

# 4. Register the skill with the host agent
# For Hermes (per install.md, Section 4):
ln -sfn ~/Developer/video-use ~/.hermes/skills/video-use
# (OR add @~/Developer/video-use/SKILL.md to a CLAUDE.md-equivalent)

# 5. ElevenLabs key
printf 'ELEVENLABS_API_KEY=%s\n' "$KEY" > ~/Developer/video-use/.env
chmod 600 ~/Developer/video-use/.env

# 6. Sanity probe
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "xi-api-key: $(sed -n 's/^ELEVENLABS_API_KEY=//p' ~/Developer/video-use/.env)" \
  https://api.elevenlabs.io/v1/user
# 200 = good; 401 = bad key; anything else = move on.

# 7. Verify helpers can be invoked
python ~/Developer/video-use/helpers/timeline_view.py --help >/dev/null && echo "helpers OK"
ffprobe -version | head -1
```

The "setup prompt" the user pastes into Hermes:

```
Set up https://github.com/browser-use/video-use for me.

Read install.md first to install this repo, wire up ffmpeg, register the skill
with whichever agent you're running under, and set up the ElevenLabs API key —
ask me to paste it when you need it. Then read SKILL.md for daily usage, and
always read helpers/ because that's where the editing scripts live. After
install, don't transcribe anything on your own — just tell me it's ready and
wait for me to drop footage into a folder.
```

### Per-session flow (from `SKILL.md`)

1. **Inventory** — `ffprobe` every source; `python helpers/transcribe_batch.py
   <videos_dir>` (4-thread parallel); `python helpers/pack_transcripts.py
   --edit-dir <videos_dir>/edit` to make `takes_packed.md`.
2. **Pre-scan** — single pass over `takes_packed.md` for verbal slips.
3. **Converse** — agent asks user content-type / target length / aesthetic /
   pacing / must-preserve / must-cut / grade / subtitle prefs / animation needs.
   No fixed checklist — questions are material-shaped.
4. **Propose strategy** — 4–8 sentences: shape, take choices, cut direction,
   animation plan, grade direction, subtitle style, length estimate. **Wait
   for confirmation.**
5. **Execute** — produce `edl.json` (via editor sub-agent brief when multi-take
   selection is needed). Drill into `timeline_view.py` at ambiguous moments.
   Build animations in **parallel sub-agents** (one per slot, via the `Agent`
   tool — `Task`/`spawn` for Hermes).
6. **Preview** — `python helpers/render.py edl.json -o edit/preview.mp4 --preview`.
7. **Self-eval** — agent runs `timeline_view.py` on the **rendered output**
   at every cut boundary (±1.5s window). Checks: visual jump, audio pop,
   subtitle hidden behind overlay, overlay alignment, grade consistency.
   Cap at 3 self-eval passes; flag and ask the user rather than loop.
8. **Iterate + persist** — natural-language feedback loop; append to
   `edit/project.md`.

### Exact commands the agent invokes

```bash
# Per-source transcription
python helpers/transcribe.py /path/to/take.mp4 --edit-dir /path/to/videos/edit

# Batch (default 4 workers)
python helpers/transcribe_batch.py /path/to/videos

# Pack transcript view
python helpers/pack_transcripts.py --edit-dir /path/to/videos/edit

# Visual drill-down (called only at decision points)
python helpers/timeline_view.py /path/to/videos/edit/preview.mp4 4.2 6.8

# Color grade a segment (presets or raw filter)
python helpers/grade.py /path/to/seg_in.mp4 -o /path/to/seg_out.mp4 --preset warm_cinematic
python helpers/grade.py /path/to/seg_in.mp4 -o /path/to/seg_out.mp4 --filter 'eq=contrast=1.1:saturation=0.9'

# Render the EDL
python helpers/render.py /path/to/edit/edl.json -o /path/to/edit/final.mp4 --preview
python helpers/render.py /path/to/edit/edl.json -o /path/to/edit/final.mp4 --build-subtitles
```

There is **no LLM call to a vision model for the bulk of editing** — the LLM
reasons from `takes_packed.md` (≈12 KB of phrase-level transcript). Vision is
only invoked at decision points via `timeline_view.py` PNG inspection.

---

## 5. Community sentiment — what people actually say

### Stars / velocity

- Shipped April 2026; per the andrew.ooo review (2026-07-02) it added **3,000+
  stars in a single week** in early July, hitting 13 k+ within three months.
- Currently ~23 k stars — well above that, but growth has flattened to a
  steady ~+1 k/week (cf. clauday.com Oct 2026 mention of 25.8 k).

### Press / blog reviews

| Outlet | Tone | Key takeaway |
|---|---|---|
| andrew.ooo (Jul 2026) | Positive — called it "one of the more surprising open-source releases of 2026" | Praises the transcript-first design ("don't ask an LLM to do what LLMs are worst at — reasoning about pixels"); notes ElevenLabs dependency cost as the main critique |
| zhichai.net (EN) | Deeply technical, positive | Token-cost framing: naive frame-by-frame would be ~54M tokens / ~$810 vs. video-use's 12 KB + a few PNGs (~$0.01) |
| coderlegion.com | Positive, architectural deep-dive | "Incredible leverage of combining specialized transcription APIs, deterministic FFmpeg pipelines, and AI coding agents" |
| clauday.com (Oct 2026) | Positive, sharp | Calls out the 30 ms fade detail as "the tell that a human who has actually edited video wrote this" — production-correctness signals |
| future-stack-reviews.com | **Mixed / cautionary** — Tier C static-review only | Flags: hardcoded `scribe_v1` with no model flag; **no Scribe v1 on the public rate card**; ElevenLabs US storage + Enterprise-only Zero Retention; helper doesn't pass Zero Retention parameter; no release tag / lockfile; contributor reports of "Chinese transcript tokens arriving one per character", "Non-Latin captions rendering as empty boxes", "Homebrew ffmpeg lacking the subtitles filter" |
| skills.sh / agskills.dev | Neutral — registries | Both auto-index the repo with one-line install (`npx skills add browser-use/video-use`) |

### The community-cited critique pattern

- **#1 critique (Reddit, X):** the ElevenLabs dependency and the cost of
  transcribing long sources. Legitimate. Fork **`Moh4696/freecut`** exists
  specifically to swap the paid Scribe backend for **local Whisper** (mlx-whisper
  on Apple Silicon, faster-whisper elsewhere) with optional `vibevoice` for
  CUDA-only diarization. The original ElevenLabs backend remains selectable.
- **#2 critique:** Hardcoded `scribe_v1` and Scribe v1's uncertain status on
  the rate card.
- **#3 critique:** Self-eval "only goes so far" — the agent will ship a video
  with broken captions if you don't catch the early signs.
- **#4 critique:** No packaged release — `pip install video-use` doesn't work;
  you must clone the moving `main`. The repo has **no git tags**.

### Forks observed

- `engoncode/video-use` (14 commits behind main)
- `raky6666/video-use`, `allinbsv/video-use`, `lllMaxMaxlll/video-use`,
  `srikant/video-use` — personal forks with minor changes
- `aradotso/trending-skills/skills/video-use-editor/SKILL.md` — a derivative
  skill package
- `timscheuerai/content-vault/skills/video-use/install.md` — vendored install doc
- **`Moh4696/freecut`** — the substantive local-Whisper fork (worth knowing
  about as a backup plan)
- `skills.sh` and `agskills.dev` registries list it under their auto-indexed
  agent-skills catalog

### X / Twitter

Public sentiment is mostly from people re-tweeting the launch demo (the
"15-second demo" linked from README is Browser Use Box's hosted version).
Most cited tweets are by `gregpr07` / browser-use announcing features. No
major public backlash. No HN front-page thread located in this research
window (search returned only the andrew.ooo and zhichai.net reviews; HN
algorithmic search isn't on the configured backend).

### Issues snapshot

- **~141 open (issue + PR)** at snapshot time. The PR-to-issue ratio is
  unusually high — many open items are PRs awaiting review.
- Top open issues observed:
  - **#121 "Add a preflight/doctor command"** — the install path has no
    environment sanity check; deep failure on missing `ffprobe`/broken
    Remotion/Manim happens mid-render. PR #129 drafts `helpers/check_env.py`
    with `--json` output, exit codes 0/1/2. Status: open, awaiting refinement.
  - **#95 "Is it possible to extract the important or exciting frames from the
    video?"** — user feature request; open since 2026-06-30.
  - **#134** (merged) — the three-review-thread transcription rework shows
    the project actually does code review on PRs (rare and reassuring).
  - **#183** (merged 2026-09-24) — caption-quality rework after the launch
    video surfaced real issues ("DOES IS" across a pause, 0.18s "WHAT A"
    flash). Adds music/SFX rules, per-section loudness check, **critic
    sub-agent** in self-eval, web-font-load assertion. 26 tests pass; 9 new.
  - **#198** (open PR) — adds `.github/workflows/tests.yml` for CI on
    Python 3.10 + 3.12. Worth noting: **there is no CI on main right now** —
    the workflow was being added in late September 2026.

---

## 6. What a Hermes / NixOS user should know before installing

### Pre-flight checklist

- [ ] **ffmpeg with `--enable-libass` (or equivalent subtitle filter)** — NixOS
  `pkgs.ffmpeg` ships with this on; some Homebrew builds don't. Verify with
  `ffmpeg -filters 2>&1 | grep subtitles`. If missing, you cannot burn SRT
  into MP4 (a known contributor-reported bug — issue not fixed as of snapshot).
- [ ] **`librosa` + `matplotlib` build deps** — `librosa` pulls `soundfile`
  which needs `libsndfile`, and `matplotlib` needs a working C compiler. On
  NixOS these resolve through the standard Python wheels (`uv sync` typically
  picks them up; pip with `--break-system-packages` works too).
- [ ] **ElevenLabs account + API key + a credit card.** Free tier exists but
  Scribe v1 minutes count. If you don't want to pay, fork **`freecut`** for
  local Whisper.
- [ ] **A non-trivial amount of disk** — `takes_packed.md` is tiny but
  `transcripts/<name>.json` is the full Scribe response (often hundreds of KB
  per hour), and rendered segments are written to `<videos_dir>/edit/`.
- [ ] **An LLM context budget for the transcript** — `takes_packed.md` is
  ~12 KB per ~10 minutes of source; a 90-minute interview packs to roughly
  100 KB, well within any modern agent's context but worth knowing.
- [ ] **Where you want the symlink.** The repo's `install.md` recommends
  `~/Developer/video-use` and a symlink at `~/.hermes/skills/video-use`. This
  matches Hermes's skill discovery (`~/.hermes/skills/<name>/SKILL.md`).

### Install on NixOS — what changes from install.md

The install doc is **macOS-centric** (Homebrew commands). On NixOS:

```nix
# In your home-manager or system config:
home.packages = with pkgs; [
  ffmpeg
  python311               # 3.10+ per pyproject.toml
  uv                      # preferred
  yt-dlp                  # optional
  nodejs_22               # ONLY if you plan to use HyperFrames / Remotion overlays
  # pillow / numpy / matplotlib / librosa / requests are pip-installed via uv sync
];
```

Then in your shell:

```bash
test -d ~/Developer/video-use || \
  git clone https://github.com/browser-use/video-use ~/Developer/video-use
cd ~/Developer/video-use
uv sync                           # installs deps into .venv
ln -sfn ~/Developer/video-use ~/.hermes/skills/video-use
printf 'ELEVENLABS_API_KEY=%s\n' "$KEY" > .env && chmod 600 .env
python helpers/timeline_view.py --help >/dev/null && echo "helpers OK"
```

**Don't `pip install --break-system-packages` blindly** — use `uv sync` so
deps land in the repo's `.venv` and the helpers resolve their `requests` /
`librosa` imports cleanly.

### Things that will bite you

1. **ElevenLabs Scribe v1 is on a moving target.** The hardcoded `scribe_v1`
   has no public rate-card line; per FSR, ask ElevenLabs in writing before
   committing volume. Otherwise you may get silent failures or surprise bills.
2. **Audio uploaded to US.** Default. No Zero Retention param sent. If your
   footage contains anything sensitive, this is a hard stop — use `freecut`
   or run your own Whisper.
4. **No git tag / no lockfile.** You're tracking `main`. Pin a commit in
   production (`git checkout <sha>`) or fork and pin.
5. **No CI on `main` yet** (PR #198 in flight). Bugs in helpers may not be
   caught before you pull.
6. **30 ms fade depends on per-segment `key`.** If you re-render with overlays
   added on top of an existing extract, you can miss the fade boundary and
   ship a video with audio pops. `render.py` is the only safe path; don't
   hand-roll.
7. **The skill assumes you start from raw, multi-take footage.** It is **not**
   a single-clip trim tool. For "just cut 30 seconds out of one file", raw
   ffmpeg is faster and cheaper.
8. **`timeline_view.py` outputs PNG.** If your agent (Hermes in this case)
   uses a hosted vision model, those frames are uploaded to that provider.
   On-device vision (via local Ollama, or model-side with vision) avoids this.
9. **Multi-track recordings** (OBS app audio vs. mic on track 0 vs. 1) need
   `--audio-track 1`. The default is track 0, which on screen-captures is
   usually wrong (the application audio). PR #134 added the flag but the
   helper still picks track 0 by default.
10. **HyperFrames / Remotion animations require Node 22+**, scaffolded inside
    each slot directory. If you don't need overlays, you can ignore this.
11. **Librosa on 2-hour files used to crash with OOM** before PR #134 — the
    issue is fixed but the fix is recent. If you see big memory use during
    transcription's peak-detection, that's expected (it's now 64k-frame
    chunked).

### Skill-packaging notes for Hermes

- `SKILL.md` has a YAML frontmatter with `name: video-use` and a one-line
  `description:`. Hermes's skill loader (`hermes skills install`) keys on
  this description for trigger matching.
- `install.md` has its own frontmatter (`name: video-use-install`,
  `description: Install video-use into the current agent...`). Hermes will
  surface this as a **separate** trigger ("install video-use") — useful
  for day-1 setup but not for the per-session flow.
- The skill path expects `helpers/` next to `SKILL.md`. Symlinking only
  `SKILL.md` will break. Use a directory-level symlink.

---

## 7. Bottom line

**Is it actively maintained?** Yes — by Gregor Žunič, the browser-use co-founder,
on a slow but steady cadence, last commit 9 days before this report.

**Is the codebase mature?** Yes — the SKILL.md is 26 KB and shipshape; 12 hard
production rules; helpers cover the whole pipeline; review culture is real (PR #134
took three rounds). But there is no CI on `main`, no release tag, and no
packaged Python distribution.

**Will it work on NixOS for Hermes?** Yes — install via `git clone` + `uv sync`
+ NixOS-managed `ffmpeg` + a directory symlink into `~/.hermes/skills/`. The
README's macOS/Homebrew assumptions are the only friction.

**Should we install it?** It depends on whether you're willing to:

- Pay ElevenLabs Scribe per minute of source audio (the only real cost)
- Upload audio to ElevenLabs US (privacy trade-off)
- Track `main` rather than a versioned release

If yes → it's the best-in-class agent-driven video editor available, with first-class Hermes support in `install.md`.

If no → `freecut` (Moh4696's fork) is the local-Whisper drop-in replacement, MIT-licensed from the same base.

**Alternative considerations:** The repo doesn't compete on ffmpeg primitives
(that's `desktop-use` territory). It's specifically a **conversation-driven
editing skill** — a one-paste-setup, plain-English editor for non-engineers.
Hermes with this skill becomes a video editor for the user, not for itself.

---

## Sources

- GitHub repo: <https://github.com/browser-use/video-use>
- API metadata: <https://api.github.com/repos/browser-use/video-use>
- API commits: <https://api.github.com/repos/browser-use/video-use/commits>
- API contents: <https://api.github.com/repos/browser-use/video-use/contents/>
- API contents (helpers): <https://api.github.com/repos/browser-use/video-use/contents/helpers>
- API contents (skills): <https://api.github.com/repos/browser-use/video-use/contents/skills>
- API open issues: <https://api.github.com/repos/browser-use/video-use/issues?state=open>
- README: <https://raw.githubusercontent.com/browser-use/video-use/main/README.md>
- SKILL.md: <https://raw.githubusercontent.com/browser-use/video-use/main/SKILL.md>
- install.md: <https://raw.githubusercontent.com/browser-use/video-use/main/install.md>
- pyproject.toml: <https://raw.githubusercontent.com/browser-use/video-use/main/pyproject.toml>
- Issue #121 preflight/doctor: <https://github.com/browser-use/video-use/issues/121>
- PR #134 (audio track): <https://github.com/browser-use/video-use/pull/134>
- PR #183 (captions rework): <https://github.com/browser-use/video-use/pull/183>
- DeepWiki transcription doc: <https://deepwiki.com/browser-use/video-use/2.1-transcription-and-ingestion>
- andrew.ooo review (Jul 2026): <https://andrew.ooo/posts/video-use-browser-use-ai-video-editor-review/>
- zhichai.net analysis: <https://zhichai.net/en/topic/178585130>
- coderlegion breakdown: <https://coderlegion.com/28224/video-use-how-browser-use-created-an-ai-agent-video-editor>
- clauday.com: <https://clauday.com/article/8def25dc-b250-4fd1-9015-e6a67dd5392b>
- future-stack-reviews.com: <https://future-stack-reviews.com/video-use-review/>
- skills.sh listing: <https://www.skills.sh/browser-use/video-use>
- agskills.dev listing: <https://agskills.dev/browser-use/video-use/video-use>
- freecut fork: <https://github.com/Moh4696/freecut>
- trending-skills derivative: <https://github.com/aradotso/trending-skills/blob/main/skills/video-use-editor/SKILL.md>