#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズR — 「通りが通りとして読めるか」を実測する

gate.py は★が道路に かかるか を歩きズームだけで見る。既定ズーム (最初に見える倍率) では
測っていない。ここでは両ズームで:

  R1 道路の実描画幅 px          (通りとして読める床 = 10px)
  R2 ★の実描画幅 px と 道路幅との比  (★ < 道路幅 でないと通りを覆う)
  R3 ★が道路の帯にかかっている店の数 (地図空間で ★半径 vs 中心線距離)
  R4 ラベル/★が地図の表示域から外れている数
  R5 スクリーンショット (既定 / 歩き)
"""
import io, json, os, math, socket, subprocess, sys, time, argparse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

ROOT = os.path.join(os.environ.get("USERPROFILE", ""), "nakayama-guidemap")
ap = argparse.ArgumentParser()
ap.add_argument("--url")
ap.add_argument("--label", default="build")
ap.add_argument("--shots")
ap.add_argument("--json")
A = ap.parse_args()

ROAD_FLOOR_PX = 10.0     # 通りとして読める最小の描画幅
STAR_ROAD_MAX = 0.60     # ★の幅 / 道路の幅 の上限

url, srv = A.url, None
if not url:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d/index.html" % port
    ok = False
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=1).read(1); ok = True; break
        except Exception:
            time.sleep(1)
    if not ok:
        srv.terminate(); print("!! サーバ起動失敗"); sys.exit(2)

JS = r"""() => {
  const svg = document.getElementById('map');
  const m = svg.getScreenCTM();
  const s0 = Math.hypot(m.a, m.b);
  const vp = document.getElementById('viewport').getBoundingClientRect();

  // 道路の実描画幅 (stroke-width * 倍率)
  const roadW = {};
  for (const cls of ['road-main-f','road-main-c','road-major-f','road-mid-f','road-minor-f']) {
    const el = document.querySelector('.' + cls);
    if (el) roadW[cls] = +(parseFloat(getComputedStyle(el).strokeWidth) * s0).toFixed(2);
  }

  const rows = [...document.querySelectorAll('g.hit')].map(h => {
    const i = +h.dataset.i, sh = GEO.shops[i];
    const st = h.querySelector('.star');
    const t  = h.querySelector('text.shoplabel');
    const sr = st ? st.getBoundingClientRect() : null;
    const tr = t  ? t.getBoundingClientRect()  : null;
    const shown = !!(t && getComputedStyle(t).display !== 'none'
                       && +getComputedStyle(t).opacity > .05 && tr && tr.width > 1);
    const inVp = sr ? (sr.left >= vp.left - 1 && sr.right  <= vp.right + 1 &&
                       sr.top  >= vp.top  - 1 && sr.bottom <= vp.bottom + 1) : false;
    return {i, name: sh.name, voices: !!(sh.voices && sh.voices.length),
            starPx: sr ? +sr.width.toFixed(2) : 0,
            starMapM: sr ? +(sr.width / s0).toFixed(2) : 0,
            labelShown: shown,
            labelInVp: tr ? (tr.left >= vp.left - 1 && tr.right <= vp.right + 1) : false,
            starInVp: inVp, x: sh.x, y: sh.y};
  });
  return {pxPerMeter: +s0.toFixed(4), roadW, rows,
          vp: {w: +vp.width.toFixed(0), h: +vp.height.toFixed(0)}};
}"""

def measure(pg, want=None):
    if want:
        w = 390 / want
        got = None
        for _ in range(6):
            pg.evaluate("v=>document.getElementById('map').setAttribute('viewBox',v)",
                        "%f %f %f %f" % (400, 700, w, w * 844 / 390))
            pg.wait_for_timeout(300)
            got = pg.evaluate("()=>{const s=document.getElementById('map').getScreenCTM();"
                              "return Math.hypot(s.a,s.b);}")
            if abs(got - want) / want < 0.02:
                break
            w = w * got / want
    return pg.evaluate(JS)

res = {}
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 390, "height": 844})
        pg.goto(url, wait_until="load")
        pg.wait_for_timeout(1800)
        res["default"] = measure(pg)
        if A.shots:
            os.makedirs(A.shots, exist_ok=True)
            pg.screenshot(path=os.path.join(A.shots, "R_%s_default.png" % A.label))
        res["walk"] = measure(pg, 2.0)
        if A.shots:
            pg.screenshot(path=os.path.join(A.shots, "R_%s_walk.png" % A.label))
        br.close()
except Exception as e:
    print("!! ブラウザ実測に失敗: %s: %s" % (type(e).__name__, e)); sys.exit(2)
finally:
    if srv:
        srv.terminate()

# ---- 道路中心線 (地図空間) から★半径を評価 ----
geo = json.load(open(os.path.join(ROOT, "tools", "v2-build", "mapdata.json"), encoding="utf-8"))
FILLW = {"road-minor": 5.0, "road-mid": 9.0, "road-major": 12.0, "road-main": 13.0}
def seg_d(px, py, x1, y1, x2, y2):
    dx, dy = x2-x1, y2-y1
    L = dx*dx + dy*dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / L))
    return math.hypot(px - (x1+t*dx), py - (y1+t*dy))
roads = geo["roads"]
# 幅は gate.py と同じ規約: cls → 塗り幅。guide_spine は main 幅。
# ★注意★ GEO.busway[1] は「東西判定用のガイド線」で、描画される道路ではない。
# バス通りは roads の中に 中山幹線１号線(major)/菖蒲沢橋線(mid) 等として描かれており
# (ガイド線との差は中央値1.4m)、これを追加の13m道路として足すと架空の食い込みが出る。
CLSMAP = {"minor": "road-minor", "mid": "road-mid", "major": "road-major",
          "service": "road-service", "path": "road-path"}
def nearest_road(px, py):
    best, bw, bn = 1e18, 5.0, None
    for r in roads:
        w = 13.0 if r.get("guide_spine") else FILLW.get(CLSMAP.get(r.get("cls"), "road-mid"), 9.0)
        pts = r["pts"]
        for i in range(len(pts)-1):
            d = seg_d(px, py, pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            if d < best: best, bw, bn = d, w, (r.get("name") or r.get("cls"))
    return best, bw

print("=" * 78)
print("レンズR — 通りが通りとして読めるか (%s / 390x844)" % A.label)
print("=" * 78)

out = {}
for zk, zn in (("default", "既定ズーム"), ("walk", "歩きズーム")):
    d = res[zk]
    s0 = d["pxPerMeter"]
    rw = d["roadW"]
    stars = sorted(r["starPx"] for r in d["rows"])
    starM = sorted(r["starMapM"] for r in d["rows"])
    main = rw.get("road-main-f", 0)
    print("")
    print("── %s (%.4f px/m) ─────────────────────────────" % (zn, s0))
    print("[R1] 道路の実描画幅 px: " + " / ".join("%s %.1f" % (k.replace("road-", "").replace("-f", ""), v)
                                             for k, v in rw.items() if k.endswith("-f")))
    if main < ROAD_FLOOR_PX:
        print("     ✗ バス通りが %.1fpx — 通りとして読める床 %.0fpx 未満" % (main, ROAD_FLOOR_PX))
    print("[R2] ★の実描画幅 px: 中央値 %.1f (地図空間 %.1fm) / バス通り幅との比 %.2f  (上限 %.2f)"
          % (stars[len(stars)//2], starM[len(starM)//2],
             stars[len(stars)//2] / main if main else 9.9, STAR_ROAD_MAX))
    if main and stars[len(stars)//2] / main > STAR_ROAD_MAX:
        print("     ✗ ★が道路より太い — 通りを覆う")

    # R3 地図空間で★が道路の帯にかかる店
    over = []
    for r in d["rows"]:
        dd, w = nearest_road(r["x"], r["y"])
        rad = r["starMapM"] / 2.0
        # 道路は地図単位の実幅で描かれる (床は入っていない) ので w をそのまま使う
        drawn_m = w
        clear = dd - (drawn_m / 2.0) - rad
        if clear < 0:
            over.append((r["name"], round(clear, 1), round(dd, 1)))
    print("[R3] ★が道路の帯にかかっている店: %d / %d" % (len(over), len(d["rows"])))
    for nm, c, dd in sorted(over, key=lambda t: t[1])[:8]:
        print("     %-26s %.1fm 食い込み (中心線から %.1fm)" % (nm, -c, dd))

    outv = [r for r in d["rows"] if not r["starInVp"]]
    hid = [r for r in d["rows"] if not r["labelShown"]]
    hidv = [r for r in hid if r["voices"]]
    print("[R4] 表示域の外にある★: %d / ラベル非表示: %d (うちこどもの声あり %d/%d)"
          % (len(outv), len(hid), len(hidv), sum(1 for r in d["rows"] if r["voices"])))
    if hidv:
        print("     声ありが隠れている: %s" % ", ".join(r["name"] for r in hidv))
    out[zk] = {"pxPerMeter": s0, "roadW": rw, "starPxMed": stars[len(stars)//2],
               "overRoad": len(over), "outVp": len(outv), "hidden": len(hid),
               "hiddenVoices": [r["name"] for r in hidv]}

print("")
print("=" * 78)
if A.json:
    json.dump(out, open(A.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.stdout.flush()
