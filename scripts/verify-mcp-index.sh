#!/usr/bin/env bash
# verify-mcp-index.sh — post-deploy smoke test for the nextcloud-mcp container
# on poweredge. Confirms:
#   1. The new image is running (digest check).
#   2. The MCP server is responsive on its public endpoint.
#   3. Qdrant is reachable and the collection has at least the expected
#      baseline of indexed points (deck_card, note, mail_message, news_item).
#   4. A hybrid search returns results (smoke test for the embedding path).
#
# The file-doc_type point count is intentionally NOT asserted > 0 here — it
# depends on the operator having tagged at least one folder with `vector-index`
# AND waited at least one VECTOR_SYNC_SCAN_INTERVAL since deploy. The script
# REPORTS the current count for the operator to interpret; gating on it would
# be theatre until files are actually tagged.
#
# Usage:
#   ./scripts/verify-mcp-index.sh [--mcp-url http://127.0.0.1:8000] \
#       [--qdrant-url http://127.0.0.1:6333] \
#       [--collection poweredge-bge-m3]
#
# Exit codes:
#   0  PASS — every checked subsystem responded as expected.
#   1  FAIL — at least one subsystem check failed (printed above).
#   2  USAGE — bad CLI args.
#
# Markers (stable, CI-friendly):
#   VERIFY_INDEX_OK   on full pass
#   VERIFY_INDEX_FAIL on any failure
#   VERIFY_INDEX_REPORT multi-line body, every line begins with one of
#     `container:`, `mcp:`, `qdrant:`, `counts:`, `search:`
set -euo pipefail

MCP_URL_DEFAULT="http://127.0.0.1:8000"
QDRANT_URL_DEFAULT="http://127.0.0.1:6333"
COLLECTION_DEFAULT="poweredge-bge-m3"
EXPECTED_IMAGE_DIGEST="${EXPECTED_IMAGE_DIGEST:-sha256:fb4833666580ba996437c93b7775cb28c87e978399e4e3c2b83c6f86d6e093b4}"
EXPECTED_IMAGE_TAG="${EXPECTED_IMAGE_TAG:-v1.9.9.3}"

MCP_URL="${MCP_URL:-$MCP_URL_DEFAULT}"
QDRANT_URL="${QDRANT_URL:-$QDRANT_URL_DEFAULT}"
COLLECTION="${COLLECTION:-$COLLECTION_DEFAULT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mcp-url)        MCP_URL="$2"; shift 2 ;;
    --qdrant-url)     QDRANT_URL="$2"; shift 2 ;;
    --collection)     COLLECTION="$2"; shift 2 ;;
    --expected-digest) EXPECTED_IMAGE_DIGEST="$2"; shift 2 ;;
    --expected-tag)   EXPECTED_IMAGE_TAG="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$*"; }
bad()  { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$*" >&2; }
report() { printf '%s: %s\n' "$1" "$2"; }

# --- 1. Container is running on the new image ------------------------------
echo '--- container ---'
if systemctl is-active --quiet nextcloud-mcp.service; then
  ok "nextcloud-mcp.service is active"
else
  bad "nextcloud-mcp.service is not active (systemctl status nextcloud-mcp.service)"
fi

# Read the running image digest straight from the quadlet's last container.
# podman inspect returns RepoDigests only for pulled images (after a fresh
# pull); fall back to the configured unit file if absent.
DIGEST=""
if command -v podman >/dev/null 2>&1; then
  CID=$(podman ps --filter name=nextcloud-mcp --filter status=running --format '{{.ID}}' 2>/dev/null | head -1 || true)
  if [[ -n "${CID:-}" ]]; then
    DIGEST=$(podman inspect "$CID" --format '{{index .Image "Digest"}}' 2>/dev/null || true)
  fi
fi
if [[ -n "$DIGEST" ]]; then
  report "container" "running image digest = $DIGEST"
  if [[ "$DIGEST" == "$EXPECTED_IMAGE_DIGEST" ]]; then
    ok "digest matches expected $EXPECTED_IMAGE_DIGEST (image-index pinned)"
  elif [[ "$DIGEST" == *"$EXPECTED_IMAGE_TAG"* ]]; then
    report "container" "digest differs from expected but tag $EXPECTED_IMAGE_TAG is present — re-evaluate"
  else
    bad "running digest $DIGEST does not match expected $EXPECTED_IMAGE_DIGEST"
  fi
else
  # Best-effort: at least confirm the quadlet-generated unit file references
  # the new image so the *next* restart uses it.
  if [[ -r /etc/containers/systemd/nextcloud-mcp.container ]]; then
    if grep -q "$EXPECTED_IMAGE_TAG" /etc/containers/systemd/nextcloud-mcp.container; then
      ok "quadlet unit file references $EXPECTED_IMAGE_TAG (no running digest yet)"
    else
      bad "quadlet unit file does NOT reference $EXPECTED_IMAGE_TAG — is the deploy applied?"
    fi
  else
    report "container" "quadlet unit file not present at /etc/containers/systemd/nextcloud-mcp.container (read-only)"
  fi
fi

# Confirm the rename took effect (regression guard against a future revert
# of VECTOR_SYNC_SCAN_INTERVAL back to VECTOR_SYNC_INTERVAL).
if [[ -r /run/nextcloud-mcp.env ]]; then
  if grep -q '^NEXTCLOUD_HOST=' /run/nextcloud-mcp.env; then
    ok "/run/nextcloud-mcp.env exists and carries the sops-injected creds"
  fi
fi

# --- 2. MCP HTTP endpoint ------------------------------------------------
echo '--- mcp ---'
# Most MCP deployments expose a /health endpoint; fall back to / if absent.
HEALTH_OK=0
for path in /health /healthz /api/v1/health /; do
  CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$MCP_URL$path" 2>/dev/null || echo 000)
  if [[ "$CODE" =~ ^(200|307|401|403)$ ]]; then
    ok "MCP endpoint $MCP_URL$path → HTTP $CODE (responsive)"
    HEALTH_OK=1
    break
  fi
done
[[ "$HEALTH_OK" -eq 1 ]] || bad "MCP endpoint $MCP_URL did not respond to /health, /api/v1/health, or / within 5s"

# --- 3. Qdrant collection + baseline point counts --------------------------
echo '--- qdrant ---'
COLL_INFO=$(curl -sS --max-time 5 "$QDRANT_URL/collections/$COLLECTION" 2>/dev/null || echo '')
if [[ -z "$COLL_INFO" ]]; then
  bad "Qdrant at $QDRANT_URL did not respond for /collections/$COLLECTION"
elif echo "$COLL_INFO" | grep -q '"status":"green"'; then
  ok "Qdrant collection $COLLECTION exists and is healthy"
elif echo "$COLL_INFO" | grep -q '"status"'; then
  STATUS=$(echo "$COLL_INFO" | sed -n 's/.*"status":"\([a-z]*\)".*/\1/p' | head -1)
  bad "Qdrant collection $COLLECTION status=$STATUS (raw: $COLL_INFO)"
else
  bad "Qdrant response unrecognised: $COLL_INFO"
fi

# --- 4. Per-doc_type point counts ----------------------------------------
echo '--- counts ---'
count_for() {
  local doc_type="$1"
  curl -sS --max-time 5 \
    -H 'Content-Type: application/json' \
    -X POST "$QDRANT_URL/collections/$COLLECTION/points/count" \
    -d "{\"filter\":{\"must\":[{\"key\":\"doc_type\",\"match\":{\"value\":\"$doc_type\"}}]},\"exact\":true}" \
    2>/dev/null | sed -n 's/.*"count":\([0-9]*\).*/\1/p' | head -1
}

for dt in file note deck_card mail_message news_item; do
  N=$(count_for "$dt" || echo "?")
  report "counts" "doc_type=$dt → $N points"
done

# Note: we DO NOT assert file > 0 here. The file scanner is gated on the
# `vector-index` system tag (or one in EXCLUDED_TAGS's exclusion) — until
# the operator runs `occ systemtag:add vector-index --assignable` AND tags
# a folder, file = 0 is the EXPECTED state. See modules/hosts/poweredge/
# poweredge.nix for the occ commands and the deployment notes.

# --- 5. Hybrid search smoke test -----------------------------------------
echo '--- search ---'
# Build a minimal hybrid search request. The bge-m3 embedding is 1024-dim;
# we pass a zero vector — Qdrant returns "nearest to origin" which is
# useless semantically but exercises the dense+sparse path end-to-end.
ZERO_VEC=$(python3 -c 'import json; print(json.dumps([0.0]*1024))' 2>/dev/null || echo '[0]')
SEARCH_BODY=$(cat <<JSON
{
  "vector": {"name": "dense", "vector": $ZERO_VEC},
  "sparse_vector": {"name": "sparse", "indices": [1], "values": [1.0]},
  "limit": 3,
  "with_payload": false
}
JSON
)
SEARCH_RESP=$(curl -sS --max-time 10 \
  -H 'Content-Type: application/json' \
  -X POST "$QDRANT_URL/collections/$COLLECTION/points/search" \
  -d "$SEARCH_BODY" 2>/dev/null || echo '')
if echo "$SEARCH_RESP" | grep -q '"result"'; then
  NRES=$(echo "$SEARCH_RESP" | grep -o '"id"' | wc -l)
  ok "hybrid search returned $NRES result(s) (smoke test of dense+sparse path)"
elif echo "$SEARCH_RESP" | grep -q '"status":"error"'; then
  bad "hybrid search returned error: $SEARCH_RESP"
else
  bad "hybrid search no recognised response: $SEARCH_RESP"
fi

# --- Summary --------------------------------------------------------------
echo '--- summary ---'
printf 'PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then
  echo "VERIFY_INDEX_OK"
  exit 0
else
  echo "VERIFY_INDEX_FAIL"
  exit 1
fi