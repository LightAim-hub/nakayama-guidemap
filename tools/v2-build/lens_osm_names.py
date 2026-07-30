#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズO — 店名で OSM の実体と突合し、外部の真値で位置を検算する

gate.py は内部整合 (建物/道路/信号) を見る。こちらは「その店が現実にそこにあるか」を
OSM の名前付きPOI (node/way/relation) との名前一致で外部から検算する。
ビルド時に osm:exact で一致した26店以外 (gsi_addr 25 / osm:partial 8 / approx 1) は
外部照合を受けていないので、そこが本命。

usage: python lens_osm_names.py [--fetch] [--json out.json]
  --fetch を付けると Overpass から取得しキャッシュする (既にあれば省略可)
"""
import io, json, math, os, re, sys, time, argparse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

ROOT = os.path.join(os.environ.get("USERPROFILE", ""), "nakayama-guidemap")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm_pois.json")

ap = argparse.ArgumentParser()
ap.add_argument("--fetch", action="store_true")
ap.add_argument("--json")
A = ap.parse_args()

BBOX = "38.2790,140.8280,38.3010,140.8560"

if A.fetch or not os.path.exists(CACHE):
    # 名前付き全件は Overpass が 504 を返すので、店舗性のあるタグに絞る
    KINDS = ["shop", "amenity", "office", "healthcare", "craft",
             "leisure", "tourism", "club", "building:use"]
    parts = []
    for k in KINDS:
        parts.append('  node["name"]["%s"](%s);' % (k, BBOX))
        parts.append('  way["name"]["%s"](%s);' % (k, BBOX))
    q = ("[out:json][timeout:120];\n(\n" + "\n".join(parts)
         + "\n);\nout center tags;")
    print("Overpass から名前付きPOIを取得中...")
    raw = None
    for ep in ("https://overpass-api.de/api/interpreter",
               "https://overpass.kumi.systems/api/interpreter",
               "https://overpass.private.coffee/api/interpreter"):
        try:
            req = urllib.request.Request(ep, data=q.encode("utf-8"),
                                        headers={"User-Agent": "nakayama-guidemap-qa/1.0"})
            raw = urllib.request.urlopen(req, timeout=180).read()
            print("  取得元: %s" % ep)
            break
        except Exception as ex:
            print("  %s → %s" % (ep, ex))
            time.sleep(2)
    if raw is None:
        print("!! Overpass 全滅 — 中止"); sys.exit(2)
    io.open(CACHE, "wb").write(raw)
    print("保存: %s (%d bytes)" % (CACHE, len(raw)))

POI = json.load(io.open(CACHE, encoding="utf-8"))["elements"]
print("OSM 名前付き要素: %d件" % len(POI))

# ---------- GEO ----------
src = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
shops = G["shops"]


def norm(s):
    """突合用の正規化: 空白・記号・全角半角・法人種別語を落とす"""
    s = s or ""
    s = s.translate({ord(c): None for c in " 　・（）()【】〔〕[]「」『』,、.。/-ー―‐"})
    s = s.replace("株式会社", "").replace("有限会社", "").replace("合同会社", "")
    z = "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in s)
    return z.lower()


# OSM 側を正規化名でインデックス
idx = {}
for e in POI:
    nm = e.get("tags", {}).get("name")
    if not nm:
        continue
    lat = e.get("lat") or (e.get("center") or {}).get("lat")
    lon = e.get("lon") or (e.get("center") or {}).get("lon")
    if lat is None or lon is None:
        continue
    idx.setdefault(norm(nm), []).append((nm, lat, lon, e["type"], e["id"],
                                         e.get("tags", {})))

print("正規化後のユニーク名: %d件" % len(idx))


def hav(a, b, c, d):
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))


rows = []
for s in shops:
    n = norm(s["name"])
    cand = idx.get(n)
    how = "完全一致"
    if not cand:
        # 部分一致 (どちらかがどちらかを含む・4文字以上)
        hits = [(k, v) for k, v in idx.items()
                if len(k) >= 4 and len(n) >= 4 and (k in n or n in k)]
        if len(hits) == 1:
            cand = hits[0][1]; how = "部分一致"
        elif len(hits) > 1:
            # 最長一致を採る
            hits.sort(key=lambda kv: -len(kv[0]))
            cand = hits[0][1]; how = "部分一致(複数→最長)"
    if not cand:
        rows.append({"name": s["name"], "src": s.get("src"), "match": None})
        continue
    best = min(cand, key=lambda c: hav(s["lat"], s["lng"], c[1], c[2]))
    d = hav(s["lat"], s["lng"], best[1], best[2])
    rows.append({"name": s["name"], "src": s.get("src"), "match": best[0],
                 "how": how, "dist_m": round(d, 1),
                 "osm": "%s/%s" % (best[3], best[4])})

matched = [r for r in rows if r["match"]]
unmatched = [r for r in rows if not r["match"]]

print("")
print("=" * 78)
print("レンズO — 店名による OSM 外部照合")
print("=" * 78)
print("名前で照合できた店: %d / %d" % (len(matched), len(shops)))
print("")

by_src = {}
for r in matched:
    by_src.setdefault(r["src"], []).append(r["dist_m"])
for k in sorted(by_src):
    v = sorted(by_src[k])
    print("  %-14s %2d件  中央値 %5.1fm  最大 %6.1fm"
          % (k, len(v), v[len(v)//2], v[-1]))

BAD = 30.0
bad = sorted([r for r in matched if r["dist_m"] > BAD], key=lambda r: -r["dist_m"])
print("")
print("外部の真値から %.0fm 超ずれている店: %d件" % (BAD, len(bad)))
for r in bad:
    print("  %-26s %6.1fm  (%s / %s / %s)"
          % (r["name"], r["dist_m"], r["src"], r["how"], r["osm"]))

print("")
print("照合できなかった店 %d件 (OSMに名前が無い = 外部検算できていない):" % len(unmatched))
for r in unmatched:
    print("  %-26s %s" % (r["name"], r["src"]))

print("")
print("=" * 78)
if bad:
    print("レンズO 判定: 要確認 — 外部の真値と%.0fm超ずれる店が%d件" % (BAD, len(bad)))
else:
    print("レンズO 判定: PASS — 照合できた%d店すべて外部の真値と%.0fm以内" % (len(matched), BAD))
print("=" * 78)

if A.json:
    json.dump(rows, io.open(A.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.stdout.flush()
sys.exit(1 if bad else 0)
