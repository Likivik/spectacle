#!/usr/bin/env python3
import json, urllib.request, urllib.parse, sys

BASE = "http://poweredge.oryx-galaxy.ts.net:8090/etapi"
TOK = "spWWWRpvMQHa_ltHXnRx80gjCEngzjcD/gKoDBxVVsol2M3ZAR6n6jgo="

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": TOK})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def note(nid):
    return get(f"/notes/{urllib.parse.quote(nid)}")

def search(q, **params):
    qs = {"search": q}
    qs.update(params)
    return get("/notes?" + urllib.parse.urlencode(qs))["results"]

def walk(nid, depth=0, out=None, maxdepth=99):
    try:
        n = note(nid)
    except Exception as e:
        return out
    for cid in n.get("childNoteIds", []):
        if cid == "_hidden":
            continue
        try:
            c = note(cid)
        except Exception:
            continue
        out.append((depth, cid, c.get("type"), c["title"]))
        if depth + 1 <= maxdepth:
            walk(cid, depth+1, out, maxdepth)
    return out

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "root"
    out = []
    walk(root, 0, out)
    for d, nid, t, title in out:
        print(f'{"  "*d}[{t}] {nid}  {title}')
    print(f"\nTOTAL: {len(out)}")
