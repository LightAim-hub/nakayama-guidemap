#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズL — 「見やすい・使いやすい」を実ブラウザで測る (gate.py が測っていない側)

gate.py は幾何 (N1-N10) を測る。こちらは人が見て使えるかを測る:

  L1 ラベル判別余裕   自分の★までの距離 / 2番目に近い★までの距離  (N4 は「最近傍か」だけ)
  L2 既定ズーム可読性  可視ラベルの実表示フォントpx (高齢者床 12px)
  L3 タップ的中        ★中心を elementFromPoint して自分の hit が返るか  ← 最重要
  L4 タップ標的サイズ  .pad の直径 px (WCAG 2.5.5 / Apple HIG = 44px)
  L5 歩行順序          通りに沿ったラベルの描画順が真の順序と一致するか (東西別)
  L6 密度              100x100px セルあたりの可視ラベル数
  L7 ★の視覚的融合    既定ズームでの最近傍★間距離 px (gate N8 は歩きズームのみ)
  L8 隠れたラベルの重要度  非表示ラベルのうちアンカー店 (こどもの声/公式URL) の数
  L9 コントラスト      ラベル文字 vs 紙 の WCAG コントラスト比

使い方: python lens_legibility.py [--url URL] [--json OUT] [--shots DIR]
"""
import io, json, os, re, socket, subprocess, sys, time, math, argparse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.exists(os.path.join(ROOT, "index.html")):
    ROOT = os.path.join(os.environ.get("USERPROFILE", ""), "nakayama-guidemap")

ap = argparse.ArgumentParser()
ap.add_argument("--url")
ap.add_argument("--json")
ap.add_argument("--shots")
ap.add_argument("--target", default="index.html")
A = ap.parse_args()

OUT = []
def P(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s); print(s)

# ---- 床 (ここを緩めるのは不正。緩めるなら理由を書いて別コミット) ----
FONT_FLOOR_PX = 12.0      # 高齢者可読の床
TAP_FLOOR_PX = 44.0       # WCAG 2.5.5 AAA / Apple HIG
STAR_SEP_FLOOR_PX = 10.0  # 既定ズームで★が融合しない最小間隔
LABEL_MARGIN_MAX = 0.55   # 自分の★までの距離 / 2番目の★までの距離
DENSITY_MAX = 6           # 100x100px あたりの可視ラベル数
CONTRAST_MIN = 4.5        # WCAG AA (通常文字)

# ---------------- L9 コントラスト (ブラウザ不要) ----------------
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
def _lum(hx):
    hx = hx.lstrip("#")
    r, g, b = (int(hx[i:i+2], 16) for i in (0, 2, 4))
    return .2126*_lin(r) + .7152*_lin(g) + .0722*_lin(b)
def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + .05) / (lo + .05)

# ---------------- サーバ (動的ポート・30秒タイムアウト) ----------------
url, srv = A.url, None
if not url:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d/%s" % (port, A.target)
    ok = False
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=1).read(1); ok = True; break
        except Exception:
            time.sleep(1)
    if not ok:
        srv.terminate(); P("!! サーバ起動失敗 — 中止"); sys.exit(2)

JS = r"""() => {
  const svg = document.getElementById('map');
  const ctm = svg.getScreenCTM();
  const s0  = Math.hypot(ctm.a, ctm.b);          // px / 地図単位(=m)
  const vpr = document.getElementById('viewport').getBoundingClientRect();
  const hits = [...document.querySelectorAll('g.hit')];

  const rows = hits.map(h => {
    const i = +h.dataset.i, sh = GEO.shops[i];
    const st  = h.querySelector('.star');
    const pad = h.querySelector('.pad');
    const t   = h.querySelector('text.shoplabel');
    const sr  = st ? st.getBoundingClientRect() : null;      // 実描画 (CSS px)
    const pr  = pad ? pad.getBoundingClientRect() : null;
    const shown = !!(t && getComputedStyle(t).display !== 'none'
                       && +getComputedStyle(t).opacity > .05
                       && t.getBoundingClientRect().width > 1);
    const tr = shown ? t.getBoundingClientRect() : null;
    const fs = t ? parseFloat(getComputedStyle(t).fontSize) : 0;
    const scx = sr ? sr.left + sr.width/2  : null;
    const scy = sr ? sr.top  + sr.height/2 : null;
    return {
      i, name: sh.name,
      // アンカー = こどもの声あり (url は60/60が持つので判別に使えない)
      anchor: !!(sh.voices && sh.voices.length),
      starCx: scx, starCy: scy,
      starPx: sr ? +sr.width.toFixed(2)  : 0,
      // ★が地図の表示域 (#viewport) の中にあるか。外なら既定表示では見えない
      starInVp: (scx !== null) && scx >= vpr.left && scx <= vpr.right
                               && scy >= vpr.top  && scy <= vpr.bottom,
      padPx:  pr ? +Math.max(pr.width, pr.height).toFixed(1) : 0,
      labelShown: shown,
      labelCx: tr ? tr.left + tr.width/2  : null,
      labelCy: tr ? tr.top  + tr.height/2 : null,
      labelRect: tr ? [+tr.left.toFixed(1), +tr.top.toFixed(1),
                       +tr.right.toFixed(1), +tr.bottom.toFixed(1)] : null,
      labelW:  tr ? +tr.width.toFixed(1)  : 0,
      labelH:  tr ? +tr.height.toFixed(1) : 0,
      fontUser: +fs.toFixed(2),
      fontPx:  +(fs * s0).toFixed(2),          // user単位なら *s0 が実表示
      fontPxDom: tr ? +tr.height.toFixed(1) : 0,
      tx: sh.tx !== undefined ? sh.tx : sh.x,
      ty: sh.ty !== undefined ? sh.ty : sh.y,
      x: sh.x, y: sh.y
    };
  });

  // 可視ラベル bbox (L6 密度用)
  const vis = rows.filter(r => r.labelShown);
  const vp = {w: innerWidth, h: innerHeight};
  return {pxPerMeter: +s0.toFixed(4), rows, visibleLabels: vis.length, vp,
          inkColor: getComputedStyle(document.documentElement).getPropertyValue('--ink').trim(),
          paperColor: getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()};
}"""

def dist(ax, ay, bx, by):
    return math.hypot(ax-bx, ay-by)

REND = None
errs = []
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 390, "height": 844})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url, wait_until="load")
        pg.wait_for_timeout(1800)
        REND = pg.evaluate(JS)
        if A.shots:
            os.makedirs(A.shots, exist_ok=True)
            pg.screenshot(path=os.path.join(A.shots, "L_default.png"), full_page=False)

        # L3 = 実際に★の中心をクリックして「何が起きるか」を見る。
        # elementFromPoint の重なり順ではダメ (密集地は nearby() でチューザーが出る仕様)。
        STATE = """() => {
          const ch = document.getElementById('chooser');
          const shown = !!(ch && ch.classList.contains('show'));
          const opts = shown ? [...ch.querySelectorAll('.copt')].map(b => b.textContent.trim()) : [];
          const dp = document.getElementById('detailPanel');
          const open = !!(dp && dp.getAttribute('aria-hidden') === 'false');
          const ti = document.getElementById('detailTitle');
          return {chooser: shown, opts, detail: open,
                  title: (open && ti) ? ti.textContent.trim() : null};
        }"""
        for r in REND["rows"]:
            r["tapResult"] = None
            if not r.get("starInVp"):
                continue
            try:
                pg.mouse.click(r["starCx"], r["starCy"])
                pg.wait_for_timeout(110)
                st = pg.evaluate(STATE)
                nm = r["name"]
                if st["chooser"]:
                    hit = any(nm in o for o in st["opts"])
                    r["tapResult"] = ("chooser_ok" if hit else "chooser_missing")
                    r["tapOpts"] = st["opts"]
                elif st["detail"]:
                    r["tapResult"] = ("detail_ok" if st["title"] and nm in st["title"]
                                      else "detail_wrong")
                    r["tapOpts"] = [st["title"]]
                else:
                    r["tapResult"] = "nothing"
                    r["tapOpts"] = []
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(60)
            except Exception as ex:
                r["tapResult"] = "error:%s" % type(ex).__name__
        br.close()
except Exception as e:
    P("!! ブラウザ実測に失敗: %s: %s" % (type(e).__name__, e))
finally:
    if srv:
        srv.terminate()

if not REND:
    sys.exit(2)

rows = REND["rows"]
s0 = REND["pxPerMeter"]
fails = []

P("=" * 78)
P("レンズL — 見やすさ・使いやすさの実測 (390x844 / 既定ズーム %.4f px/m)" % s0)
P("=" * 78)
P("店数: %d / 可視ラベル: %d / JSエラー: %d" % (len(rows), REND["visibleLabels"], len(errs)))

# ---------------- L3 タップ的中 ----------------
# 地図の表示域に入っている★だけを対象にする。表示域の外はスクロールで届くので別集計。
inv = [r for r in rows if r.get("starInVp")]
outv = [r for r in rows if not r.get("starInVp")]
from collections import Counter
tc = Counter(r.get("tapResult") for r in inv)
ok = tc["detail_ok"] + tc["chooser_ok"]
bad = [r for r in inv if r.get("tapResult") in ("chooser_missing", "detail_wrong", "nothing")]
P("")
P("[L3] 表示域内の★ %d/%d を実クリック — 自店が開く %d / チューザーに自店あり %d / 到達不能 %d"
  % (len(inv), len(rows), tc["detail_ok"], tc["chooser_ok"], len(bad)))
if tc["chooser_ok"]:
    P("     ※ 密集地は仕様どおり「どのお店？」が出る (nearby 22m)。自店が選択肢にあれば到達可")
for r in bad[:20]:
    P("     × %-26s → %s  %s" % (r["name"], r.get("tapResult"),
                                 "/".join(r.get("tapOpts") or [])[:60]))
if outv:
    P("     既定表示では地図の外にある★ %d件: %s"
      % (len(outv), ", ".join(r["name"] for r in outv[:10])))
if bad:
    fails.append(("L3 ★をタップしても自店に到達できない", len(bad)))

# ---------------- L4 タップ標的 ----------------
small = sorted([r for r in rows if r["padPx"] < TAP_FLOOR_PX], key=lambda r: r["padPx"])
P("")
P("[L4] タップ標的 (.pad) 実寸 px: 中央値 %.1f / 最小 %.1f  (床 %.0f)"
  % (sorted(r["padPx"] for r in rows)[len(rows)//2], min(r["padPx"] for r in rows), TAP_FLOOR_PX))
if small:
    P("     床未満 %d件: %s" % (len(small), ", ".join("%s %.0fpx" % (r["name"], r["padPx"]) for r in small[:6])))
    fails.append(("L4 タップ標的が44px未満", len(small)))

# ---------------- L2 フォント ----------------
visr = [r for r in rows if r["labelShown"]]
if visr:
    fpx = sorted(r["fontPxDom"] for r in visr)
    tiny = [r for r in visr if r["fontPxDom"] < FONT_FLOOR_PX]
    P("")
    P("[L2] 可視ラベルの実表示高さ px: 中央値 %.1f / 最小 %.1f / 最大 %.1f  (床 %.0f)"
      % (fpx[len(fpx)//2], fpx[0], fpx[-1], FONT_FLOOR_PX))
    if tiny:
        P("     床未満 %d/%d件: %s" % (len(tiny), len(visr),
          ", ".join("%s %.1f" % (r["name"], r["fontPxDom"]) for r in tiny[:8])))
        fails.append(("L2 ラベルが12px未満", len(tiny)))

# ---------------- L7 ★の視覚的融合 ----------------
P("")
merged = []
for r in rows:
    if r["starCx"] is None: continue
    best, bn = 1e9, None
    for o in rows:
        if o is r or o["starCx"] is None: continue
        d = dist(r["starCx"], r["starCy"], o["starCx"], o["starCy"])
        if d < best: best, bn = d, o["name"]
    r["nnStarPx"], r["nnStarName"] = best, bn
    if best < STAR_SEP_FLOOR_PX:
        merged.append(r)
nn = sorted(r["nnStarPx"] for r in rows if r.get("nnStarPx") is not None)
P("[L7] 既定ズームでの最近傍★間距離 px: 最小 %.1f / 中央値 %.1f  (床 %.0f・★実寸 中央値 %.1fpx)"
  % (nn[0], nn[len(nn)//2], STAR_SEP_FLOOR_PX, sorted(r["starPx"] for r in rows)[len(rows)//2]))
seen = set()
for r in sorted(merged, key=lambda r: r["nnStarPx"]):
    k = tuple(sorted([r["name"], r["nnStarName"]]))
    if k in seen: continue
    seen.add(k)
    P("     融合 %.1fpx: %s ⇔ %s" % (r["nnStarPx"], r["name"], r["nnStarName"]))
if merged:
    fails.append(("L7 既定ズームで★が融合", len(seen)))

# ---------------- L1 ラベル判別余裕 ----------------
P("")
def rect_d(rc, sx, sy):
    """ラベルの矩形から★中心までの最短距離。長い店名の中心で測ると
    「左端が自分の★に接していても遠い」と誤判定するため縁で測る。"""
    l, t, rr, b = rc
    dx = max(l - sx, 0.0, sx - rr)
    dy = max(t - sy, 0.0, sy - b)
    return math.hypot(dx, dy)

worst = []
for r in visr:
    if r.get("labelRect") is None or r["starCx"] is None: continue
    rc = r["labelRect"]
    own = rect_d(rc, r["starCx"], r["starCy"])
    ds = sorted(((rect_d(rc, o["starCx"], o["starCy"]), o["name"])
                 for o in rows if o is not r and o["starCx"] is not None))
    second = ds[0][0] if ds else 1e9
    r["ownPx"], r["secondPx"], r["secondName"] = own, second, (ds[0][1] if ds else None)
    r["margin"] = own / second if second > 0 else 9.9
    if r["margin"] > LABEL_MARGIN_MAX:
        worst.append(r)
if visr:
    ms = sorted(r["margin"] for r in visr if "margin" in r)
    P("[L1] ラベル判別余裕 (自分の★/2番目の★): 中央値 %.2f / 最悪 %.2f  (上限 %.2f)"
      % (ms[len(ms)//2], ms[-1], LABEL_MARGIN_MAX))
    for r in sorted(worst, key=lambda r: -r["margin"])[:12]:
        P("     △ %-24s 自分 %.0fpx / 他人(%s) %.0fpx = %.2f"
          % (r["name"], r["ownPx"], r["secondName"], r["secondPx"], r["margin"]))
    if worst:
        fails.append(("L1 ラベルが自分の★に十分近くない", len(worst)))

# ---------------- L8 隠れたラベルの重要度 ----------------
hidden = [r for r in rows if not r["labelShown"]]
hidden_anchor = [r for r in hidden if r["anchor"]]
P("")
P("[L8] 既定ズームで非表示のラベル: %d/%d  (うち こどもの声あり %d/%d)"
  % (len(hidden), len(rows), len(hidden_anchor), sum(1 for r in rows if r["anchor"])))
if hidden_anchor:
    P("     声ありが隠れている: %s" % ", ".join(r["name"] for r in hidden_anchor[:10]))
    fails.append(("L8 こどもの声ありのラベルが隠れている", len(hidden_anchor)))

# ---------------- L6 密度 ----------------
cell = {}
for r in visr:
    if r["labelCx"] is None: continue
    k = (int(r["labelCx"] // 100), int(r["labelCy"] // 100))
    cell.setdefault(k, []).append(r["name"])
hot = sorted(((len(v), k, v) for k, v in cell.items()), reverse=True)
P("")
P("[L6] 100x100px セルの可視ラベル数: 最大 %d  (上限 %d)"
  % (hot[0][0] if hot else 0, DENSITY_MAX))
for n, k, v in hot[:3]:
    if n > DENSITY_MAX:
        P("     混雑 セル%s に %d枚: %s" % (str(k), n, "/".join(v)))
if hot and hot[0][0] > DENSITY_MAX:
    fails.append(("L6 ラベル密度が上限超", sum(1 for n, k, v in hot if n > DENSITY_MAX)))

# ---------------- L5 歩行順序 ----------------
def spine_x_factory(geo_busway):
    pts = geo_busway
    def f(y):
        best, bx = 1e18, pts[0][0]
        for i in range(len(pts)-1):
            (x1,y1),(x2,y2) = pts[i], pts[i+1]
            if (y1-y)*(y2-y) <= 0 and y1 != y2:
                t = (y-y1)/(y2-y1); return x1 + t*(x2-x1)
            for (px,py) in ((x1,y1),(x2,y2)):
                d = abs(py-y)
                if d < best: best, bx = d, px
        return bx
    return f

geo = json.load(open(os.path.join(ROOT, "tools", "v2-build", "mapdata.json"), encoding="utf-8"))
spine = geo["busway"][1] if isinstance(geo.get("busway"), list) else None
P("")
if spine:
    sx = spine_x_factory(spine)
    order_bad = 0
    for sgn, nm in ((1, "東側"), (-1, "西側")):
        grp = [r for r in rows if (1 if r["x"] >= sx(r["y"]) else -1) == sgn]
        true_order = [r["name"] for r in sorted(grp, key=lambda r: r["ty"])]
        drawn_order = [r["name"] for r in sorted(grp, key=lambda r: r["y"])]
        inv = sum(1 for i in range(len(true_order)) for j in range(i+1, len(true_order))
                  if drawn_order.index(true_order[i]) > drawn_order.index(true_order[j]))
        order_bad += inv
        P("[L5] %s %d店: 南北の並び順の入れ替わり %d組" % (nm, len(grp), inv))
    if order_bad:
        fails.append(("L5 通り沿いの並び順が入れ替わる", order_bad))
else:
    P("[L5] spine を取得できず (mapdata.json の busway 構造)")

# ---------------- L9 コントラスト ----------------
ink = REND.get("inkColor") or "#5C4327"
paper = REND.get("paperColor") or "#FBF4E2"
cr = contrast(ink, paper)
P("")
P("[L9] ラベル %s / 紙 %s のコントラスト比 %.2f:1  (WCAG AA %.1f)" % (ink, paper, cr, CONTRAST_MIN))
if cr < CONTRAST_MIN:
    fails.append(("L9 コントラスト不足", 1))

# ---------------- 判定 ----------------
P("")
P("=" * 78)
if fails:
    P("レンズL 判定: FAIL — %d種 / 計%d件" % (len(fails), sum(n for _, n in fails)))
    for nm, n in fails:
        P("   %-34s %d件" % (nm, n))
else:
    P("レンズL 判定: PASS — 見やすさ・使いやすさの床を全て満たしています")
P("=" * 78)

if A.json:
    json.dump({"pxPerMeter": s0, "fails": fails, "rows": rows, "jsErrors": errs},
              open(A.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

sys.stdout.flush()
sys.exit(1 if fails else 0)
