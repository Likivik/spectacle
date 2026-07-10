---
description: Speak text aloud using local Kokoro TTS server
---

Use curl to call the local Kokoro-FastAPI server at localhost:8880 and play the audio.

1. If text argument provided: speak that text
2. If no text argument: summarize the last assistant message into 1-2 sentences, then speak that

Call the API:
```bash
curl -s -X POST http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"kokoro","input":"<text>","voice":"af_heart"}' \
  -o /tmp/tts-output.wav && pw-play /tmp/tts-output.wav && rm /tmp/tts-output.wav
```

Available voices: af_heart (default), af_bella, af_nicole, am_adam, am_michael, bf_emma, bm_george
