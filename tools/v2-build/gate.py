#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""なかやまマップ 単一合格ゲート — 「地図を見ながら歩いて、正しくその店に行けるか」

ボスの合格定義 (2026-07-30):
  「使いやすいな見やすいなって思うのと同時に、この店舗はここの向かい側あってるね
    みたいな、そのマップを見ながら歩いた時に正しくその店に行けるようにしないといけない」

= 正しい位置関係 と 見やすさ が同時に成り立つこと。片方だけでは不合格。

店ごとに N1..N29 を判定し、全部通った店だけ「歩ける (NAVIGABLE)」とする。
1件でも落ちれば exit 1。

  N1..N10  位置関係と歩きズームでの見やすさ
  N11..N15 概観ズーム (開いた瞬間の画面) での見やすさ  ← 2026-07-30 追加
  N16      座標の出典 (src) の書き換え検出              ← 2026-07-30 追加
  N17      固定UI (お店一覧/ズーム) が店名を覆わない    ← 2026-07-30 追加
  N18-N19  こどもの声バッジ / 信号アイコン               ← 2026-07-30 追加
  N20-N24  UI/UX (押しやすさ・文字の大きさ・配置)        ← 2026-07-31 追加

usage:
  python tools/v2-build/gate.py [--url http://127.0.0.1:PORT/index.html] [--json out.json]
  (--url 省略時は index.html を file:// で開く)
"""
import argparse, io, json, math, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

ap = argparse.ArgumentParser()
ap.add_argument("--url", default=None)
ap.add_argument("--json", default=None)
ap.add_argument("--target", default=os.path.join(ROOT, "index.html"))
ap.add_argument("--no-browser", action="store_true")
A = ap.parse_args()

OUT = []
def P(*a):
    OUT.append(" ".join(str(x) for x in a))

# 建物が無い敷地 (建物内判定の除外)。公園はポリゴンで別途判定する。
OPEN_SITES = {"たきみち公園", "なかやまとびのこ公園", "中山山の神公園",
              "中山小学校", "中山中学校", "中山ドライブスクール",
              "中山鳥瀧不動尊（目の神様）", "商店街モニュメント"}

# 歩きながら見るズーム。1m が画面2px = 通り1本が26px で見える倍率。
WALK_PX_PER_M = 2.0
MIN_STAR_PX = 6.0          # これ未満の★は見えない
SETBACK = 2.0              # 道路の帯からこれだけ離れていること

# ---- 2026-07-30 追加 (N11-N15): 概観ズーム側の「見やすさ」 ----
# 歩きズームだけを見ていたため、最初に見える倍率で「通りが読めない / ★が通りより太い /
# ラベルが他店の★を内包する」を取りこぼしていた。バーは上がる方向にのみ変更している。
# 床の決め方 (勘で置かず、他の床から逆算している):
#   ★は 6px 未満だと見えない (MIN_STAR_PX)。★ ≤ 0.60 × 道路幅 を満たすには
#   道路幅 ≥ 10px が必要で、10px では★がちょうど6pxで余裕がない。12px なら★7.2px。
ROAD_FLOOR_PX = 12.0       # バス通りが通りとして読める最小の描画幅
STAR_ROAD_MAX = 0.60       # ★の幅 / バス通りの描画幅 の上限 (超えると通りを覆う)
# 「自分の★が明確に最近傍」= 他のどの★より25%以上近い。
# 0.55 (=2倍近い) にすると、人が問題なく読めるラベルまで非表示を強いるので採らない。
# ボスの訴えは「どの星がどの店名か分からない」なので、順序が明確なら足りる。
LABEL_MARGIN_MAX = 0.80
# ★の先端が帯にかすってよい量 (m)。現実が近い店 (中心線から9.2m 等) では
# 可読な大きさの★は必ず縁に触れる。乗っている (中心が内側) は N15 で別に不合格。
# 実測の最大は1.2m。2.0m を上限にして、これ以上悪化したら不合格になるようにする。
MAX_STAR_ROAD_BITE = 2.0

# ---- 2026-07-30 追加 (N20-N23): UI/UX ----
# ボス指示「文字の大きさ・位置・ボタンの配置と押しやすさを、位置関係を変えずに」。
# 実測 (2026-07-30) の出発点:
#   押しやすさ: chip44 / 検索44 / お店一覧44 / ズーム44x44 / 閉じる44x44 / 一覧の行60 → 合格
#   文字      : カテゴリ名12.5 / お店一覧13.6 / 検索結果12.5 / 見出し下12.0 / フッタ10.9 → 不足
#   カテゴリ  : 6個中2個しか見えない (必要875px vs 画面360-428px)。
#              しかも「こどもの声（11店）」が最後尾で常に画面外
TAP_MIN_PX = 44.0          # WCAG 2.5.5 / Apple HIG。操作要素の最小
TEXT_MIN_PX = 14.0         # 高齢者も読める床
ATTRIB_MIN_PX = 12.0       # 帰属表示 (OpenStreetMap ODbL 等) だけはこの床
# 地図の大きさの床。当初 0.62 (比率のみ) にしたが、背の低い実機を試さずに置いた値だった。
# 実測 (2026-07-31): 360x640 では上下UIが295px = 画面の46%を占める。
#   header 38 + カテゴリ2段 101 + 検索 50 + フッタ 106 = 295px
# 62%を満たすには余白を243pxまで削る必要があり、チップを44px未満にしないと届かない
# (= N20 の押しやすさを壊す)。44pxの操作要素と帰属表示(ODbL)の表示を保ったまま
# 62%は達成不能なので、比率を下げるかわりに絶対値の床を併せて置いて歯止めにする。
MAP_MIN_RATIO = 0.52       # 画面の高さに対する地図の最小比率
MAP_MIN_PX = 330.0         # 地図の最小の高さ (実測 360x640 で345px)
# UI検査を回す実機サイズ。幅だけ変えて高さを844固定にしていたため、
# 360x640 (よくある小型Android) の実際の高さを一度も測っていなかった
# (2026-07-31 発覚: そこでは上下UIが295pxを占め地図が53.9%しかない)。
UI_DEVICES = [(360, 640), (375, 667), (390, 844), (428, 926)]
# 端末を寝かせた状態。文字の大きさと押しやすさは向きに関係なく成り立つべきなので
# N20/N21 はここでも見る。一方 N23 (地図の大きさ) は横向きだと前提が変わるので
# 縦向きだけで判定する — 横向きは「地図が主」でなく「一覧が主」の使い方になる。
UI_LANDSCAPE = [(640, 360), (844, 390)]
# 横向きの地図の床。実測 (2026-07-31) では 640x360 で地図が57px・844x390 で51px しかなく、
# 上下のUIが画面の87%を占めていた。この状態では地図として使えない。
# 横向きは横に余裕があるので、カテゴリと検索を横の列へ逃がせば縦は
#   ヘッダ38 + フッタ約100 = 138px で済み、640x360 なら地図222px (62%) が取れる計算。
# 余裕を見て 200px / 45% を床に置く。達成不能だと分かったら、縦向きの 0.62→0.52 と
# 同じように「なぜ届かないか」を書いたうえで下げる。勘で下げない。
LAND_MAP_MIN_PX = 200.0
LAND_MAP_MIN_RATIO = 0.45
# ラベル配置の所要時間の上限。2026-07-31 の Task R で、こどもの声の店を同時に解く
# 「打ち切りの無い再帰探索」が入った。いまの条件では12手で終わるが、店やバッジが増えて
# 制約が厳しくなると組み合わせ爆発する。地図が固まるのは最悪の壊れ方 (店名が消えるより悪い)
# なので、賢さでなく時間で歯止めをかける。ズーム操作1回あたりの最悪値で測る。
MAX_LAYOUT_MS = 400.0

# ---------------- GEO ----------------
src = io.open(A.target, encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
shops, roads, signals, parks = G["shops"], G["roads"], G["signals"], G["parks"]
meta = G["meta"]
SPINE = G["busway"][1]

# 描画幅を生成物から読む (固定値を置かない)
FILLW = {}
for m in re.finditer(r"class:'(road-[a-z-]+)-f', 'stroke-width':([\d.]+)", src):
    FILLW[m.group(1)] = float(m.group(2))
SPINE_W = FILLW.get("road-main", 13.0)
CLSMAP = {"minor": "road-minor", "mid": "road-mid", "major": "road-major",
          "service": "road-service", "path": "road-path"}


def road_w(r):
    if r.get("guide_spine"):
        return SPINE_W
    return FILLW.get(CLSMAP.get(r["cls"], "road-mid"), 9.0)


def seg_d(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def road_d(px, py, r):
    return min(seg_d(px, py, a[0], a[1], b[0], b[1]) for a, b in zip(r["pts"], r["pts"][1:]))


def spine_x(y):
    best = None
    for (x1, y1), (x2, y2) in zip(SPINE, SPINE[1:]):
        lo, hi = min(y1, y2), max(y1, y2)
        if lo <= y <= hi:
            t = 0.0 if abs(y2 - y1) < 1e-9 else (y - y1) / (y2 - y1)
            return x1 + t * (x2 - x1)
        d = min(abs(y - lo), abs(y - hi))
        if best is None or d < best[0]:
            best = (d, x1 if abs(y - y1) < abs(y - y2) else x2)
    return best[1]


def TX(s): return s.get("tx", s["x"])
def TY(s): return s.get("ty", s["y"])
def side(x, y): return 1 if x >= spine_x(y) else -1


def poly_inside(pl, x, y):
    c = False
    n = len(pl)
    for i in range(n):
        x1, y1 = pl[i]; x2, y2 = pl[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
                c = not c
    return c


# ---------------- 建物ポリゴン ----------------
BLD = []
bpath = os.path.join(HERE, "buildings_raw.json")
if os.path.exists(bpath):
    p = meta["proj"]
    R = math.radians(p["rot_deg"]); CA, SA = math.cos(R), math.sin(R)
    mnx, mny = meta["minx"], meta["miny"]

    def proj(lat, lng):
        mx = (lng - p["lon0"]) * p["cosf"] * 111320.0
        my = (lat - p["lat0"]) * 111320.0
        return mx * CA + my * SA - mnx, mx * SA - my * CA - mny

    W, H = meta["W"], meta["H"]
    for e in json.load(io.open(bpath, encoding="utf-8"))["elements"]:
        g = e.get("geometry")
        if not g:
            continue
        pts = [proj(q["lat"], q["lon"]) for q in g if q.get("lat") is not None]
        if len(pts) < 3:
            continue
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        if max(xs) < -60 or min(xs) > W + 60 or max(ys) < -60 or min(ys) > H + 60:
            continue
        BLD.append((min(xs), min(ys), max(xs), max(ys), pts))


def in_building(x, y):
    for x0, y0, x1, y1, pts in BLD:
        if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1 and poly_inside(pts, x, y):
            return True
    return False


# ---------------- 交差点 ----------------
def _ix(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -0.001 <= t <= 1.001 and -0.001 <= u <= 1.001:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


NODES = []
for i in range(len(roads)):
    si = list(zip(roads[i]["pts"], roads[i]["pts"][1:]))
    for j in range(i + 1, len(roads)):
        for a, b in si:
            for c, e in zip(roads[j]["pts"], roads[j]["pts"][1:]):
                q = _ix(a, b, c, e)
                if q:
                    NODES.append(q)
XN = []
for q in NODES:
    if not any(math.hypot(q[0] - r[0], q[1] - r[1]) < 12 for r in XN):
        XN.append(q)

SIG_OK = []       # 交差点に立っている信号 (waypointとして使える)
for sx, sy in signals:
    d = min((math.hypot(sx - q[0], sy - q[1]) for q in XN), default=1e9)
    SIG_OK.append(d <= 20)

# ---------------- ブラウザ側の実測 ----------------
REND = None
if not A.no_browser:
    url = A.url
    srv = None
    if not url:
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = "http://127.0.0.1:%d/index.html" % port
        ok = False
        for _ in range(30):
            try:
                import urllib.request
                urllib.request.urlopen(url, timeout=1).read(1)
                ok = True; break
            except Exception:
                time.sleep(1)
        if not ok:
            srv.terminate(); srv = None; url = None
    if url:
        try:
            from playwright.sync_api import sync_playwright
            JS = """(walkPxPerM) => {
              const svg = document.getElementById('map');
              const s0 = Math.hypot(svg.getScreenCTM().a, svg.getScreenCTM().b);
              // 道路の実描画幅 (px)。通りとして読めるかを見るため
              const roadPx = {};
              for (const c of ['main','major','mid','minor']) {
                const el = document.querySelector('.road-' + c + '-f');
                if (el) roadPx[c] = +(parseFloat(getComputedStyle(el).strokeWidth) * s0).toFixed(2);
              }
              const rows = [...document.querySelectorAll('g.hit')].map(h => {
                const i = +h.dataset.i, s = GEO.shops[i];
                const st = h.querySelector('.star'), t = h.querySelector('text.shoplabel');
                const bb = st ? st.getBBox() : null;
                const m  = st ? st.getScreenCTM() : null;
                const sc = m ? Math.hypot(m.a, m.b) : 0;
                const tb = t ? t.getBBox() : null;
                const sr = st ? st.getBoundingClientRect() : null;
                const shown = !!(t && getComputedStyle(t).display !== 'none' && +getComputedStyle(t).opacity > 0);
                const tr = (shown && t) ? t.getBoundingClientRect() : null;
                return {i, name: s.name,
                        starPxNow:  bb ? +(bb.width * sc).toFixed(2) : 0,
                        starMapM:   bb && sc ? +(bb.width * sc / s0).toFixed(2) : 0,
                        labelShown: shown,
                        lx: s.lx, ly: s.ly,
                        starCx: sr ? +(sr.left + sr.width / 2).toFixed(1) : null,
                        starCy: sr ? +(sr.top + sr.height / 2).toFixed(1) : null,
                        labelRect: (tr && tr.width > 1)
                                   ? [+tr.left.toFixed(1), +tr.top.toFixed(1),
                                      +tr.right.toFixed(1), +tr.bottom.toFixed(1)] : null,
                        labelMapW: tb ? +tb.width.toFixed(1) : 0};
              });
              // ラベルbbox交差
              const vis = [...document.querySelectorAll('text.shoplabel')].filter(t =>
                getComputedStyle(t).display !== 'none' && t.getBoundingClientRect().width > 1);
              let cross = 0;
              const bx = vis.map(t => t.getBoundingClientRect());
              for (let i=0;i<bx.length;i++) for (let j=i+1;j<bx.length;j++){
                const ox = Math.min(bx[i].right,bx[j].right)-Math.max(bx[i].left,bx[j].left);
                const oy = Math.min(bx[i].bottom,bx[j].bottom)-Math.max(bx[i].top,bx[j].top);
                if (ox>0.5 && oy>0.5) cross++;
              }
              // 固定UI (position:fixed) が可視ラベルを覆っていないか。
              // 表示域の外に出ているぶんはクリップされて見えないだけなので除く
              // (パン可能な地図では端で切れるのは正常)。
              const vpr = document.getElementById('viewport').getBoundingClientRect();
              const fx = ['#listbtn', '.zoomctl', '#editbar', '#srcinfo']
                .map(q => document.querySelector(q))
                .filter(e => e && getComputedStyle(e).position === 'fixed'
                               && getComputedStyle(e).display !== 'none')
                .map(e => e.getBoundingClientRect());
              const covered = [];
              for (const t of document.querySelectorAll('text.shoplabel')) {
                if (getComputedStyle(t).display === 'none') continue;
                const b = t.getBoundingClientRect();
                if (b.width < 1) continue;
                const l = Math.max(b.left, vpr.left),  r2 = Math.min(b.right, vpr.right);
                const tp = Math.max(b.top, vpr.top),   bo = Math.min(b.bottom, vpr.bottom);
                if (r2 <= l || bo <= tp) continue;
                for (const f of fx) {
                  const ox = Math.min(r2, f.right) - Math.max(l, f.left);
                  const oy = Math.min(bo, f.bottom) - Math.max(tp, f.top);
                  if (ox > 1 && oy > 1)
                    covered.push({name: t.textContent.trim(),
                                  pct: Math.round(100 * ox * oy / ((r2 - l) * (bo - tp)))});
                }
              }
              // こどもの声バッジ / 信号アイコン。★と同じく「地図単位固定で大きすぎる」
              // 問題を持ちうるのに見ていなかった (2026-07-30 9周目で発覚)。
              const starList = [...document.querySelectorAll('g.hit')].map(h => {
                const st = h.querySelector('.star');
                if (!st) return null;
                const b = st.getBoundingClientRect();
                return {n: GEO.shops[+h.dataset.i].name,
                        cx: b.left + b.width / 2, cy: b.top + b.height / 2, b: b};
              }).filter(Boolean);
              const badges = [...document.querySelectorAll('g.voice-badge')].map(g => {
                const b = g.getBoundingClientRect();
                const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
                const own = g.closest('g.hit');
                const on = own ? GEO.shops[+own.dataset.i].name : null;
                let bn = null, bd = 1e9, od = -1;
                for (const s of starList) {
                  const d = Math.hypot(s.cx - cx, s.cy - cy);
                  if (d < bd) { bd = d; bn = s.n; }
                  if (s.n === on) od = d;
                }
                return {own: on, nearest: bn, nearestPx: +bd.toFixed(1),
                        ownPx: +od.toFixed(1), wPx: +b.width.toFixed(1)};
              });
              const ovl = (a, b) => (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1)
                                 && (Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1);
              const sigBoxes = [...svg.querySelectorAll('rect')]
                .filter(r => r.getAttribute('rx') === '5.5' && r.getAttribute('width') === '22')
                .map(r => r.parentNode.getBoundingClientRect());
              const sigHit = [];
              for (const g of sigBoxes) {
                for (const s of starList) if (ovl(g, s.b)) sigHit.push({n: s.n, kind: '★'});
                for (const t of vis) if (ovl(g, t.getBoundingClientRect()))
                  sigHit.push({n: t.textContent.trim(), kind: 'ラベル'});
              }
              // この倍率で「どのお店？」チューザーが出る店の数。
              // nearby が地図単位固定だとズームしても減らない。
              let chooserShops = null;
              try {
                chooserShops = GEO.shops.filter(s2 => nearby(s2).length > 1).length;
              } catch (e) { chooserShops = null; }
              return {pxPerMeter:+s0.toFixed(4), rows, roadPx, labelCross:cross,
                      labelsVisible:vis.length, uiCovered:covered, chooserShops,
                      badges, sigW: sigBoxes.length ? +sigBoxes[0].width.toFixed(1) : 0,
                      sigCount: sigBoxes.length, sigHit, jsErrors:0};
            }"""
            with sync_playwright() as pw:
                br = pw.chromium.launch()
                pg = br.new_page(viewport={"width": 390, "height": 844})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(url, wait_until="load")
                pg.wait_for_timeout(1500)
                REND = pg.evaluate(JS, WALK_PX_PER_M)
                REND["jsErrors"] = len(errs)
                # 歩きズーム: viewBox幅から逆算すると初期倍率の影響でずれるので、
                # 実DOM倍率を測りながら WALK_PX_PER_M に収束させる (Codex指摘のバグ修正)
                w = 390 / WALK_PX_PER_M
                for _ in range(6):
                    pg.evaluate("v=>document.getElementById('map').setAttribute('viewBox',v)",
                                "%f %f %f %f" % (400, 700, w, w * 844 / 390))
                    pg.wait_for_timeout(300)
                    got = pg.evaluate("""() => { const s=document.getElementById('map').getScreenCTM();
                                                return Math.hypot(s.a,s.b); }""")
                    if abs(got - WALK_PX_PER_M) / WALK_PX_PER_M < 0.02:
                        break
                    w = w * got / WALK_PX_PER_M
                REND["walk"] = pg.evaluate(JS, WALK_PX_PER_M)
                REND["walkPxPerMeter"] = round(got, 4)

                # ---- UI/UX の実測 (N20-N24)。画面幅を変えて操作部だけ見る ----
                UIJS = """() => {
                  const out = {vw: innerWidth, taps: [], texts: [], offscreen: []};
                  const SEL = [['.chip','カテゴリ'], ['#q','検索入力'], ['#listbtn','お店一覧'],
                               ['.zoomctl button','ズーム'], ['#detailClose','詳細を閉じる'],
                               ['.chooser .copt','チューザーの選択肢'], ['#listrows > *','一覧の行']];
                  const shown = e => {
                    const cs = getComputedStyle(e);
                    return cs.display !== 'none' && cs.visibility !== 'hidden'
                           && parseFloat(cs.opacity) > 0.05;
                  };
                  for (const [q, nm] of SEL) {
                    document.querySelectorAll(q).forEach((e, i) => {
                      if (!shown(e)) return;
                      const b = e.getBoundingClientRect();
                      if (b.width < 1 && b.height < 1) return;
                      const cs = getComputedStyle(e);
                      out.taps.push({nm: nm + (i ? '#' + i : ''), w: +b.width.toFixed(0),
                                     h: +b.height.toFixed(0),
                                     fs: +parseFloat(cs.fontSize).toFixed(1),
                                     txt: (e.textContent || '').trim().slice(0, 12)});
                      // 画面に一切かかっていないものは「閉じたパネルの中身」。
                      // 閉じた詳細シートは display:none ではなく画面外へずらしてあるので、
                      // これを見ないと ✕ ボタンを毎回「画面外」と誤検出する (2026-07-31)。
                      const onScreen = Math.min(b.right, innerWidth) - Math.max(b.left, 0) > 0
                                    && Math.min(b.bottom, innerHeight) - Math.max(b.top, 0) > 0;
                      if (onScreen && (b.right > innerWidth + 0.5 || b.left < -0.5))
                        out.offscreen.push({nm: nm + '#' + i,
                                            txt: (e.textContent || '').trim().slice(0, 12)});
                    });
                  }
                  // 文字サイズ (帰属表示は別枠)
                  const T = [['header h1','見出し',0], ['header p','見出し下',0],
                             ['#q','検索入力',0], ['#searchstatus','検索結果',0],
                             ['.chip .lbl','カテゴリ名',0], ['#listbtn','お店一覧ボタン',0],
                             ['.detail-address','詳細の住所',0], ['footer,.credits,.foot','帰属表示',1]];
                  for (const [q, nm, attrib] of T) {
                    const e = document.querySelector(q); if (!e) continue;
                    // display:none の要素は誰も見ないので測らない
                    // (2026-07-31: header p が元から非表示で誤検出していた)
                    if (!shown(e)) continue;
                    out.texts.push({nm, fs: +parseFloat(getComputedStyle(e).fontSize).toFixed(1),
                                    attrib: !!attrib});
                  }
                  // N25 固定UIが帰属表示・注記を覆っていないか。
                  // OpenStreetMap の ODbL は帰属が読める状態を求める。
                  const fxb = ['#listbtn', '.zoomctl'].map(q => document.querySelector(q))
                    .filter(e => e && getComputedStyle(e).position === 'fixed' && shown(e))
                    .map(e => e.getBoundingClientRect());
                  out.credits = [];
                  for (const e of document.querySelectorAll('body *')) {
                    if (e.children.length || !shown(e)) continue;
                    const t = (e.textContent || '').trim();
                    if (t.length < 4) continue;
                    if (e.closest('#map, #listpanel, .detail-panel, .chooser, header, .filters, .searchbar')) continue;
                    if (e.closest('#listbtn, .zoomctl')) continue;
                    const b = e.getBoundingClientRect();
                    if (b.width < 2 || b.height < 2) continue;
                    for (const f of fxb) {
                      const ox = Math.min(b.right, f.right) - Math.max(b.left, f.left);
                      const oy = Math.min(b.bottom, f.bottom) - Math.max(b.top, f.top);
                      if (ox > 1 && oy > 1)
                        out.credits.push({txt: t.slice(0, 36),
                          pct: Math.round(100 * ox * oy / (b.width * b.height))});
                    }
                  }
                  const vp = document.getElementById('viewport').getBoundingClientRect();
                  out.mapRatio = +(vp.height / innerHeight).toFixed(3);
                  out.mapH = Math.round(vp.height);
                  out.vh = innerHeight;
                  // N26 こどもの声の店のラベルが既定ズームで出ているか。
                  // 本企画の看板機能なので、端末が小さくても消えてはいけない。
                  out.voiceHidden = [];
                  for (const h of document.querySelectorAll('g.hit')) {
                    const sp = GEO.shops[+h.dataset.i];
                    if (!(sp.voices && sp.voices.length)) continue;
                    const st = h.querySelector('.star');
                    const t = h.querySelector('text.shoplabel');
                    if (!st) continue;
                    const bb = st.getBoundingClientRect();
                    const cx = bb.left + bb.width / 2, cy = bb.top + bb.height / 2;
                    const inV = cx >= vp.left && cx <= vp.right && cy >= vp.top && cy <= vp.bottom;
                    const vis = !!(t && getComputedStyle(t).display !== 'none'
                                   && t.getBoundingClientRect().width > 1);
                    if (inV && !vis) out.voiceHidden.push(sp.name);
                  }
                  // nearby の半径 (チューザーが出る条件) を実際の関数から測る
                  let nb = null;
                  try { nb = (typeof nearby === 'function')
                        ? GEO.shops.filter(o => nearby(GEO.shops[0]).includes(o)).length : null; } catch (e) {}
                  out.chooserShops = GEO.shops.filter(s => {
                    try { return nearby(s).length > 1; } catch (e) { return false; }
                  }).length;
                  return out;
                }"""
                # N27 ズームのたびに走るラベル配置が、時間内に終わるか。
                # layoutLabels を包んで実測する。包めていない (呼ばれた形跡が無い) 時は
                # 「測れた」ことにせず失敗として扱う — 0ms の偽合格を作らないため。
                TIMEJS = r"""async () => {
                  const orig = layoutLabels;
                  let worst = 0, calls = 0;
                  window.layoutLabels = function(){
                    const t0 = performance.now();
                    const r = orig.apply(this, arguments);
                    worst = Math.max(worst, performance.now()-t0); calls++;
                    return r;
                  };
                  const btns = [...document.querySelectorAll('.zoomctl button')];
                  const frame = () => new Promise(r =>
                    requestAnimationFrame(() => requestAnimationFrame(r)));
                  for (const b of btns) {
                    for (let i=0;i<3;i++){
                      b.click(); await frame(); await new Promise(r=>setTimeout(r,120));
                    }
                  }
                  window.layoutLabels = orig;
                  return {worst:+worst.toFixed(1), calls, buttons:btns.length};
                }"""
                # N20/N21 を「画面の状態ごとの総なめ」にする。
                # 2026-07-31 まで、手で選んだ8個のセレクタの *最初の1個ずつ* しか測っておらず、
                # 詳細シート・チューザー・一覧の住所・横向きを一度も測っていなかった。
                # 見えている文字と操作要素を全部拾う (地図の中の★は N24 の領分なので除く)。
                SWEEPJS = r"""(state) => {
                  const shown = e => { const cs = getComputedStyle(e);
                    return cs.display !== 'none' && cs.visibility !== 'hidden'
                        && parseFloat(cs.opacity) > .05 && e.getAttribute('aria-hidden') !== 'true'; };
                  // 閉じたパネルは display:none ではなく画面外へずらしてあるだけなので、
                  // 祖先の表示状態だけを見ると中身を全部拾ってしまう。面積の半分以上が
                  // 画面の中にあるものだけを「映っている」とする。
                  const vis = e => {
                    for (let n = e; n && n !== document.documentElement; n = n.parentElement)
                      if (!shown(n)) return false;
                    const r = e.getBoundingClientRect();
                    if (!(r.width > 0 && r.height > 0)) return false;
                    const iw = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
                    const ih = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
                    if (iw <= 0 || ih <= 0) return false;
                    return (iw * ih) >= .5 * (r.width * r.height); };
                  const sel = e => { const p = e.parentElement;
                    const cn = x => x && typeof x.className === 'string' && x.className.trim()
                      ? '.' + x.className.trim().split(/\s+/).slice(0,2).join('.') : '';
                    return e.id ? '#'+e.id
                      : (cn(p) ? cn(p)+' > ' : '') + e.tagName.toLowerCase() + cn(e); };
                  const texts = [], taps = [];
                  for (const e of document.querySelectorAll('body *')) {
                    if (e.closest('svg') || !vis(e)) continue;
                    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
                    const attrib = !!e.closest('footer, .credits, .foot');
                    const fs = +parseFloat(getComputedStyle(e).fontSize).toFixed(1);
                    if (fs < (attrib ? 12 : 14))
                      texts.push({state, sel:sel(e), fs, attrib,
                                  txt:(e.textContent||'').trim().slice(0,18)});
                  }
                  for (const e of document.querySelectorAll(
                        'button,a[href],input,select,[role="button"],[tabindex]')) {
                    if (e.closest('svg') || !vis(e)) continue;
                    const r = e.getBoundingClientRect();
                    if (r.width < 44 || r.height < 44)
                      taps.push({state, sel:sel(e), w:+r.width.toFixed(1), h:+r.height.toFixed(1),
                                 txt:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,18)});
                  }
                  // N28 ボタン・チップのラベルが語の途中で改行されていないか。
                  // 日本語の本文はどこで折り返しても正しいが、短いラベルが
                  // 「食べる・飲｜む・食料」のように切れると壊れて見える。
                  // 中点・読点・空白・括弧での改行は自然なので許す。
                  const OK_BREAK = '・、，  （(）)／/';
                  const wrap = [];
                  for (const e of document.querySelectorAll(
                        'button, .chip, .chip .lbl, [role="button"]')) {
                    if (!vis(e)) continue;
                    const t = [...e.childNodes].find(n => n.nodeType === 3 && n.textContent.trim());
                    if (!t) continue;
                    const txt = t.textContent;
                    if (txt.trim().length < 2) continue;
                    const rg = document.createRange();
                    let prevTop = null;
                    for (let i = 0; i < txt.length; i++) {
                      rg.setStart(t, i); rg.setEnd(t, i+1);
                      const b = rg.getBoundingClientRect();
                      if (prevTop !== null && b.top > prevTop + 2) {
                        const before = txt[i-1], after = txt[i];
                        if (!OK_BREAK.includes(before) && !OK_BREAK.includes(after))
                          wrap.push({state, sel:sel(e), txt:txt.trim().slice(0,20),
                                     at: txt.slice(Math.max(0,i-3), i) + '｜' + txt.slice(i, i+3)});
                      }
                      prevTop = b.top;
                    }
                  }
                  // N29 文字が入れ物からはみ出していないか (検索の説明文など)。
                  const clip = [];
                  for (const e of document.querySelectorAll('input')) {
                    if (!vis(e) || !e.placeholder) continue;
                    const cs = getComputedStyle(e);
                    const probe = document.createElement('span');
                    probe.style.cssText =
                      'position:absolute;visibility:hidden;white-space:pre;font:' + cs.font;
                    probe.textContent = e.placeholder;
                    document.body.appendChild(probe);
                    const need = probe.getBoundingClientRect().width;
                    probe.remove();
                    const has = e.getBoundingClientRect().width
                              - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
                    if (need > has + 1)
                      clip.push({state, sel:sel(e), txt:e.placeholder,
                                 need:Math.round(need), has:Math.round(has)});
                  }
                  return {texts, taps, wrap, clip};
                }"""
                # 画面の状態を作る手順。詳細シートは単一ボタンで開ける店、
                # チューザーは複数候補が出る店を選ぶ。
                STATES = [
                  ("詳細シート", r"""async () => {
                     const h=[...document.querySelectorAll('g.hit')].find(x=>{
                       try{return nearby(GEO.shops[+x.dataset.i]).length<=1;}catch(e){return false;}})
                       || document.querySelector('g.hit');
                     h.dispatchEvent(new MouseEvent('click',{bubbles:true}));
                     await new Promise(r=>setTimeout(r,450)); return true; }"""),
                  ("チューザー", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     const h=[...document.querySelectorAll('g.hit')].find(x=>{
                       try{return nearby(GEO.shops[+x.dataset.i]).length>1;}catch(e){return false;}});
                     if(!h) return false;
                     h.dispatchEvent(new MouseEvent('click',{bubbles:true}));
                     await new Promise(r=>setTimeout(r,450)); return true; }"""),
                  ("お店一覧", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     document.getElementById('listbtn').click();
                     await new Promise(r=>setTimeout(r,450)); return true; }"""),
                  ("検索中", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     const q=document.getElementById('q'); q.value='なか';
                     q.dispatchEvent(new Event('input',{bubbles:true}));
                     await new Promise(r=>setTimeout(r,450)); return true; }"""),
                ]
                UI = []
                for uw, uh in UI_DEVICES + UI_LANDSCAPE:
                    up = br.new_page(viewport={"width": uw, "height": uh})
                    up.goto(url, wait_until="load")
                    up.wait_for_timeout(1200)
                    sweep = {"texts": [], "taps": [], "wrap": [], "clip": []}
                    base = up.evaluate(SWEEPJS, "開いた直後")
                    for _k in ("texts", "taps", "wrap", "clip"):
                        sweep[_k] += base[_k]
                    for st, act in STATES:
                        if up.evaluate(act) is False:
                            continue
                        r = up.evaluate(SWEEPJS, st)
                        for _k in ("texts", "taps", "wrap", "clip"):
                            sweep[_k] += r[_k]
                    up.evaluate("""async () => {
                        document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                        const q=document.getElementById('q');
                        if(q){ q.value=''; q.dispatchEvent(new Event('input',{bubbles:true})); }
                        await new Promise(r=>setTimeout(r,350)); }""")
                    # 既存の測定 (N22/N23/N25/N26) は「開いた直後 + お店一覧」で行う
                    up.evaluate("()=>document.getElementById('listbtn').click()")
                    up.wait_for_timeout(350)
                    u = up.evaluate(UIJS)
                    u["vh"] = uh
                    u["portrait"] = uh > uw
                    u["sweep"] = sweep
                    u["layout"] = up.evaluate(TIMEJS)
                    UI.append(u)
                    up.close()
                REND["ui"] = UI
                br.close()
        except Exception as e:
            P("!! ブラウザ実測に失敗: %s: %s" % (type(e).__name__, e))
        if srv:
            srv.terminate()

byname = {r["name"]: r for r in (REND["rows"] if REND else [])}
walkby = {r["name"]: r for r in (REND.get("walk", {}).get("rows", []) if REND else [])}

# ---------------- 店ごとの判定 ----------------
P("=" * 78)
P("歩行者ゲート — 「地図を見ながら歩いて正しくその店に行けるか」")
P("=" * 78)
P("道路の塗り幅:", json.dumps({**FILLW, "spine": SPINE_W}, ensure_ascii=False))
P("建物ポリゴン(canvas内): %d / 交差点: %d / 信号: %d (うち交差点上 %d)"
  % (len(BLD), len(XN), len(signals), sum(SIG_OK)))
if REND:
    P("実測倍率: %.4f px/m (デフォルト) / 歩きズーム %.1f px/m を別測" % (REND["pxPerMeter"], WALK_PX_PER_M))
else:
    P("!! ブラウザ実測なし → N3/N4 の画面判定はスキップ (合格にはしない)")
P("")

fails = {k: [] for k in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10",
                         "N11", "N12", "N13", "N14", "N15", "N16", "N17", "N18", "N19",
                         "N20", "N21", "N22", "N23", "N24", "N25", "N26", "N27",
                         "N28", "N29")}
band = [s for s in shops if abs(TX(s) - spine_x(TY(s))) < 60]

# 同一住所グループ。ジオコーディング結果が同一なので、見分けるための分離を人工的に
# 入れている。よって真座標との差はその分離量を許容する。
# ハードコードだと取りこぼす (中山5-19-10 は3店・2026-07-30に実際に取りこぼした) ので
# 住所から導出する。真座標が40m以内に固まっているものだけを「同一地点」とみなす。
_by_addr = {}
for _s in shops:
    if _s.get("addr"):
        _by_addr.setdefault(_s["addr"], []).append(_s)
SAME_ADDR_GROUPS = []
for _a, _v in _by_addr.items():
    if len(_v) < 2:
        continue
    _cx = sum(TX(t) for t in _v) / len(_v)
    _cy = sum(TY(t) for t in _v) / len(_v)
    if max(math.hypot(TX(t) - _cx, TY(t) - _cy) for t in _v) <= 40:
        SAME_ADDR_GROUPS.append((_a, [t["name"] for t in _v]))
PAIRED = {n for _a, g in SAME_ADDR_GROUPS for n in g}
P("同一住所グループ (通り沿いの移動制限を免除): %d組" % len(SAME_ADDR_GROUPS))
for _a, _g in SAME_ADDR_GROUPS:
    P("   %s : %s" % (_a, " / ".join(_g)))
P("")
# 移動の上限は「距離」ではなく「向き」で決める。2026-07-30 敵対レビュー2周目の実測より:
#   住所ジオコーディング(gsi_addr)の点は街区の"道路に面した接点"にあるので、
#   建物の奥へ入れる動き = 通りに直交する動き = 正しいセットバック補正。
#   位置関係を壊すのは 通りに沿う動き (どの店の隣か・信号の上下が変わる)。
#   実測: 花祭壇 15.9m のうち沿い0.9m・直交15.8m / ウエルシア 14.4m のうち沿い0.2m・直交14.4m
MAX_ALONG = {"osm:exact": 4.0, "osm:partial": 4.0, "gsi_addr": 8.0, "approx": 8.0}
MAX_CROSS = {"osm:exact": 20.0, "osm:partial": 20.0, "gsi_addr": 20.0, "approx": 25.0}
# 同一住所グループは1点を共有しているので、判別のために街区の奥 (通りに直交) へ
# 広げる必要がある。この許容は「グループの構成員か」で決める。src の値で決めると
# src を書き換えるだけで上限が緩むため (2026-07-30 に実際に10店で発生した)。
MAX_CROSS_PAIRED = 25.0
MAX_WARP_ALONG = 6.0      # 隣接ペアの「通り沿いの間隔」の変化の上限 (m)

for s in shops:
    nm, x, y = s["name"], s["x"], s["y"]

    # N1 建物の中にいる (公園は自分のポリゴン内)
    if nm not in OPEN_SITES:
        if BLD and not in_building(x, y):
            fails["N1"].append(nm)
    else:
        pk = next((p for p in parks if p["name"] == nm), None)
        if pk and not poly_inside(pk["pts"], x, y):
            fails["N1"].append(nm + "(公園ポリゴン外)")

    # N2 道路の帯の内側にいない
    for r in roads:
        if road_d(x, y, r) < road_w(r) / 2.0 + SETBACK:
            fails["N2"].append("%s ← %s (%.1fm)" % (nm, r.get("name") or "(無名 " + r["cls"] + ")", road_d(x, y, r)))
            break

    # N3 歩きズームで★の絵が道路の帯にかからない / 見える大きさである
    w = walkby.get(nm)
    if w:
        rad = w["starMapM"] / 2.0
        hit = next((r for r in roads if road_d(x, y, r) < road_w(r) / 2.0 + rad), None)
        if hit:
            fails["N3"].append("%s ★%.1fm が %s にかかる" % (nm, w["starMapM"], hit.get("name") or hit["cls"]))
        if w["starPxNow"] < MIN_STAR_PX:
            fails["N3"].append("%s ★が%.1fpx (最小%.0f)" % (nm, w["starPxNow"], MIN_STAR_PX))

    # N4 ラベルが自分の★に一意に結びつく
    b = byname.get(nm)
    if b and b.get("labelShown") and b.get("lx") is not None:
        dself = math.hypot(b["lx"] - x, b["ly"] - y)
        dother = min((math.hypot(b["lx"] - o["x"], b["ly"] - o["y"]) for o in shops if o is not s), default=1e9)
        if dother <= dself:
            fails["N4"].append("%s (自分%.0fm / 他人%.0fm)" % (nm, dself, dother))

    # N5 バス通り沿い: 東西が実座標と一致 + 向かいの店が反対側にいる
    if s in band:
        if side(x, y) != side(TX(s), TY(s)):
            fails["N5"].append("%s 東西が反転" % nm)
        opp = [o for o in band if side(o["x"], o["y"]) != side(x, y) and abs(o["y"] - y) < 40]
        opp_true = [o for o in band if side(TX(o), TY(o)) != side(TX(s), TY(s)) and abs(TY(o) - TY(s)) < 40]
        if opp_true and not opp:
            fails["N5"].append("%s 真では向かいに店があるのに表示では無い" % nm)

    # N6 最寄り信号との南北関係 + その信号が交差点にある
    if s in band and signals:
        k = min(range(len(signals)), key=lambda i: math.hypot(signals[i][0] - TX(s), signals[i][1] - TY(s)))
        sx, sy = signals[k]
        if abs(TY(s) - sy) >= 15 and (TY(s) - sy) * (y - sy) < 0:
            fails["N6"].append("%s 信号との上下が逆" % nm)
        if not SIG_OK[k]:
            d = min((math.hypot(sx - q[0], sy - q[1]) for q in XN), default=1e9)
            fails["N6"].append("%s の目印になる信号(%.0f,%.0f)が交差点にない(%.0fm)" % (nm, sx, sy, d))

# ---- 通りの方向で移動を分解する ----
def street_axis(y):
    h = 2.0
    ax, ay = spine_x(y + h) - spine_x(y - h), 2 * h
    L = math.hypot(ax, ay) or 1.0
    return ax / L, ay / L          # 通りに沿う単位ベクトル


def decompose(s):
    """真座標からの移動を (通りに沿う, 通りに直交) に分ける"""
    tx, ty = TX(s), TY(s)
    dx, dy = s["x"] - tx, s["y"] - ty
    ax, ay = street_axis(ty)
    return abs(dx * ax + dy * ay), abs(dx * ay - dy * ax)


def along_coord(s, use_true=False):
    """通り沿いの位置 (南北の順序を表す1次元座標)"""
    x, y = (TX(s), TY(s)) if use_true else (s["x"], s["y"])
    ax, ay = street_axis(TY(s))
    return x * ax + y * ay


# ---- N7 移動が「通りに沿う」方向に偏っていない (位置関係を壊していない) ----
for s in shops:
    al, cr = decompose(s)
    src = s.get("src", "approx")
    lim_a = MAX_ALONG.get(src, 8.0)
    # 直交の上限は「同一住所グループの構成員か」で決める (src では決めない)
    lim_c = MAX_CROSS_PAIRED if s["name"] in PAIRED else MAX_CROSS.get(src, 25.0)
    if s["name"] not in PAIRED and al > lim_a:
        fails["N7"].append("%s が通りに沿って%.1fm動いた (上限%.0fm / %s)" % (s["name"], al, lim_a, src))
    if cr > lim_c:
        fails["N7"].append("%s が通りに直交して%.1fm動いた (上限%.0fm / %s)" % (s["name"], cr, lim_c, src))

# ---- N8 ★同士が重ならない (歩きズームでの★直径より離れている) ----
star_m = max((r["starMapM"] for r in (REND.get("walk", {}).get("rows", []) if REND else [])), default=4.0)
MIN_SEP = max(3.0, star_m * 1.2)
for i in range(len(shops)):
    for j in range(i + 1, len(shops)):
        a, b = shops[i], shops[j]
        d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        if d < MIN_SEP:
            fails["N8"].append("%s ⇔ %s が%.1fm (★直径%.1fm・最低%.1fm)"
                               % (a["name"], b["name"], d, star_m, MIN_SEP))

# ---- N9 公園ポリゴンとの内外が真座標と一致 ----
for pk in parks:
    for s in shops:
        if poly_inside(pk["pts"], TX(s), TY(s)) != poly_inside(pk["pts"], s["x"], s["y"]):
            fails["N9"].append("%s と %s の内外が真座標と違う" % (s["name"], pk["name"]))

# ---- N10 「通り沿いの間隔」が歪んでいない ----
# 直線距離ではなく通り沿いの1次元間隔で見る。向かい合う店の間隔(通りを横切る距離)は
# セットバックで正しく変わるが、通り沿いの間隔が変わると「どの店の隣か」が壊れる。
bs = sorted(band, key=lambda s: TY(s))
for a, b in zip(bs, bs[1:]):
    if a["name"] in PAIRED and b["name"] in PAIRED:
        continue
    gt = abs(along_coord(a, True) - along_coord(b, True))
    gd = abs(along_coord(a) - along_coord(b))
    if abs(gd - gt) > MAX_WARP_ALONG:
        fails["N10"].append("%s ⇔ %s 通り沿いの間隔 真%.1fm → 表示%.1fm (%+.1fm)"
                            % (a["name"], b["name"], gt, gd, gd - gt))

# ---- N11-N14 概観ズーム (最初に見える倍率) の見やすさ ----
# 歩きズームは N3/N4/N8 が見ている。ここは「開いた瞬間の画面」を見る。
def _rect_d(rc, sx, sy):
    """ラベル矩形の縁から★中心までの最短距離。中心で測ると長い店名が不利になる。"""
    l, t, r, b = rc
    return math.hypot(max(l - sx, 0.0, sx - r), max(t - sy, 0.0, sy - b))


def _zoom_checks(D, zname, is_default):
    if not D:
        return
    rows = D.get("rows") or []
    rp = D.get("roadPx") or {}
    main = rp.get("main", 0.0)
    s0 = D.get("pxPerMeter") or 1.0
    if is_default:
        if main and main < ROAD_FLOOR_PX:
            fails["N11"].append("%s でバス通りが%.1fpx (通りとして読める床%.0fpx)"
                                % (zname, main, ROAD_FLOOR_PX))
        for r in rows:
            if main and r["starPxNow"] / main > STAR_ROAD_MAX:
                fails["N12"].append("%s ★%.1fpx が通り%.1fpx の%.2f倍 (上限%.2f)"
                                    % (r["name"], r["starPxNow"], main,
                                       r["starPxNow"] / main, STAR_ROAD_MAX))
    # N15 その倍率で実際に描かれている帯に★が「乗って」いないか。
    # 帯の幅は「描画px ÷ 倍率」で地図単位に戻す (画面px床が効いている場合を含める)。
    #
    # 判定は2段。「絵が一切触れない」を要求すると物理的に達成できないため
    # (2026-07-30 実測):
    #   既定0.92px/m・★7.2px(地図7.83m/半径3.91m)・バス通り半幅6.5m
    #   → 一切触れないには中心線から 10.41m 必要
    #   実際: 藤倉設備工業 9.21m / BAKERY&BAKE EndRoll 9.41m ← 現実がそれより近い
    #   ★を可読の下限6px(MIN_STAR_PX)まで縮めても必要9.76mで この2店は解消しない
    # ボスの訴えは「道路の上に店舗がある」なので、乗っているか(=中心が帯の内側か)を
    # 不合格とし、先端のかすりは量に上限を置いて歯止めにする。
    DRAWN = {}
    for c in ("main", "major", "mid", "minor"):
        if c in rp:
            DRAWN["road-" + c] = rp[c] / s0
    byn = {r["name"]: r for r in rows}
    for s in shops:
        r = byn.get(s["name"])
        if not r:
            continue
        rad = r["starMapM"] / 2.0
        for rd in roads:
            key = "road-main" if rd.get("guide_spine") else CLSMAP.get(rd["cls"], "road-mid")
            half = DRAWN.get(key, road_w(rd)) / 2.0
            d = road_d(s["x"], s["y"], rd)
            nm2 = rd.get("name") or rd["cls"]
            if d < half:      # ★の中心が帯の内側 = 道路の上に乗っている
                fails["N15"].append("%s の★が %s の帯の上に乗っている (中心線から%.1fm / 帯の半幅%.1fm) (%s)"
                                    % (s["name"], nm2, d, half, zname))
                break
            bite = half + rad - d
            if bite > MAX_STAR_ROAD_BITE:
                fails["N15"].append("%s ★%.1fm が %s に%.1fm食い込む (上限%.1fm) (%s)"
                                    % (s["name"], r["starMapM"], nm2, bite,
                                       MAX_STAR_ROAD_BITE, zname))
                break
    stars = [r for r in rows if r.get("starCx") is not None]
    for r in rows:
        rc = r.get("labelRect")
        if not rc:
            continue
        inside = [o["name"] for o in stars
                  if o["i"] != r["i"] and rc[0] <= o["starCx"] <= rc[2]
                  and rc[1] <= o["starCy"] <= rc[3]]
        if inside:
            fails["N13"].append("%s のラベルが %s の★を内包 (%s)"
                                % (r["name"], "/".join(inside[:2]), zname))
        if r.get("starCx") is None:
            continue
        own = _rect_d(rc, r["starCx"], r["starCy"])
        oth = sorted((_rect_d(rc, o["starCx"], o["starCy"]), o["name"])
                     for o in stars if o["i"] != r["i"])
        if oth and (own > LABEL_MARGIN_MAX * oth[0][0] if oth[0][0] > 0 else own > 0):
            fails["N14"].append("%s のラベル 自分%.0fpx / %s %.0fpx (%s)"
                                % (r["name"], own, oth[0][1], oth[0][0], zname))


if REND:
    _zoom_checks(REND, "既定ズーム", True)
    _zoom_checks(REND.get("walk"), "歩きズーム", False)
    # N17 固定UI (お店一覧ボタン / ズーム操作) が店名を覆っていないか。
    # 2026-07-30: 西原歯科医院 のラベルが「お店一覧」に36%覆われていた。
    # 表示域の端で切れるぶんは正常なので除いてある (パンで届く)。
    for c in (REND.get("uiCovered") or []):
        if c["pct"] >= 10:
            fails["N17"].append("%s のラベルが固定UIに%d%%覆われている (既定ズーム)"
                                % (c["name"], c["pct"]))

    # N18 こどもの声バッジが自分の★に一意に結びつくか。
    # 2026-07-30: 11個中4個が他店の★のほうが近く、声の持ち主を取り違える。
    # バッジは★から約17.5m (地図単位固定) の位置に出るが、隣の店は8.4mまで近づける。
    # N19 信号アイコンと★/ラベルが重なっていないか。
    # 描画順は gRoads(信号) → gShops(★/ラベル) なので、隠れるのは信号のほう。
    # 店は読めるが、N6 で「歩く時の目印」として使う信号が読めなくなる。
    # 信号は22m (道路13mの1.68倍) の地図単位固定で、カットショップ NOBU と重なっていた。
    for zk, zn in (("", "既定ズーム"), ("walk", "歩きズーム")):
        D = REND if not zk else REND.get(zk)
        if not D:
            continue
        for b in (D.get("badges") or []):
            if b.get("own") and b.get("nearest") and b["nearest"] != b["own"]:
                fails["N18"].append("%s の声バッジが %s の★のほうに近い (自分%.0fpx / 相手%.0fpx) (%s)"
                                    % (b["own"], b["nearest"], b["ownPx"], b["nearestPx"], zn))
        for h in (D.get("sigHit") or []):
            fails["N19"].append("信号アイコンが %s の%sと重なり、信号が読めない (%s)"
                                % (h["n"], h["kind"], zn))

    # ---- N20-N24 UI/UX。画面幅を変えて操作部だけ見る ----
    _tap_bad, _txt_bad = {}, {}
    for u in (REND.get("ui") or []):
        vw = u["vw"]
        dev = "%dx%d" % (vw, u.get("vh", 0))
        # N20/N21 は画面の状態ごとの総なめ。直す場所はセレクタ単位なので、
        # 端末・状態をまたいで1件にまとめる (同じ1箇所を136件に数えても読めないだけ)。
        for t in (u.get("sweep") or {}).get("taps", []):
            e = _tap_bad.setdefault(t["sel"], {"txt": t["txt"], "w": t["w"], "h": t["h"], "where": []})
            e["w"] = min(e["w"], t["w"]); e["h"] = min(e["h"], t["h"])
            e["where"].append("%s %s" % (dev, t["state"]))
        for t in (u.get("sweep") or {}).get("texts", []):
            e = _txt_bad.setdefault(t["sel"], {"txt": t["txt"], "fs": t["fs"],
                                               "attrib": t["attrib"], "where": []})
            e["fs"] = min(e["fs"], t["fs"])
            e["where"].append("%s %s" % (dev, t["state"]))
        for o in u["offscreen"]:
            fails["N22"].append("%s (%s) が画面の外にある [幅%d]" % (o["nm"], o["txt"], vw))
        for c in (u.get("credits") or []):
            fails["N25"].append("「%s」が固定UIに%d%%覆われている [幅%d]"
                                % (c["txt"], c["pct"], vw))
        # N23 / N26 は縦向きだけ。横向きは「地図が主」でなく「一覧が主」の使い方になり、
        # 同じ床を当てると達成不能な要求になる (縦向きの床は実測で導出したもの)。
        if u.get("portrait", True):
            if u["mapRatio"] < MAP_MIN_RATIO:
                fails["N23"].append("地図が画面の%.0f%%しかない (床%.0f%%) [%dx%d]"
                                    % (u["mapRatio"] * 100, MAP_MIN_RATIO * 100, vw, u.get("vh", 0)))
            if u.get("mapH", 0) < MAP_MIN_PX:
                fails["N23"].append("地図の高さが%dpxしかない (床%.0fpx) [%dx%d]"
                                    % (u["mapH"], MAP_MIN_PX, vw, u.get("vh", 0)))
            for n in (u.get("voiceHidden") or []):
                fails["N26"].append("%s のこどもの声ラベルが出ていない [%dx%d]"
                                    % (n, vw, u.get("vh", 0)))
        else:
            if u.get("mapH", 0) < LAND_MAP_MIN_PX or u["mapRatio"] < LAND_MAP_MIN_RATIO:
                fails["N23"].append("横向きで地図が%dpx (画面の%.0f%%) しかない "
                                    "(床%.0fpx / %.0f%%) [%dx%d]"
                                    % (u.get("mapH", 0), u["mapRatio"] * 100,
                                       LAND_MAP_MIN_PX, LAND_MAP_MIN_RATIO * 100,
                                       vw, u.get("vh", 0)))
        lay = u.get("layout") or {}
        if not lay.get("calls"):
            fails["N27"].append("ラベル配置の時間を測れなかった (呼び出し%s回/ズームボタン%s個) [%dx%d]"
                                % (lay.get("calls"), lay.get("buttons"), vw, u.get("vh", 0)))
        elif lay.get("worst", 0) > MAX_LAYOUT_MS:
            fails["N27"].append("ズーム1回のラベル配置に%.0fms かかる (上限%.0fms) [%dx%d]"
                                % (lay["worst"], MAX_LAYOUT_MS, vw, u.get("vh", 0)))
    for _k, _n, _fmt in (("wrap", "N28", "%s (%s) が「%s」で改行される [%s]"),
                         ("clip", "N29", "%s (%s) が入れ物に収まらない 必要%dpx / 幅%dpx [%s]")):
        _seen = {}
        for u in (REND.get("ui") or []):
            for it in (u.get("sweep") or {}).get(_k, []):
                _seen.setdefault(it["sel"], []).append((it, "%dx%d %s" % (u["vw"], u.get("vh", 0), it["state"])))
        for sel_, rows in sorted(_seen.items()):
            it = rows[0][0]
            where = sorted(set(r[1] for r in rows))
            wtxt = "どの端末でも" if len(where) >= 12 else where[0] + ("" if len(where) == 1 else " ほか%d" % (len(where)-1))
            if _n == "N28":
                fails[_n].append(_fmt % (sel_, it["txt"], it["at"], wtxt))
            else:
                fails[_n].append(_fmt % (sel_, it["txt"], it["need"], it["has"], wtxt))

    def _where(w):
        # 全端末・全状態に出るなら「どこでも」。そうでなければ最初の1つを示す。
        u = sorted(set(w))
        return "どの端末でも" if len(u) >= 12 else u[0] + ("" if len(u) == 1 else " ほか%d" % (len(u) - 1))

    for sel_, e in sorted(_tap_bad.items(), key=lambda kv: min(kv[1]["w"], kv[1]["h"])):
        fails["N20"].append("%s (%s) が %.0fx%.0fpx (最小%.0f) [%s]"
                            % (sel_, e["txt"], e["w"], e["h"], TAP_MIN_PX, _where(e["where"])))
    for sel_, e in sorted(_txt_bad.items(), key=lambda kv: kv[1]["fs"]):
        lim = ATTRIB_MIN_PX if e["attrib"] else TEXT_MIN_PX
        fails["N21"].append("%s (%s) が %.1fpx (床%.0f) [%s]"
                            % (sel_, e["txt"], e["fs"], lim, _where(e["where"])))

    # N24 密集地でチューザーが出る店の数。既定ズームでは指(44px)が2店(最短8.5m=7.8px)を
    # 覆うので不可避。だが nearby が地図単位固定(22m)だとズームしても減らない
    # (2026-07-30 実測: 5px/m でも21件。店は42px離れているのに出る)。
    # 画面px基準にすれば歩きズームで8件、拡大しきれば0件になり単一ボタンで押せる。
    wk = REND.get("walk") or {}
    if wk.get("chooserShops") is not None and wk["chooserShops"] > 10:
        fails["N24"].append("歩きズームでチューザーが出る店が%d件 (上限10件)。"
                            "nearby が画面px基準になっていない" % wk["chooserShops"])

# ---- N16 座標の出典 (src) が書き換えられていない ----
# src は N7 の上限を決めるキーなので、書き換えれば閾値を緩めたのと同じになる。
# 2026-07-30、同一住所の分離のために10店が gsi_addr → approx に変わり、
# うち1店 (中杜建設) が直交23.8m を approx の25m 上限で通していた。
_sbp = os.path.join(HERE, "src_baseline.json")
if os.path.exists(_sbp):
    _base = json.load(io.open(_sbp, encoding="utf-8"))["src"]
    for s in shops:
        b = _base.get(s["name"])
        if b and s.get("src") != b:
            fails["N16"].append("%s の出典が %s → %s に書き換わっている (src_baseline.json と不一致)"
                                % (s["name"], b, s.get("src")))

LBL = {"N1": "建物の中にいる", "N2": "道路の帯の内側にいない",
       "N3": "歩きズームで★が道路にかからず見える大きさ", "N4": "ラベルが自分の★に一意に結びつく",
       "N5": "通りの東西と向かい合いが成立", "N6": "目印の信号が使える",
       "N7": "移動が通りに沿う方向に偏っていない", "N8": "★同士が重なっていない",
       "N9": "公園との内外が真座標と一致", "N10": "通り沿いの間隔が歪んでいない",
       "N11": "既定ズームで通りが通りとして読める", "N12": "既定ズームで★が通りを覆わない",
       "N13": "ラベルが他店の★を内包しない", "N14": "ラベルの縁から自分の★が明確に最近傍",
       "N15": "★が道路の帯の上に乗っていない",
       "N16": "座標の出典(src)が書き換えられていない",
       "N17": "固定UIが店名を覆っていない",
       "N18": "こどもの声バッジが自分の★に一意に結びつく",
       "N19": "信号アイコンが★やラベルと重なっていない",
       "N20": "操作要素が44x44px以上", "N21": "文字が14px以上 (帰属表示は12px)",
       "N22": "操作要素が画面の外に出ていない", "N23": "地図が画面の62%以上",
       "N24": "拡大すればチューザーなしで単一ボタンで押せる",
       "N25": "固定UIが帰属表示・注記を覆っていない",
       "N26": "こどもの声の店のラベルが端末を問わず出ている",
       "N27": "ズームしても地図の再描画が止まらない",
       "N28": "ボタンの文字が語の途中で改行されない",
       "N29": "文字が入れ物からはみ出していない"}
for k in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10",
          "N11", "N12", "N13", "N14", "N15", "N16", "N17", "N18", "N19",
          "N20", "N21", "N22", "N23", "N24", "N25", "N26", "N27", "N28", "N29"):
    v = sorted(set(fails[k]))
    P("【%s】%s — 違反 %d件" % (k, LBL[k], len(v)))
    for t in v[:14]:
        P("      " + t)
    if len(v) > 14:
        P("      ...他 %d件" % (len(v) - 14))

# ---------------- 全体 ----------------
P("")
P("【全体】")
gfail = []
if REND:
    P("  ★表示数: %d / 60" % len(REND["rows"]))
    if len(REND["rows"]) != 60:
        gfail.append("★が60件でない")
    wv = REND.get("walk", {}).get("labelsVisible", 0)
    P("  ラベル可視: デフォルト %d / 歩きズーム %d / bbox交差 %d"
      % (REND["labelsVisible"], wv, REND["labelCross"]))
    if REND["labelCross"]:
        gfail.append("ラベルbbox交差 %d件" % REND["labelCross"])
    # N4 は「ラベルを全部隠せば通る」盲点があるので、可視数の下限を全体側で見る
    if REND["labelsVisible"] < 40:
        gfail.append("デフォルトのラベル可視が%d件 (40件未満は情報が落ちすぎ)" % REND["labelsVisible"])
    if wv and wv < 60:
        gfail.append("歩きズームでもラベルが%d件しか出ない (60件必要)" % wv)
    P("  JSエラー: %d" % REND["jsErrors"])
    if REND["jsErrors"]:
        gfail.append("JSエラー %d件" % REND["jsErrors"])
    mn = min((r["starPxNow"] for r in REND["rows"]), default=0)
    P("  ★の画面サイズ (デフォルト): 最小 %.1fpx" % mn)
    if mn < MIN_STAR_PX:
        gfail.append("★が%.1fpx (最小%.0f)" % (mn, MIN_STAR_PX))
    smap = sorted({r["starMapM"] for r in REND["rows"]})
    wmap = sorted({r["starMapM"] for r in REND.get("walk", {}).get("rows", [])})
    P("  ★の地図空間サイズ: デフォルト %s m / 歩きズーム %s m" % (smap[:3], wmap[:3]))
    if wmap and wmap[-1] > 12.0:
        gfail.append("歩きズームで★が%.1fm (実店舗の間口10m超・縮尺の外)" % wmap[-1])
else:
    gfail.append("ブラウザ実測なし")
P("  信号が交差点に立っている: %d / %d" % (sum(SIG_OK), len(signals)))
if sum(SIG_OK) != len(signals):
    gfail.append("交差点にない信号 %d基" % (len(signals) - sum(SIG_OK)))

nav_fail = set()
for k in fails:
    for t in fails[k]:
        nav_fail.add(t.split(" ")[0].split("(")[0].split("←")[0].strip())
P("")
P("=" * 78)
P("歩ける店 (N1..N29 全通過): %d / %d" % (len(shops) - len(nav_fail), len(shops)))
P("全体の不合格項目: %d件 %s" % (len(gfail), gfail if gfail else ""))
total = sum(len(set(v)) for v in fails.values()) + len(gfail)
P("判定: %s (違反 %d件)" % ("PASS" if total == 0 else "FAIL", total))
P("=" * 78)

if A.json:
    io.open(A.json, "w", encoding="utf-8").write(json.dumps(
        {"fails": {k: sorted(set(v)) for k, v in fails.items()}, "global": gfail,
         "navigable": len(shops) - len(nav_fail), "shops": len(shops),
         "verdict": "PASS" if total == 0 else "FAIL"}, ensure_ascii=False, indent=1))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
print("\n".join(OUT))
sys.exit(0 if total == 0 else 1)
