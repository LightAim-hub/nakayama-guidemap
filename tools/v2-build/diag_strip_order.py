#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通り(二列)ビューの「位置関係」を実測する。

なぜ要るか (2026-08-14):
  あみさんから「通りの地図の位置関係がズレている。信号機の場所とか」と指摘を受けた。
  ところが diag_geometry.py は G3=0基・G4 取りこぼし0 と言う。
  **あの検査は「OSM と自分の整合」しか見ていない**。二列ビューでの並びは誰も測っていない。

  計器が緑なのに人が見えている時は、たいてい計器が別のものを測っている。
  だから直す前に、ここで「人が歩く順」と「画面に並ぶ順」を突き合わせる。

測るもの:
  S1 バス通りが canvas の y について単調か
     (単調でないと streetXAtY() の y→x 走査が最初に跨いだ区間を返し、東西判定が入れ替わる)
  S2 歩く順 (通り沿いの弧長 s) と 表示順 (y の昇順) の食い違いペア
  S3 信号の歩く順の位置と、y 順での位置の食い違い
     (二列は信号を y で内挿して置くので、S2 がズレていれば信号だけが店に対して動く)
  S4 東西の判定: streetXAtY() 方式 と 最近点の法線方式 が食い違う店

外部への通信はしない。index.html の GEO を読むだけ。

usage: python diag_strip_order.py [target.html]
"""
import io
import json
import math
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

ROOT = os.path.join(os.environ.get("USERPROFILE", ""), "nakayama-guidemap")
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "index.html")

SIDE_BAND = 60.0        # template.html の stripAlong と同じ (通り沿いとみなす幅)
SIGNAL_ON_STREET = 30.0  # これより通りから遠い信号は「中山バス通りの信号」ではない
OUT = []


def P(*a):
    OUT.append(" ".join(str(x) for x in a))


src = io.open(TARGET, encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
shops, signals = G["shops"], G.get("signals", [])
busways = G.get("busway", []) or []
main = sorted(busways, key=len, reverse=True)[0] if busways else []


def true_point(s):
    x = s["tx"] if isinstance(s.get("tx"), (int, float)) else s["x"]
    y = s["ty"] if isinstance(s.get("ty"), (int, float)) else s["y"]
    return x, y


def seg_len(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


CUM = [0.0]
for i in range(1, len(main)):
    CUM.append(CUM[-1] + seg_len(main[i - 1], main[i]))


def project(px, py):
    """通りの折れ線への最近点。(弧長 s, 最短距離 d, 左右符号) を返す。

    符号は進行方向ベクトルとの外積。負=左手側 / 正=右手側。
    """
    best = (0.0, float("inf"), 0.0)
    for i in range(1, len(main)):
        a, b = main[i - 1], main[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        den = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / den)) if den else 0.0
        qx, qy = a[0] + t * dx, a[1] + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best[1]:
            cross = dx * (py - a[1]) - dy * (px - a[0])
            best = (CUM[i - 1] + t * math.sqrt(den), d, cross)
    return best


def street_x_at_y(y):
    """template.html の streetXAtY() をそのまま写したもの (同じ挙動で比べるため)"""
    if not main:
        return G["meta"]["W"] / 2
    if y <= main[0][1]:
        return main[0][0]
    if y >= main[-1][1]:
        return main[-1][0]
    for i in range(1, len(main)):
        a, b = main[i - 1], main[i]
        if y < min(a[1], b[1]) or y > max(a[1], b[1]) or a[1] == b[1]:
            continue
        t = (y - a[1]) / (b[1] - a[1])
        return a[0] + t * (b[0] - a[0])
    return main[-1][0]


P("=" * 76)
P("通り(二列)ビューの位置関係 診断  対象:", os.path.basename(TARGET))
P("=" * 76)
P("バス通り %d本 / 採用した折れ線 %d点 / 全長 %.1fm" % (len(busways), len(main), CUM[-1] if CUM else 0))
P("店 %d / 信号 %d" % (len(shops), len(signals)))
P("")

# ---- S1 通りが y について単調か -------------------------------------------
P("【S1】バス通りは canvas の y について単調か")
P("      単調でないと streetXAtY() の y→x 走査が最初に跨いだ区間を返し、東西判定が入れ替わる")
dirs = [1 if main[i][1] > main[i - 1][1] else (-1 if main[i][1] < main[i - 1][1] else 0)
        for i in range(1, len(main))]
flips = [i for i in range(1, len(dirs)) if dirs[i] and dirs[i - 1] and dirs[i] != dirs[i - 1]]
P("      向きが変わる箇所: %d" % len(flips))
for i in flips:
    P("        点%d 付近 (x%.0f, y%.0f) で y の進みが反転" % (i, main[i][0], main[i][1]))
P("      判定: %s" % ("単調 (y順 = 通り沿い順)" if not flips else "🔴 単調でない"))
P("")

# ---- S2 歩く順 vs 表示順 ---------------------------------------------------
rows = []
for i, s in enumerate(shops):
    x, y = true_point(s)
    sx = street_x_at_y(y)
    if abs(x - sx) > SIDE_BAND:
        continue                                  # 二列に出ない遠方店
    s_arc, dist, cross = project(x, y)
    rows.append({"name": s["name"], "x": x, "y": y, "s": s_arc, "d": dist,
                 "cross": cross, "side_x": "west" if x < sx else "east"})

by_y = sorted(rows, key=lambda r: (r["y"], r["x"]))
by_s = sorted(rows, key=lambda r: (r["s"], r["x"]))
pos_y = {r["name"]: i for i, r in enumerate(by_y)}
pos_s = {r["name"]: i for i, r in enumerate(by_s)}

inversions = []
names = [r["name"] for r in rows]
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = names[i], names[j]
        if (pos_y[a] - pos_y[b]) * (pos_s[a] - pos_s[b]) < 0:
            gap = abs(by_s[pos_s[a]]["s"] - by_s[pos_s[b]]["s"])
            inversions.append((gap, a, b))
inversions.sort(reverse=True)

P("【S2】歩く順 (通り沿いの弧長) と 表示順 (y の昇順) の食い違い")
P("      二列に出る店: %d" % len(rows))
P("      入れ替わっているペア: %d組" % len(inversions))
for gap, a, b in inversions[:15]:
    P("        %-24s ⇔ %-24s  通り沿いに %.1fm 離れているのに順が逆" % (a, b, gap))
if len(inversions) > 15:
    P("        …ほか %d組" % (len(inversions) - 15))
P("")

# ---- S3 信号 ---------------------------------------------------------------
P("【S3】信号を y で置いた時と、歩く順で置いた時のズレ")
P("      二列は信号を y から内挿して置く。y順と歩く順が違えば信号だけが店に対して動く")
sig_rows = []
for k, p in enumerate(signals):
    s_arc, dist, cross = project(p[0], p[1])
    if dist > SIGNAL_ON_STREET:
        continue                                   # 通り沿いでない信号は S5 で扱う
    # y 順で見た時に「直前に来る店」と、歩く順で見た時に「直前に来る店」
    prev_y = None
    for r in by_y:
        if r["y"] <= p[1]:
            prev_y = r["name"]
    prev_s = None
    for r in by_s:
        if r["s"] <= s_arc:
            prev_s = r["name"]
    sig_rows.append((k, p, dist, prev_y, prev_s))
    mark = "  🔴 違う" if prev_y != prev_s else ""
    P("        信号%-2d (x%.0f,y%.0f) 通りまで%.1fm  y順の直前=%s / 歩く順の直前=%s%s"
      % (k, p[0], p[1], dist, prev_y, prev_s, mark))
mismatch = sum(1 for r in sig_rows if r[3] != r[4])
P("      二列に出る信号 %d基 / 直前の店が食い違う %d基" % (len(sig_rows), mismatch))
P("")

# ---- S4 東西の判定 ---------------------------------------------------------
P("【S4】東西の判定: streetXAtY() 方式 と 最近点の法線方式 の食い違い")
side_bad = []
for r in rows:
    by_normal = "west" if r["cross"] > 0 else "east"
    if by_normal != r["side_x"]:
        side_bad.append((r["name"], r["side_x"], by_normal, r["d"]))
P("      食い違い: %d店" % len(side_bad))
for name, a, b, d in side_bad[:12]:
    P("        %-24s 画面=%s / 最近点=%s (通りまで%.1fm)" % (name, a, b, d))
P("")

# ---- S5 二列に出しているのに通り沿いにない信号 -----------------------------
P("【S5】二列 (中山バス通りの一本線) に並べる信号が、通り沿いのものだけか")
P("      2026-08-14 まで buildStrip() は GEO.signals を絞らずに全基を通りの線上へ置いていた。")
P("      別の道路の信号がバス通りの信号として並ぶ (最遠622m)。これが位置ズレ指摘の原因。")
_m = re.search(r"STRIP_SIGNAL_MAX_M\s*=\s*([0-9.]+)", src)
limit = float(_m.group(1)) if _m else None
if limit is None:
    P("      🔴 STRIP_SIGNAL_MAX_M が無い = 絞り込みをしていない")
else:
    P("      画面側の絞り込み: STRIP_SIGNAL_MAX_M = %.0fm" % limit)
off, drawn = [], []
for k, p in enumerate(signals):
    s_arc, dist, cross = project(p[0], p[1])
    on_street = dist <= SIGNAL_ON_STREET
    shown = (limit is None) or (dist <= limit)
    if shown and not on_street:
        tag = "🔴 別の道路なのに二列に出る"
    elif shown:
        tag = "二列に出る (通り沿い)"
    else:
        tag = "二列には出さない"
    P("        信号%-2d (x%.0f,y%.0f)  通りまで %6.1fm  %s" % (k, p[0], p[1], dist, tag))
    if shown:
        drawn.append(k)
    if shown and not on_street:
        off.append((k, p, dist))
P("      GEO の信号 %d基 / 二列に出る %d基 / そのうち通り沿いでない %d基 (最遠 %.1fm)"
  % (len(signals), len(drawn), len(off), max([d for _, _, d in off]) if off else 0))
P("      ※ 地図ビューは真の座標に描くので %d基すべて出るのが正しい" % len(signals))
P("")

P("=" * 76)
P("要約: S1 反転=%d / S2 入替=%d組 / S3 信号の食い違い=%d基 / S4 東西の食い違い=%d店 / S5 通り沿いでない信号=%d基"
  % (len(flips), len(inversions), mismatch, len(side_bad), len(off)))
P("")
P("読み方: S1 が反転>0 なら、まず streetXAtY() が原因。")
P("        S2 が0でないなら、二列は『歩く順』でなく『y の順』に並んでいる。")
P("        S3 は、二列の信号が店に対してどれだけ動くかの実測値。")
P("        S5 が0でないなら、二列に『その通りにない信号』を描いている。")

print("\n".join(OUT))
