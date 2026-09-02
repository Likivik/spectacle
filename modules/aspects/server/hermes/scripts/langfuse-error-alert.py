#!/usr/bin/env nix-shell
#! nix-shell -i python3 -p python3
# Langfuse model error rate monitor — alerts if >50% of recent observations are errors.
# v4 migration: reads the Observations API v2 (GENERATION type only) — the legacy
# /api/public/observations endpoint 404s after Langfuse Cloud's 2026-11-16 cutover.
import base64, json, subprocess, sys, urllib.request

LF_PK = "pk-lf-e8b29ad2-524b-4439-98d7-9fd4f2d783e1"
LF_SK = subprocess.run(
    ["/run/wrappers/bin/sudo", "cat", "/run/secrets/langfuse/graphiti-litellm/secret-key"],
    capture_output=True, text=True,
).stdout.strip()
LF_HOST = "https://cloud.langfuse.com"

if not LF_SK:
    print("langfuse-alert: no secret key, skipping", file=sys.stderr)
    sys.exit(0)

def api(path):
    req = urllib.request.Request(
        f"{LF_HOST}{path}",
        headers={"Authorization": "Basic " + base64.b64encode(f"{LF_PK}:{LF_SK}".encode()).decode()},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

try:
    # Observations carry the ERROR levels; fetch recent generations (v4 API).
    obs = api("/api/public/v2/observations?limit=100&type=GENERATION").get("data", [])
except Exception as e:
    print(f"langfuse-alert: API error: {e}", file=sys.stderr)
    sys.exit(0)

total = len(obs)
if total == 0:
    sys.exit(0)

errors = sum(1 for o in obs if o.get("level") == "ERROR")
rate = errors * 100 // total

if rate > 50:
    # Show which models are failing
    models = {}
    for o in obs:
        if o.get("level") == "ERROR":
            m = o.get("model") or o.get("name") or "?"
            models[m] = models.get(m, 0) + 1
    top = ", ".join(f"{m} x{n}" for m, n in sorted(models.items(), key=lambda x: -x[1])[:5])
    print(f"🚨 Langfuse Alert: {errors}/{total} observations errored ({rate}%)")
    print(f"Top failing: {top}")
    print(f"Check: {LF_HOST}")
