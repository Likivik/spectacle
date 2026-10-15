#!/usr/bin/env bash
# verify-mcp-index.sh — post-deploy smoke test for the nextcloud-mcp server
# on poweredge.
#
# Confirms:
#   1. nextcloud-mcp.service is active and the systemd ExecStart references a
#      recognisable image (parsed from `systemctl show`, not a brittle quadlet
#      path that may not be readable from this host).
#   2. The MCP server responds to a streamable-HTTP `initialize` handshake at
#      /mcp with HTTP 200, an `Mcp-Session-Id` header, and a body that
#      contains `serverInfo` (does NOT pin a specific server version).
#   3. Qdrant is reachable and the `poweredge-bge-m3` collection exists and
#      reports status=green.
#   4. For each tracked doc_type (file / note / deck_card / mail_message /
#      news_item) we report total points, placeholder points, and
#      non-placeholder points — and we ASSERT that at least one
#      non-placeholder point exists somewhere. This is the meaningful gate:
#      a non-zero total with is_placeholder:true only means "scanner
#      discovered files" — it does NOT mean anything is searchable yet.
#
# What we deliberately do NOT do:
#   * We do not run a vector search. Synthesising a valid 1024-dim bge-m3
#     vector requires the embedder; a zero/random vector produces a
#     dimension-mismatch or a "nearest to origin" answer that is theatre.
#   * We do not hard-code the running image digest — it rotates on every
#     upstream rebuild and a hard-coded expected would produce false
#     failures after every upgrade. Pass --expected-image to opt in.
#   * We do not assert doc_type=file > 0. The file scanner only ingests
#     folders the operator has tagged `vector-index`; before that, file == 0
#     is the EXPECTED state and asserting > 0 would be a false alarm.
#
# Operator tagging (IMPORTANT — the old comment was wrong):
#   Tagging the Nextcloud files ROOT does NOT work — `occ systemtag:add`
#   reports success on the root and the scanner expands nothing. Tag each
#   TOP-LEVEL FOLDER under the user you want indexed; the scanner
#   recursively expands a directly-tagged folder and so covers the whole
#   subtree. The tags in use are:
#     vector-index   — hybrid index (the one that matters)
#     keyword-index  — keyword-only, optional
#     vector-exclude — exclusion list (wired via EXCLUDED_TAGS)
#   Tag example for likivik:
#     occ systemtag:add vector-index --assignable
#     for fid in $(occ user:files:list-folders likivik); do
#       occ systemtag:assign vector-index "$fid"
#     done
#
# Usage:
#   ./scripts/verify-mcp-index.sh [--mcp-url URL] [--qdrant-url URL] \
#       [--collection NAME] [--expected-image REF]
#
# Exit codes:
#   0  PASS  — every required check passed. VERIFY_INDEX_OK printed.
#   1  FAIL  — at least one required check failed. VERIFY_INDEX_FAIL printed.
#   2  USAGE — bad CLI args.
#
# Markers (stable, CI-friendly):
#   VERIFY_INDEX_OK     on full pass
#   VERIFY_INDEX_FAIL   on any required-check failure
#   VERIFY_INDEX_REPORT multi-line body, every line begins with one of:
#     container:   mcp:   qdrant:   counts:   content:
set -euo pipefail

MCP_URL_DEFAULT="http://127.0.0.1:8000"
QDRANT_URL_DEFAULT="http://127.0.0.1:6333"
COLLECTION_DEFAULT="poweredge-bge-m3"

MCP_URL="${MCP_URL:-$MCP_URL_DEFAULT}"
QDRANT_URL="${QDRANT_URL:-$QDRANT_URL_DEFAULT}"
COLLECTION="${COLLECTION:-$COLLECTION_DEFAULT}"
EXPECTED_IMAGE="${EXPECTED_IMAGE:-}"   # optional; pass via env or --expected-image

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mcp-url)          MCP_URL="$2"; shift 2 ;;
    --qdrant-url)       QDRANT_URL="$2"; shift 2 ;;
    --collection)       COLLECTION="$2"; shift 2 ;;
    --expected-image)   EXPECTED_IMAGE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,46p' "$0" | sed 's/^# \{0,1\}//'
      exit 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# doc_types we surface. file + note + deck_card cover the current scanner;
# mail_message + news_item are forward-compatible. Total / placeholder /
# non-placeholder for each is REPORTED. The gate is "≥1 non-placeholder
# point across any doc_type", not "file > 0".
DOC_TYPES=(file note deck_card mail_message news_item)

PASS=0; FAIL=0; REQUIRED_FAIL=0
ok()    { PASS=$((PASS+1));      printf '  [PASS] %s\n' "$*"; }
bad()   { FAIL=$((FAIL+1)); REQUIRED_FAIL=$((REQUIRED_FAIL+1)); printf '  [FAIL] %s\n' "$*" >&2; }
warn()  { printf '  [WARN] %s\n' "$*"; }
report(){ printf '%s: %s\n' "$1" "$2"; }

# Pull a count integer out of a Qdrant `count` response. Empty/missing -> "?".
count_from() {
  local body="$1"
  echo "$body" | sed -n 's/.*"count":\([0-9][0-9]*\).*/\1/p' | head -1
}

# Pull the first `"id":"..."` UUID-ish token out of a Qdrant `scroll` response.
# Empty/missing -> "".
id_from_scroll() {
  local body="$1"
  echo "$body" | grep -o '"id":"[a-fA-F0-9-]\+"' | head -1 || true
}

# ─── 1. Container ─────────────────────────────────────────────────────────
echo '--- container ---'
SVC_STATE="inactive"
if systemctl is-active --quiet nextcloud-mcp.service 2>/dev/null; then
  SVC_STATE="active"
  ok "nextcloud-mcp.service is active"
else
  bad "nextcloud-mcp.service is NOT active (systemctl status nextcloud-mcp.service)"
fi

# Read the image straight from the live systemd unit's ExecStart. This works
# regardless of where the quadlet ends up on disk — podman args are the
# source of truth.
IMAGE_REF=""
if [[ "$SVC_STATE" == "active" ]]; then
  EXEC_START=$(systemctl show nextcloud-mcp.service -p ExecStart --value 2>/dev/null || true)
  if [[ -n "$EXEC_START" ]]; then
    # ExecStart for a quadlet-wrapped podman container embeds the image ref
    # (e.g. ghcr.io/pi0n00r/nextcloud-mcp-server:v1.9.9.3@sha256:...). It is
    # always the LAST positional argument of argv[]. Extract just argv[]'s
    # contents (terminated by the next top-level `;`) and take the last
    # whitespace-separated token — this sidesteps false matches against
    # `--env FOO=http://host:port` style arguments.
    IMAGE_REF=$(echo "$EXEC_START" \
      | grep -oE 'argv\[\]=[^;]+' \
      | head -1 \
      | sed 's/^argv\[\]=//' \
      | awk '{print $NF}' \
      || true)
  fi
fi
if [[ -n "$IMAGE_REF" ]]; then
  report "container" "running image = $IMAGE_REF"
  if [[ -n "$EXPECTED_IMAGE" ]]; then
    if [[ "$IMAGE_REF" == *"$EXPECTED_IMAGE"* ]]; then
      ok "running image matches EXPECTED_IMAGE ($EXPECTED_IMAGE)"
    else
      bad "running image $IMAGE_REF does not contain EXPECTED_IMAGE"
    fi
  else
    report "container" "EXPECTED_IMAGE not set; image match check skipped (set --expected-image or EXPECTED_IMAGE to opt in)"
  fi
else
  warn "could not parse a running image out of systemctl show (svc state: $SVC_STATE)"
fi

# Confirm the sops-injected creds file is present (regression check that the
# rename didn't silently drop NEXTCLOUD_HOST). Read-only — we never print
# its contents. The file is mode 600 root-owned, so when run as a
# non-root operator we can only see that it exists; we still confirm its
# shape when run with read access.
if [[ -e /run/nextcloud-mcp.env ]]; then
  if [[ -r /run/nextcloud-mcp.env ]] && grep -q '^NEXTCLOUD_HOST=' /run/nextcloud-mcp.env; then
    ok "/run/nextcloud-mcp.env exists and carries NEXTCLOUD_HOST (sops creds present)"
  elif [[ -r /run/nextcloud-mcp.env ]]; then
    warn "/run/nextcloud-mcp.env exists but has no NEXTCLOUD_HOST — check the secrets template"
  else
    ok "/run/nextcloud-mcp.env exists (mode 600; non-root cannot inspect, but presence confirms template)"
  fi
else
  warn "/run/nextcloud-mcp.env missing — secrets template did not provision it"
fi

# ─── 2. MCP streamable-HTTP handshake ─────────────────────────────────────
echo '--- mcp ---'
# This server speaks MCP streamable-HTTP at /mcp and has no /health. A
# healthy server returns HTTP 200 with an `Mcp-Session-Id` response header
# and an SSE-framed body that contains a `serverInfo` object (per the
# MCP spec). We DO NOT pin a specific server version.
INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"1"}}}'
INIT_RAW=$(curl -sS -i --max-time 10 \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -X POST "$MCP_URL/mcp" \
  --data "$INIT_BODY" 2>/dev/null || echo '')
INIT_STATUS=$(echo "$INIT_RAW" | head -1 | awk '{print $2}')
INIT_HAS_HEADER=$(echo "$INIT_RAW" | grep -ic '^mcp-session-id:' || true)
INIT_HAS_SERVERINFO=$(echo "$INIT_RAW" | grep -c '"serverInfo"' || true)

if [[ "$INIT_STATUS" == "200" ]] \
   && [[ "${INIT_HAS_HEADER:-0}" -ge 1 ]] \
   && [[ "${INIT_HAS_SERVERINFO:-0}" -ge 1 ]]; then
  SESSION_ID=$(echo "$INIT_RAW" | awk 'tolower($1)=="mcp-session-id:" {sub(/\r$/,""); print $2}' | head -1)
  ok "MCP initialize handshake → HTTP 200 + Mcp-Session-Id + serverInfo (session ${SESSION_ID:0:8}…)"
else
  bad "MCP initialize handshake failed (status=${INIT_STATUS:-?} session-id=${INIT_HAS_HEADER:-0} serverInfo=${INIT_HAS_SERVERINFO:-0})"
  report "mcp" "POST $MCP_URL/mcp returned no recognisable initialize response"
fi

# ─── 3. Qdrant collection health ──────────────────────────────────────────
echo '--- qdrant ---'
COLL_INFO=$(curl -sS --max-time 5 "$QDRANT_URL/collections/$COLLECTION" 2>/dev/null || echo '')
# Qdrant wraps the collection health in result.status and a top-level
# request status=ok. We must pick the FIRST `status` (the collection one),
# not the top-level one — a naive `.*status..."X"` regex would greedy-match
# the request status instead. Pick the first `"status":"<word>"` literally.
COLL_STATUS=$(echo "$COLL_INFO" | { grep -oE '"status":"[a-z]+"' || true; } | head -1 | sed -n 's/"status":"\([a-z]*\)"/\1/p' || true)
if [[ "$COLL_STATUS" == "green" ]]; then
  ok "Qdrant collection $COLLECTION exists and is green"
elif [[ -z "$COLL_INFO" ]]; then
  bad "Qdrant at $QDRANT_URL did not respond for /collections/$COLLECTION"
elif [[ -n "$COLL_STATUS" ]]; then
  bad "Qdrant collection $COLLECTION status=$COLL_STATUS"
else
  bad "Qdrant response unrecognised: $COLL_INFO"
fi

# ─── 4. Per-doc_type counts (placeholder vs real) ────────────────────────
echo '--- counts ---'
declare -A TOTAL PLACEHOLDER NONPH
ANY_NONPH=0
for dt in "${DOC_TYPES[@]}"; do
  TOTAL[$dt]="?"
  PLACEHOLDER[$dt]="?"
  NONPH[$dt]="?"

  T_BODY=$(curl -sS --max-time 5 \
    -H 'Content-Type: application/json' \
    -X POST "$QDRANT_URL/collections/$COLLECTION/points/count" \
    -d "{\"filter\":{\"must\":[{\"key\":\"doc_type\",\"match\":{\"value\":\"$dt\"}}]},\"exact\":true}" \
    2>/dev/null || echo '')
  TOTAL[$dt]="$(count_from "$T_BODY")"

  P_BODY=$(curl -sS --max-time 5 \
    -H 'Content-Type: application/json' \
    -X POST "$QDRANT_URL/collections/$COLLECTION/points/count" \
    -d "{\"filter\":{\"must\":[{\"key\":\"doc_type\",\"match\":{\"value\":\"$dt\"}},{\"key\":\"is_placeholder\",\"match\":{\"value\":true}}]},\"exact\":true}" \
    2>/dev/null || echo '')
  PLACEHOLDER[$dt]="$(count_from "$P_BODY")"

  NP_BODY=$(curl -sS --max-time 5 \
    -H 'Content-Type: application/json' \
    -X POST "$QDRANT_URL/collections/$COLLECTION/points/count" \
    -d "{\"filter\":{\"must\":[{\"key\":\"doc_type\",\"match\":{\"value\":\"$dt\"}},{\"key\":\"is_placeholder\",\"match\":{\"value\":false}}]},\"exact\":true}" \
    2>/dev/null || echo '')
  NONPH[$dt]="$(count_from "$NP_BODY")"

  # arithmetic only if all three are integers
  if [[ "${TOTAL[$dt]}" =~ ^[0-9]+$ && "${PLACEHOLDER[$dt]}" =~ ^[0-9]+$ && "${NONPH[$dt]}" =~ ^[0-9]+$ ]]; then
    if (( TOTAL[$dt] != PLACEHOLDER[$dt] + NONPH[$dt] )); then
      warn "doc_type=$dt counts inconsistent: total=${TOTAL[$dt]} != placeholder+non-placeholder (${PLACEHOLDER[$dt]}+${NONPH[$dt]}) — some points may carry no is_placeholder flag"
    fi
  fi
  if [[ "${NONPH[$dt]}" =~ ^[0-9]+$ ]] && (( NONPH[$dt] > 0 )); then
    ANY_NONPH=1
  fi
  report "counts" "doc_type=$dt total=${TOTAL[$dt]} placeholder=${PLACEHOLDER[$dt]} non_placeholder=${NONPH[$dt]}"
done

# ─── 5. Real-content assertion ────────────────────────────────────────────
echo '--- content ---'
# Scroll ONE real (non-placeholder) file point. Getting a non-empty result
# is direct evidence that the scanner has actually embedded at least one
# file — placeholder points don't count.
SCROLL_BODY='{"filter":{"must":[{"key":"doc_type","match":{"value":"file"}},{"key":"is_placeholder","match":{"value":false}}]},"limit":1,"with_payload":true}'
SCROLL_RESP=$(curl -sS --max-time 5 \
  -H 'Content-Type: application/json' \
  -X POST "$QDRANT_URL/collections/$COLLECTION/points/scroll" \
  --data "$SCROLL_BODY" 2>/dev/null || echo '')
SCROLL_ID=$(id_from_scroll "$SCROLL_RESP")
if [[ -n "$SCROLL_ID" ]]; then
  ok "file scroll returned at least one non-placeholder point ($SCROLL_ID)"
else
  report "content" "file scroll returned no non-placeholder point (response=$SCROLL_RESP)"
fi

# Gate: the whole pipeline is meaningful iff at least one non-placeholder
# point exists across ANY doc_type (notes/deck qualify — they were the
# baseline before the file scanner was enabled). file > 0 is NOT the gate.
if (( ANY_NONPH == 1 )); then
  ok "≥1 non-placeholder point exists across ${DOC_TYPES[*]} — indexing is meaningful"
else
  bad "no non-placeholder points found in any of ${DOC_TYPES[*]} — only placeholders are indexed, nothing is searchable"
fi

# ─── Summary ────────────────────────────────────────────────────────────────
echo '--- summary ---'
printf 'PASS=%d FAIL=%d (required=%d)\n' "$PASS" "$FAIL" "$REQUIRED_FAIL"
if [[ "$REQUIRED_FAIL" -eq 0 ]]; then
  echo "VERIFY_INDEX_OK"
  exit 0
else
  echo "VERIFY_INDEX_FAIL"
  exit 1
fi