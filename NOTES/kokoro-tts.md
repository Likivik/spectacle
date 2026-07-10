# Kokoro-FastAPI TTS Server

Local text-to-speech server using Kokoro-82M via the [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) container image.

## Architecture

```
┌──────────────┐     HTTP (OpenAI-compatible)
│  Podman (OCI)├──── localhost:8880 ──────► curl / opencode
│  Kokoro-Fast │                                │
│  API (CPU)   │                                │
│              │◄──── /v1/audio/speech ──────────┘
└──────────────┘        POST {"input": "..."}
```

- Runs via `virtualisation.oci-containers` (system podman container)
- Binds `127.0.0.1:8880` (localhost only — not on Tailscale yet)
- CPU inference (3–5× realtime). Traversal's Ryzen 7 6800H Radeon 680M iGPU is **not** ROCm-compatible (RDNA 2, not in any ROCm 7.x matrix). If user upgrades to a ROCm-compatible GPU, see "ROCm upgrade" below.
- Model weights cached in `kokoro-models` podman volume (~327 MB first-run download)

## Usage

### Via opencode

```
/tts <text>
```

Or just `/tts` to read the last assistant response.

### Via curl

```bash
curl -s -X POST http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"kokoro","input":"hello world","voice":"af_heart"}' \
  -o /tmp/tts.wav && pw-play /tmp/tts.wav
```

### Available voices

| Voice | Description |
|---|---|
| `af_heart` | Premium American female (default) |
| `af_bella` | American female |
| `af_nicole` | American female, deeper |
| `am_adam` | American male |
| `am_michael` | American male, deeper |
| `bf_emma` | British female |
| `bm_george` | British male |

## Container details

| Field | Value |
|---|---|
| Image | `ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.0post4` |
| Port | `127.0.0.1:8880:8880` |
| Volume | `kokoro-models:/app/data` |
| Pull policy | `--pull=newer` |
| Auto-start | `true` |

## Files

- `modules/aspects/tts/default.nix` — Aspect definition (oci-container + curl/pulseaudio packages)
- `modules/hosts/traversal/traversal.nix` — Includes `den.aspects.tts`
- `.opencode/commands/tts.md` — `/tts` slash command for opencode

## Known issues

- Technical text (code, abbreviations, numbers) is mispronounced. Kokoro doesn't have specialized text normalization. Pre-normalize manually (e.g., "WV" → "West Virginia") if precision matters.
- First run downloads ~327 MB model weights. Takes 5–15s on cold start.
- CPU-only on traversal. Inference at ~3–5× realtime.

## ROCm upgrade

If the host gets a ROCm-compatible GPU (Radeon RX 7000 series or higher), switch the image to:

```
ghcr.io/remsky/kokoro-fastapi-rocm:v0.2.0post4
```

And add ROCm kernel modules + device passthrough:

```nix
extraOptions = [
  "--device=/dev/kfd"
  "--device=/dev/dri"
  "--group-add=video"
];
```
