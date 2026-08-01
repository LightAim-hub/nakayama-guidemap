# -*- coding: utf-8 -*-
"""lens_locate.py — 現在地ボタンを実際に押して、押した人が次に何を見るかを測る。

なぜ要るか (2026-08-01):
  gate.py が N1〜N52 すべて0件で PASS した状態で、現在地ボタンを実際に押したら
  見える店が 29件 → 1件 になっていた (店の無い場所へ縮尺そのままで寄っていた)。
  利用者からは「押したら地図が空になった」に見える。
  採点表は「機能が動くか」を見るが、「押した人が次に何を見るか」は見ていなかった。
  ボスの言葉:「利用者の声っていうのを考えて作らないとダメだよ」

  gate.py に入れないのは、位置情報の差し替えに browser context が要り、
  gate の作り (page 単位) と合わないため。押す操作は独立した目で見る。

使い方:
  python tools/v2-build/lens_locate.py
  → 押す前後の 見える店の数 / 縮尺 / ★の大きさ / 画面に出る言葉 を出す。

合否の目安:
  ・範囲内で押したら、押した後に店が5件以上見えること (空の地図にしない)
  ・いちばん近い店の名前と距離・方角が伝わること
  ・範囲外で押したら、地図を動かさず距離を伝えること
  ・どの場合も ★は14px以上を保つこと (N12)
  ・位置は外部に送らない・保存しない
"""
import os, sys, json
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
URL = "file:///" + ROOT.replace("\\", "/") + "/index.html"

# 中山の商店街まわりと、明らかに外
POINTS = [
    ("商店街の中",        38.2935, 140.8435, "inside"),
    ("端のほう(店が無い)", 38.2960, 140.8440, "inside"),
    ("北へ1.4km",        38.3050, 140.8470, "outside"),
    ("仙台駅(5km)",      38.2600, 140.8820, "outside"),
]
MIN_SHOPS_AFTER = 5
MIN_STAR_PX = 14.0

MEASURE = """() => {
  const vp=document.getElementById('viewport').getBoundingClientRect();
  const svg=document.getElementById('map');
  const vb=svg.getAttribute('viewBox').split(' ').map(Number);
  const sb=svg.getBoundingClientRect();
  let vis=0;
  document.querySelectorAll('#map g.hit').forEach(h=>{
    const r=h.getBoundingClientRect();
    if(r.right>vp.left&&r.left<vp.right&&r.bottom>vp.top&&r.top<vp.bottom) vis++;});
  const st=[...document.querySelectorAll('#map use.star, #map .star')]
    .map(e=>{const r=e.getBoundingClientRect(); return Math.max(r.width,r.height);});
  return {pxPerM:+(sb.width/vb[2]).toFixed(3), shops:vis,
          starMin: st.length ? +Math.min(...st).toFixed(1) : 0,
          msg:((document.getElementById('locationStatus')||{}).textContent||'').trim(),
          viewBox: svg.getAttribute('viewBox')};
}"""

# 位置を外へ出していないか (押した後に確かめる)
LEAK = """() => ({
  ls: Object.keys(localStorage).length,
  ss: Object.keys(sessionStorage).length,
})"""


def main():
    bad = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for nm, lat, lon, kind in POINTS:
            ctx = br.new_context(viewport={"width": 360, "height": 640},
                                 geolocation={"latitude": lat, "longitude": lon},
                                 permissions=["geolocation"])
            pg = ctx.new_page()
            sent = []
            pg.on("request", lambda r: sent.append(r.url)
                  if not r.url.startswith(("file:", "data:")) else None)
            pg.goto(URL); pg.wait_for_timeout(1600)
            pg.evaluate("()=>document.getElementById('mapbtn').click()")
            pg.wait_for_timeout(1000)
            before = pg.evaluate(MEASURE)
            pg.evaluate("()=>document.getElementById('locatebtn').click()")
            pg.wait_for_timeout(2500)
            after = pg.evaluate(MEASURE)
            leak = pg.evaluate(LEAK)
            ctx.close()

            print("== %s ==" % nm)
            print("   押す前 店%2d (%.2fpx/m) → 押した後 店%2d (%.2fpx/m) ★%.1fpx"
                  % (before["shops"], before["pxPerM"], after["shops"],
                     after["pxPerM"], after["starMin"]))
            print("   画面の言葉: 「%s」" % after["msg"])

            if kind == "inside":
                if after["shops"] < MIN_SHOPS_AFTER:
                    bad.append("%s: 押した後に店が%d件しか見えない (最低%d・空の地図にしない)"
                               % (nm, after["shops"], MIN_SHOPS_AFTER))
                if "いちばん近い" not in after["msg"]:
                    bad.append("%s: いちばん近い店が伝わらない 「%s」" % (nm, after["msg"]))
            else:
                if after["viewBox"] != before["viewBox"]:
                    bad.append("%s: 範囲外なのに地図を動かしている" % nm)
                if "離れています" not in after["msg"]:
                    bad.append("%s: 範囲外だと伝わらない 「%s」" % (nm, after["msg"]))
            if after["starMin"] < MIN_STAR_PX:
                bad.append("%s: ★が%.1fpx (最低%.0f)" % (nm, after["starMin"], MIN_STAR_PX))
            if leak["ls"] or leak["ss"]:
                bad.append("%s: 位置を保存している (localStorage %d / sessionStorage %d)"
                           % (nm, leak["ls"], leak["ss"]))
            ext = [u for u in sent if "lightaim" not in u and "fonts.g" not in u]
            if ext:
                bad.append("%s: 外部へ送っている %s" % (nm, ext[:2]))
        br.close()

    print()
    if bad:
        print("不合格 %d件:" % len(bad))
        for b in bad:
            print("   " + b)
        sys.exit(1)
    print("合格 — 押した人が次に見るものが成立している")


main()
