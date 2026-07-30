#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ボス指摘の幾何的整合性を全数測定
 G1 店が道路の帯の上に乗っている
 G2 店が2つ並んで道路の上
 G3 信号が交差点にない
 G4 交差点に信号がない (OSMに信号があるのに)
 G5 ★とラベルの対応が曖昧
 G6 向かい合い関係の破れ
"""
import io, json, math, re, os, sys, collections

SC = os.path.dirname(os.path.abspath(__file__))
ROOT = r"C:\Users\paipa\nakayama-guidemap"
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "index.html")
OUT = []


def P(*a):
    OUT.append(" ".join(str(x) for x in a))


src = io.open(TARGET, encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
sh, roads, sig = G["shops"], G["roads"], G["signals"]

# 描画幅 (template の実値をHTMLから読む)
WID = {}
for m in re.finditer(r"class:'(road-[a-z-]+)-f', 'stroke-width':([\d.]+)", src):
    WID[m.group(1)] = float(m.group(2))
CLSMAP = {"minor": "road-minor", "mid": "road-mid", "major": "road-major"}
SPINE_W = WID.get("road-main", 13.0)


def road_fill_w(r):
    if r.get("guide_spine"):
        return SPINE_W
    return WID.get(CLSMAP.get(r["cls"], "road-mid"), 9.0)


def seg_dist_pt(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def dist_to_road(px, py, r):
    return min(seg_dist_pt(px, py, a[0], a[1], b[0], b[1]) for a, b in zip(r["pts"], r["pts"][1:]))


P("=" * 76)
P("幾何整合性 診断  対象:", os.path.basename(TARGET))
P("=" * 76)
P("道路の塗り幅:", json.dumps({**WID, "road-main(spine)": SPINE_W}, ensure_ascii=False))
P("店 %d / 道路 %d / 信号 %d" % (len(sh), len(roads), len(sig)))

# ---------- G1: 店が道路の帯の上 ----------
P("")
P("【G1】店が道路の帯の上に乗っている (中心線からの距離 < 帯の片側幅)")
P("      建物は道路の外側にあるので、これは物理的にあり得ない配置")
g1 = []
for s in sh:
    worst = None
    for r in roads:
        d = dist_to_road(s["x"], s["y"], r)
        half = road_fill_w(r) / 2.0
        if d < half:
            over = half - d
            if worst is None or over > worst[0]:
                worst = (over, r.get("name") or ("(無名 " + r["cls"] + ")"), d, half)
    if worst:
        g1.append((worst[0], s["name"], worst[1], worst[2], worst[3]))
g1.sort(reverse=True)
P("      件数: %d / %d 店" % (len(g1), len(sh)))
for over, nm, rn, d, half in g1:
    P("        %5.1fm 食い込み  %-24s ← %s (中心から%.1fm / 片側%.1fm)" % (over, nm, rn, d, half))

# ---------- G1b: ★の絵が道路にかかる ----------
P("")
P("【G1b】★の絵 (地図空間で19.3m幅・半径9.65m) が道路の帯にかかる")
g1b = []
STAR_R = 9.65
for s in sh:
    for r in roads:
        d = dist_to_road(s["x"], s["y"], r)
        if d < road_fill_w(r) / 2.0 + STAR_R:
            g1b.append(s["name"])
            break
P("      件数: %d / %d 店" % (len(g1b), len(sh)))

# ---------- G2: 2店が並んで道路上 ----------
P("")
P("【G2】2店が並んで道路の帯の上 (両方G1違反で、互いに30m以内)")
g2 = []
names1 = {t[1] for t in g1}
lst = [s for s in sh if s["name"] in names1]
for i in range(len(lst)):
    for j in range(i + 1, len(lst)):
        a, b = lst[i], lst[j]
        d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        if d < 30:
            g2.append((d, a["name"], b["name"]))
g2.sort()
P("      組数: %d" % len(g2))
for d, a, b in g2:
    P("        %5.1fm  %s ⇔ %s" % (d, a, b))

# ---------- 交差点の抽出 ----------
def segs(r):
    return list(zip(r["pts"], r["pts"][1:]))


def inter(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -0.001 <= t <= 1.001 and -0.001 <= u <= 1.001:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


nodes = []
for i in range(len(roads)):
    for j in range(i + 1, len(roads)):
        for a, b in segs(roads[i]):
            for c, e in segs(roads[j]):
                p = inter(a, b, c, e)
                if p:
                    nodes.append(p)
# 近接をまとめる
merged = []
for p in nodes:
    hit = False
    for q in merged:
        if math.hypot(p[0] - q[0], p[1] - q[1]) < 12:
            hit = True
            break
    if not hit:
        merged.append(p)

P("")
P("【G3】信号が交差点にない")
P("      描画されている道路同士の交点: %d 箇所 (12m以内をまとめた後)" % len(merged))
g3 = []
for x, y in sig:
    dmin = min((math.hypot(x - q[0], y - q[1]) for q in merged), default=1e9)
    if dmin > 20:
        g3.append((dmin, x, y))
g3.sort(reverse=True)
P("      交点から20m以上離れている信号: %d / %d 基" % (len(g3), len(sig)))
for d, x, y in g3:
    P("        最近交点まで %6.1fm  信号(%.1f, %.1f)" % (d, x, y))

# ---------- G4: OSMの信号との突合 ----------
P("")
P("【G4】OSMの実信号と本番の信号の突合")
try:
    raw = json.load(io.open(os.path.join(ROOT, "tools/v2-build/signals_raw.json"), encoding="utf-8"))
    els = raw.get("elements", raw)
    ts = [e for e in els if (e.get("tags") or {}).get("highway") == "traffic_signals"]
    p = G["meta"]["proj"]
    R = math.radians(p["rot_deg"]); ca, sa = math.cos(R), math.sin(R)
    minx, miny = G["meta"]["minx"], G["meta"]["miny"]

    def proj(lat, lng):
        mx = (lng - p["lon0"]) * p["cosf"] * 111320.0
        my = (lat - p["lat0"]) * 111320.0
        return mx * ca + my * sa - minx, mx * sa - my * ca - miny

    W, H = G["meta"]["W"], G["meta"]["H"]
    inside = []
    for e in ts:
        x, y = proj(e["lat"], e["lon"])
        if -40 <= x <= W + 40 and -40 <= y <= H + 40:
            inside.append((round(x, 1), round(y, 1)))
    P("      OSM traffic_signals: 全%d基 / canvas内 %d基" % (len(ts), len(inside)))
    P("      本番に描いている: %d基" % len(sig))
    missing = [q for q in inside if min((math.hypot(q[0] - x, q[1] - y) for x, y in sig), default=1e9) > 15]
    extra = [(x, y) for x, y in sig if min((math.hypot(q[0] - x, q[1] - y) for q in inside), default=1e9) > 15]
    P("      OSMにあるのに描いていない: %d基" % len(missing))
    for q in missing[:14]:
        P("        (%.1f, %.1f)" % q)
    P("      OSMに無いのに描いている (手置き疑い): %d基" % len(extra))
    for q in extra:
        dmin = min((math.hypot(q[0] - m[0], q[1] - m[1]) for m in merged), default=1e9)
        P("        (%.1f, %.1f)  最近交点まで %.1fm" % (q[0], q[1], dmin))
except Exception as e:
    P("      突合失敗:", type(e).__name__, e)

# ---------- G5: ★とラベルの対応 ----------
P("")
P("【G5】どの★がどのラベルか分からない")
amb = []
for s in sh:
    lx, ly = s.get("lx"), s.get("ly")
    if lx is None:
        continue
    dself = math.hypot(lx - s["x"], ly - s["y"])
    dother = min((math.hypot(lx - o["x"], ly - o["y"]) for o in sh if o is not s), default=1e9)
    if dother < dself:
        amb.append((dself, dother, s["name"]))
amb.sort(key=lambda t: t[1] - t[0])
P("      ラベルが「自分の★」より「他人の★」に近い: %d / %d 店" % (len(amb), len(sh)))
for a, b, n in amb[:16]:
    P("        自分まで%5.1fm / 他人まで%5.1fm  %s" % (a, b, n))

# ---------- G6: 向かい合いの破れ ----------
P("")
P("【G6】バス通りを挟んだ向かい合いの候補と、その通り沿い位置の差")
SP = G["busway"][1]


def sx_at(y):
    best = None
    for (x1, y1), (x2, y2) in zip(SP, SP[1:]):
        lo, hi = min(y1, y2), max(y1, y2)
        if lo <= y <= hi:
            t = 0.0 if abs(y2 - y1) < 1e-9 else (y - y1) / (y2 - y1)
            return x1 + t * (x2 - x1)
        d = min(abs(y - lo), abs(y - hi))
        if best is None or d < best[0]:
            best = (d, x1 if abs(y - y1) < abs(y - y2) else x2)
    return best[1]


band = [s for s in sh if abs(s["x"] - sx_at(s["y"])) < 60]
west = sorted([s for s in band if s["x"] < sx_at(s["y"])], key=lambda s: s["y"])
east = sorted([s for s in band if s["x"] >= sx_at(s["y"])], key=lambda s: s["y"])
P("      バス通り沿い: 西 %d店 / 東 %d店" % (len(west), len(east)))
for w in west:
    cand = min(east, key=lambda e: abs(e["y"] - w["y"]))
    P("        西 %-22s (y%.0f)  ⇔ 東 %-22s (y%.0f)  通り沿いの差 %.1fm"
      % (w["name"], w["y"], cand["name"], cand["y"], abs(cand["y"] - w["y"])))

P("")
P("=" * 76)
P("要約: G1=%d店 / G1b=%d店 / G2=%d組 / G3=%d基 / G5=%d店"
  % (len(g1), len(g1b), len(g2), len(g3), len(amb)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
print("\n".join(OUT))
