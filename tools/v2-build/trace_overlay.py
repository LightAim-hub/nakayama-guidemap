#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""トレース台: Googleマップを下に敷いて、うちの店・道路・信号を重ねてズレを炙り出す。
Googleマップは「検証のための参照」としてのみ使用。座標は焼き込まない・成果物に含めない。
(Google Maps Platform 3.2.3/3.2.4 を踏まえ、内部QAの目視参照に限定)

usage: python trace_overlay.py <lat> <lng> <zoom> <out.png> [label]
"""
import io, json, math, os, re, sys
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

ROOT = r"C:\Users\paipa\nakayama-guidemap"
SC = os.path.dirname(os.path.abspath(__file__))
LAT, LNG, Z = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
OUTP = sys.argv[4]
TAG = sys.argv[5] if len(sys.argv) > 5 else ""
VW, VH = 1200, 1200

# ---------- 1. GEO を読む ----------
src = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
p = G["meta"]["proj"]
minx, miny = G["meta"]["minx"], G["meta"]["miny"]
ROT = math.radians(p["rot_deg"])
CA, SA = math.cos(ROT), math.sin(ROT)


def unproject(x, y):
    """GEOのx,y (回転+オフセット済み) → lat,lng"""
    gx, gy = x + minx, y + miny
    # 回転を戻す
    mx = gx * CA + gy * SA
    my = gx * SA - gy * CA
    lng = p["lon0"] + mx / (111320.0 * p["cosf"])
    lat = p["lat0"] + my / 111320.0
    return lat, lng


# ---------- 2. Web Mercator (Googleマップと同じ) ----------
WORLD = 256.0 * (2 ** Z)


def merc(lat, lng):
    x = (lng + 180.0) / 360.0 * WORLD
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * WORLD
    return x, y


CX, CY = merc(LAT, LNG)
MPP = 156543.03392 * math.cos(math.radians(LAT)) / (2 ** Z)   # metres per pixel


def to_screen(lat, lng):
    x, y = merc(lat, lng)
    return (x - CX) + VW / 2.0, (y - CY) + VH / 2.0


# ---------- 3. Googleマップを撮る ----------
GMAP = os.path.join(SC, "_trace_gmap.png")
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": VW, "height": VH})
    pg.goto("https://www.google.com/maps/@%.7f,%.7f,%dz" % (LAT, LNG, Z), wait_until="load")
    pg.wait_for_timeout(11000)
    # UIを消して地図だけにする
    pg.add_style_tag(content="""
      #omnibox-container,#watermark,#vasquette,.app-viewer-container,#minimap,
      .scene-footer-container,#assistive-chips,.widget-zoom-controls,
      #titlecard,.searchbox,#gb,.app-vertical-widget-holder,#runway-expand-button,
      .watermark,.gm-style-cc,#content-container>div:not(#pane) {display:none !important;}
    """)
    pg.wait_for_timeout(1200)
    pg.screenshot(path=GMAP)
    br.close()

base = Image.open(GMAP).convert("RGB")

# ---------- 4. うちのデータを重ねる ----------
ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
d = ImageDraw.Draw(ov)

# 道路 (うちが描いている62本)
for r in G["roads"]:
    pts = []
    for x, y in r["pts"]:
        la, ln = unproject(x, y)
        pts.append(to_screen(la, ln))
    w = 13.0 if r.get("guide_spine") else {"major": 12.0, "mid": 9.0, "minor": 5.0}.get(r["cls"], 9.0)
    px = max(1, int(round(w / MPP)))
    if len(pts) > 1:
        d.line(pts, fill=(0, 120, 255, 90), width=px, joint="curve")

# 信号
for x, y in G["signals"]:
    la, ln = unproject(x, y)
    sx, sy = to_screen(la, ln)
    d.ellipse([sx - 9, sy - 9, sx + 9, sy + 9], outline=(255, 0, 255, 255), width=4)
    d.line([sx - 13, sy, sx + 13, sy], fill=(255, 0, 255, 220), width=2)
    d.line([sx, sy - 13, sx, sy + 13], fill=(255, 0, 255, 220), width=2)

# 店 (★の実サイズ 19.3m の円 + 中心の十字)
labels = []
for s in G["shops"]:
    la, ln = unproject(s["x"], s["y"])
    sx, sy = to_screen(la, ln)
    if not (-60 <= sx <= VW + 60 and -60 <= sy <= VH + 60):
        continue
    rr = (19.3 / 2.0) / MPP
    d.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], outline=(220, 0, 0, 200), width=3)
    d.line([sx - 7, sy, sx + 7, sy], fill=(220, 0, 0, 255), width=3)
    d.line([sx, sy - 7, sx, sy + 7], fill=(220, 0, 0, 255), width=3)
    labels.append((sx, sy, s["name"]))

out = Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
d2 = ImageDraw.Draw(out)
for sx, sy, nm in labels:
    d2.text((sx + 10, sy - 6), nm, fill=(150, 0, 0))
d2.rectangle([0, 0, 560, 46], fill=(255, 255, 255))
d2.text((8, 6), "TRACE  %s  center=%.6f,%.6f  z=%d  %.3f m/px" % (TAG, LAT, LNG, Z, MPP), fill=(0, 0, 0))
d2.text((8, 24), "red=うちの店(円=★の19.3m)  blue=うちの道路  magenta=うちの信号", fill=(0, 0, 0))
out.save(OUTP)
print("saved %s   m/px=%.4f   shops drawn=%d" % (OUTP, MPP, len(labels)))
