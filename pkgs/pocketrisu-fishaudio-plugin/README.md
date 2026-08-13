# PocketRisu — Fish Audio Controls

A PocketRisu (RisuAI) **V3 plugin** that adds full playback controls to its built-in TTS
pipeline. Hooks into `addTTSPostprocessor` to capture every TTS audio buffer produced
by the built-in FishSpeech/OpenAI provider, stores it in memory, and exposes a
floating control bar with **play / pause / stop / seek / volume / speed / replay /
skip / clear / playlist** — no source modifications, no proxy changes.

## What it does

When PocketRisu calls `playAudio(arrayBuffer)` for any TTS message, the plugin:
1. Captures the raw audio bytes into a per-message registry (no copy if you skip them)
2. Lazily creates an in-iframe `HTML5 Audio()` instance the user can drive with native
   controls or our floating bar
3. Restores the original playback path unchanged — PocketRisu still plays fire-and-forget
   if you never open the bar

You get:
- ▶ / ⏸ / ⏹ play-pause-stop on the captured buffer
- ⏪ / ⏭ skip within playlist
- 🔁 replay any captured message
- 0–200 % volume slider
- 0.5×–2× playback rate
- 🎣 floating bar (always on top, draggable, minimizable)
- ⚙ settings iframe page for proxy URL / format / voice / auto-play
- 🎣 chat-bar button to play the most recent TTS

## Install

In PocketRisu → **Settings → Plugins → Import Plugin → From URL**:

```
https://raw.githubusercontent.com/likivik/pocketrisu-fishaudio-controls/main/plugin.js
```

Or paste the file contents from this repo into the **From Text** tab.

## Configure

After install, set plugin arguments (Plugin Settings → Fish Audio Controls):

| Arg | Type | Default | Notes |
|-----|------|---------|-------|
| `proxy_url` | string | `http://127.0.0.1:8099` | Erebus Fish Audio proxy base |
| `proxy_path` | string | `/v1/audio/speech` | POST path |
| `response_format` | string | `mp3` | `mp3` `wav` `opus` `pcm` |
| `voice` | string | (empty) | default Fish reference_id |
| `auto_play` | int | `0` | `1` = play each new TTS immediately |

In PocketRisu character settings, pick **fishspeech** (or **OpenAI-compatible** pointed at your proxy),
set `apiUrl = http://erebus.lan:8099/v1/audio/speech` (or your tailnet URL), and any model voice id.

## Update flow

`//@update-url` auto-update checks against the same raw URL on every plugin reload.

## Internals

- `addTTSPostprocessor` — capture, return `void` → original playback untouched
- `addTTSPreprocessor` — strips `*action*` and `_emphasis_` markup before synthesis
- `registerButton('chat', ...)` — 🎣 Play Last
- `registerSetting(...)` — opens `showContainer('fullscreen')` settings iframe
- No native DOM <audio> injected — sits inside plugin iframe so the SafeElement bridge
  isn't needed for media events
- Audio registry: `Map<msgId:segIdx, {mime, base64}>`, base64-encoded because pluginStorage
  is sandbox-safe (no Blob/ArrayBuffer round-trip)

## Files

```
plugin.js        526 lines — single-file V3 plugin
README.md        this file
LICENSE          MIT
```

## Network policy

The plugin does **not** talk to the proxy directly. It only intercepts audio that
PocketRisu's built-in provider already returns. The Fish Audio proxy must be
reachable from PocketRisu's container network already; nothing changes here.

## Tested against

- RisuAI V3 plugin API (plugin format `//@api 3.0`)
- Fish Audio proxy deployed at `erebus.tailXYZ.ts.net:8099` (SillyTavern origin)
- PocketRisu `ghcr.io/pocketrisu/pocketrisu:latest`
