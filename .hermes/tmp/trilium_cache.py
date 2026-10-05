#!/usr/bin/env python3
"""Fetch full Trilium tree (titles, type, content length) into a JSON cache."""
import json, urllib.request, urllib.parse, sys, re
from concurrent.futures import ThreadPoolExecutor

BASE = "http://poweredge.oryx-galaxy.ts.net:8090/etapi"
TOK = "spWWWRpvMQHa_ltHXnRx80gjCEngzjcD/gKoDBxVVsol2M3ZAR6n6jgo="
CACHE = "/Storage/Git/spectacle/.hermes/tmp/trilium_cache.json"

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": TOK})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def content_len(nid):
    req = urllib.request.Request(BASE + f"/notes/{urllib.parse.quote(nid)}/content", headers={"Authorization": TOK})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            return len(data)
    except Exception as e:
        return -1

def build(nid, depth, parent, out):
    try:
        n = get(f"/notes/{urllib.parse.quote(nid)}")
    except Exception:
        return
    for cid in n.get("childNoteIds", []):
        if cid == "_hidden":
            continue
        try:
            c = get(f"/notes/{urllib.parse.quote(cid)}")
        except Exception:
            continue
        out.append({"id": cid, "title": c["title"], "type": c.get("type"),
                    "parent": nid, "depth": depth,
                    "children": len(c.get("childNoteIds", []))})
        build(cid, depth+1, nid, out)

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "root"
    out = []
    build(root, 1, "root", out)
    ids = [n["id"] for n in out]
    with ThreadPoolExecutor(max_workers=16) as ex:
        lens = list(ex.map(content_len, ids))
    for n, l in zip(out, lens):
        n["clen"] = l
    json.dump(out, open(CACHE, "w"), ensure_ascii=False, indent=1)
    print(f"notes={len(out)} -> {CACHE}")
