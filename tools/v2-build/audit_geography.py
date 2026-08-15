#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""位置と方角の整合性を実座標で当て直す (2026-08-15 ボス指示)。

なぜ要るか:
  地図の canvas は バス通りを画面の縦にするため **46.4度回した座標系**。
  画面の左右は「真西・真東」ではない。それなのに詳細シートには
  「西へ約213m」のように**方角の語**を出している。ここが実際の方位と食い違うと、
  現地に立った人を反対側へ歩かせることになる。gate は画面の中の整合しか見ていない。

  だから **緯度経度に戻して**、出している語・数字が現実と合うかを全数で当てる。

見るもの:
  D1 canvas の +x が実際にどの方位か (回した座標系の素性を明示する)
  D2 詳細シートの「東へ/西へ」が、実際の経度の東西と一致しているか (全数)
  D3 「約◯m」が実距離と合っているか (全数)
  D4 南北の並び (画面の上下) が実緯度の順と合っているか
  D5 緯度経度から投影し直した位置と、地図に置いてある位置の差 (人手で動かした量)
  D6 方位記号の回転角が投影の回転と合っているか
  D7 「◯◯方面」の出口表記が、その向きの実際の方位と合っているか

外部への通信はしない。index.html の GEO を読むだけ。

usage: python audit_geography.py
"""
import io
import json
import math
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "index.html")

src = io.open(TARGET, encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
shops, meta = G["shops"], G["meta"]
P = meta["proj"]
ROT = math.radians(P["rot_deg"])
MINX, MINY = meta["minx"], meta["miny"]
SIDE_BAND = 60.0
findings = []
notes = []


def bad(code, who, msg):
    findings.append((code, who, msg))


def to_canvas(lat, lng):
    xm = (lng - P["lon0"]) * 111320.0 * P["cosf"]
    ym = -(lat - P["lat0"]) * 110540.0
    return (xm * math.cos(ROT) - ym * math.sin(ROT) - MINX,
            xm * math.sin(ROT) + ym * math.cos(ROT) - MINY)


def to_latlng(x, y):
    u, v = x + MINX, y + MINY
    xm = u * math.cos(ROT) + v * math.sin(ROT)
    ym = -u * math.sin(ROT) + v * math.cos(ROT)
    return (P["lat0"] - ym / 110540.0, P["lon0"] + xm / (111320.0 * P["cosf"]))


busways = G.get("busway") or []
main = sorted(busways, key=len, reverse=True)[0] if busways else []


def street_nearest(px, py):
    best = (None, float("inf"))
    for i in range(1, len(main)):
        a, b = main[i - 1], main[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        den = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / den)) if den else 0.0
        q = (a[0] + t * dx, a[1] + t * dy)
        d = math.hypot(px - q[0], py - q[1])
        if d < best[1]:
            best = (q, d)
    return best


def street_x_at_y(y):
    if not main:
        return meta["W"] / 2
    if y <= main[0][1]:
        return main[0][0]
    if y >= main[-1][1]:
        return main[-1][0]
    for i in range(1, len(main)):
        a, b = main[i - 1], main[i]
        if y < min(a[1], b[1]) or y > max(a[1], b[1]) or a[1] == b[1]:
            continue
        return a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
    return main[-1][0]


def tp(s):
    return (s["tx"] if isinstance(s.get("tx"), (int, float)) else s["x"],
            s["ty"] if isinstance(s.get("ty"), (int, float)) else s["y"])


def bearing(lat1, lon1, lat2, lon2):
    """真北を0度とする方位 (度)。"""
    dy = (lat2 - lat1) * 110540.0
    dx = (lon2 - lon1) * 111320.0 * P["cosf"]
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def compass_word(deg):
    names = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]
    return names[int((deg + 22.5) % 360 // 45)]


out = []
out.append("=" * 78)
out.append("位置と方角の整合性 (実座標で当て直す)   店 %d" % len(shops))
out.append("=" * 78)

# ---- D1 canvas の +x はどの方位か ----
_o = to_latlng(0, 0)
_ex = to_latlng(100, 0)
_ey = to_latlng(0, 100)
bx = bearing(_o[0], _o[1], _ex[0], _ex[1])
by = bearing(_o[0], _o[1], _ey[0], _ey[1])
out.append("")
out.append("【D1】回した座標系の素性 (回転 %.1f度)" % P["rot_deg"])
out.append("      画面の右 (+x) = 方位 %.1f度 (%s)" % (bx, compass_word(bx)))
out.append("      画面の下 (+y) = 方位 %.1f度 (%s)" % (by, compass_word(by)))
out.append("      ※ 画面の右は真東ではない。「東へ/西へ」の語は、実際の経度で当て直す必要がある")

# ---- D2 「東へ/西へ」が実際の東西と合っているか ----
out.append("")
out.append("【D2】画面に出る「東へ/西へ」が実際の経度の東西と一致しているか")
out.append("      ※ 遠方店のうち far_m>=400 の店は「約◯m先」だけで方角の語を出さない。")
out.append("         語が出ない店は違反として数えない (出ていない文言は間違いようがない)。")
d2 = 0
rows = []
shown_rows = []
for s in shops:
    x, y = tp(s)
    sx = street_x_at_y(y)
    shown = "西" if x < sx else "東"
    q, dist = street_nearest(x, y)
    if q is None:
        continue
    slat, slng = to_latlng(q[0], q[1])
    truth = "西" if s["lng"] < slng else "東"
    deg = bearing(slat, slng, s["lat"], s["lng"])
    rows.append((s["name"], shown, truth, deg, dist))
    far = abs(x - sx) > SIDE_BAND
    fm = s.get("far_m") or 0
    word_shown = far and not (fm >= 400)
    side_shown = not far           # 通り沿いは西/東の列そのものが side を表している
    if word_shown:
        shown_rows.append(s["name"])
    if (word_shown or side_shown) and shown != truth:
        bad("D2", s["name"],
            "画面では「%s」側だが、実際は通りの%s側 (通りから見て方位%.0f度=%s・%.0fm)"
            % (shown, truth, deg, compass_word(deg), dist))
        d2 += 1
    elif shown != truth:
        notes.append("%s は画面上「%s」側の扱いだが実際は%s側。ただし方角の語も列も出ない "
                     "(遠方枠で「約%dm先」だけ) ので画面には出ない" % (s["name"], shown, truth, fm))
out.append("      方角の語を出している店 %d / 列で東西を示している店 %d"
           % (len(shown_rows), len([s for s in shops
                                    if abs(tp(s)[0] - street_x_at_y(tp(s)[1])) <= SIDE_BAND])))
out.append("      食い違い %d件" % d2)
for c, w, m in [f for f in findings if f[0] == "D2"]:
    out.append("      %s: %s" % (w, m))
# 方角の語がどれくらい「真横」から外れているか
_off = [abs((r[3] - (90 if r[2] == "東" else 270) + 180) % 360 - 180) for r in rows]
if _off:
    out.append("      「東/西」と実際の方位のずれ: 平均 %.0f度 / 最大 %.0f度"
               % (sum(_off) / len(_off), max(_off)))
    _worst = sorted(zip(rows, _off), key=lambda z: -z[1])[:3]
    for r, o in _worst:
        out.append("        %-24s 画面「%sへ」/ 実際は方位%.0f度(%s) ずれ%.0f度"
                   % (r[0], r[1], r[3], compass_word(r[3]), o))

# ---- D3 距離が実距離と合っているか ----
out.append("")
out.append("【D3】画面に出る距離が実距離と合っているか")
out.append("      近い店は canvas の最短距離、縁にクランプした遠方店は far_m を出している。")
out.append("      出している方の数字を、緯度経度で測り直した実距離と比べる。")
d3 = 0
for s in shops:
    x, y = tp(s)
    q, dist = street_nearest(x, y)
    if q is None:
        continue
    slat, slng = to_latlng(q[0], q[1])
    real = math.hypot((s["lat"] - slat) * 110540.0,
                      (s["lng"] - slng) * 111320.0 * P["cosf"])
    fm = s.get("far_m") or 0
    if fm >= 400:
        # 「約650m先」のように出している値。まるめの粗さを見込んで 20% まで許す
        if real > 0 and abs(fm - real) / real > 0.20:
            bad("D3", s["name"], "画面は「約%dm先」だが実距離は %.0fm (%.0f%% ずれ)"
                % (fm, real, abs(fm - real) / real * 100))
            d3 += 1
        else:
            notes.append("%s: 画面「約%dm先」/ 実距離 %.0fm (差 %.0fm)" % (s["name"], fm, real, abs(fm - real)))
        continue
    if abs(real - dist) > 5.0:
        bad("D3", s["name"], "画面の距離 %.0fm / 実距離 %.0fm (差 %.0fm)"
            % (dist, real, abs(real - dist)))
        d3 += 1
out.append("      食い違い %d店" % d3)
for c, w, m in [f for f in findings if f[0] == "D3"]:
    out.append("      %s: %s" % (w, m))

# ---- D4 南北の並びが実緯度の順と合っているか ----
out.append("")
out.append("【D4】画面の上下 (y) の並びが、実際の南北 (緯度) の順と合っているか")
band = [s for s in shops if abs(tp(s)[0] - street_x_at_y(tp(s)[1])) <= SIDE_BAND]
by_y = sorted(band, key=lambda s: tp(s)[1])
by_lat = sorted(band, key=lambda s: -s["lat"])          # 北が上
pos_y = {s["name"]: i for i, s in enumerate(by_y)}
pos_l = {s["name"]: i for i, s in enumerate(by_lat)}
inv = []
names = [s["name"] for s in band]
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = names[i], names[j]
        if (pos_y[a] - pos_y[b]) * (pos_l[a] - pos_l[b]) < 0:
            la = [s for s in band if s["name"] == a][0]
            lb = [s for s in band if s["name"] == b][0]
            gap = abs(la["lat"] - lb["lat"]) * 110540.0
            inv.append((gap, a, b))
inv.sort(reverse=True)
out.append("      通り沿い %d店 / 上下が実際の南北と逆のペア %d組" % (len(band), len(inv)))
for gap, a, b in inv[:8]:
    out.append("        %-22s ⇔ %-22s 南北に %.1fm 離れているのに上下が逆" % (a, b, gap))
# 二列は「通り沿いの並び順」で並べると画面に書いてある。真南北の順とは食い違って当然なので、
# 逆転そのものは違反にしない。**画面が「南北の順」だと言っていたら**違反にする。
_claim = re.search(r'<p>西側・東側を([^<]{0,40}?)並べています', src)
_claim_text = _claim.group(1) if _claim else "(見つからない)"
out.append("      画面の説明: 「西側・東側を%s並べています」" % _claim_text)
if "南北" in _claim_text:
    bad("D4", "-", "画面は「南北位置に合わせて」と言っているが、実際は通り沿いの順で "
                   "%d組が真南北と逆 (最大 %.1fm)。並べ方か言い方のどちらかを直す"
        % (len(inv), inv[0][0] if inv else 0))
else:
    notes.append("二列の並びは通り沿いの順。真南北とは %d組が逆 (最大 %.1fm) だが、"
                 "画面もそう言っているので食い違いではない" % (len(inv), inv[0][0] if inv else 0))

# ---- D5 投影し直した位置と、置いてある位置の差 ----
out.append("")
out.append("【D5】緯度経度から投影し直した位置と、地図に置いてある位置の差")
moves, clamped = [], []
for s in shops:
    cx, cy = to_canvas(s["lat"], s["lng"])
    tx, ty = tp(s)
    d = math.hypot(cx - tx, cy - ty)
    # クランプした遠方店は、画面の外に出ないよう**意図して**縁へ寄せてある。
    # 実距離は far_m で別に出しているので、ここで差が出るのは想定どおり。
    (clamped if s.get("clamped") else moves).append((d, s["name"]))
moves.sort(reverse=True)
clamped.sort(reverse=True)
out.append("      真位置(tx,ty)との差 (クランプした遠方店を除く %d店): 最大 %.1fm / 平均 %.1fm"
           % (len(moves), moves[0][0], sum(m[0] for m in moves) / len(moves)))
for d, n in moves[:3]:
    out.append("        %-24s %.1fm" % (n, d))
if clamped:
    out.append("      縁へ寄せた遠方店 %d店 (意図した移動・実距離は far_m で出す): %s"
               % (len(clamped), "、".join("%s %.0fm" % (n, d) for d, n in clamped)))
if moves[0][0] > 5.0:
    bad("D5", moves[0][1], "真位置が投影と %.1fm ずれている (tx,ty は投影そのものであるべき)" % moves[0][0])
shown = []
for s in shops:
    shown.append((math.hypot(s["x"] - tp(s)[0], s["y"] - tp(s)[1]), s["name"]))
shown.sort(reverse=True)
out.append("      表示位置(x,y)を真位置からずらした量: 最大 %.1fm / 平均 %.1fm"
           % (shown[0][0], sum(s[0] for s in shown) / len(shown)))
for d, n in shown[:3]:
    out.append("        %-24s %.1fm" % (n, d))
_declared = (meta.get("shop_positioning") or {}).get("max_move_m")
if _declared is not None and abs(_declared - shown[0][0]) > 0.6:
    bad("D5", "-", "meta の申告 %.1fm と実測の最大 %.1fm が合わない" % (_declared, shown[0][0]))

# ---- D6 方位記号 ----
out.append("")
out.append("【D6】方位記号の回転角")
m = re.search(r"rotate\(\s*([-\d.]+)\s+22\s+22\s*\)", src)
_needle = re.search(r"compassNeedle[^>]*", src)
out.append("      投影の回転 %.1f度 → 針は真上から %.1f度 回っているはず" % (P["rot_deg"], -P["rot_deg"] % 360))
out.append("      ※ 画面上の実測は gate N61 が見ている (ここでは投影値だけ出す)")

# ---- D7 方面表記 ----
out.append("")
out.append("【D7】「◯◯方面」の出口表記と、その位置の実際の方位")
for e in G.get("exits") or []:
    lat, lng = to_latlng(e["x"], e["y"])
    deg = bearing(P["lat0"], P["lon0"], lat, lng)
    out.append("      %-16s 画面(%.0f,%.0f) → 中心から方位 %.0f度 (%s)"
               % (e.get("text", "?"), e["x"], e["y"], deg, compass_word(deg)))

out.append("")
out.append("=" * 78)
out.append("食い違い 合計 %d件" % len(findings))
out.append("=" * 78)
print("\n".join(out))
sys.exit(1 if findings else 0)
