#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズI — 指での操作感を測る (ボス指摘「見にくい・操作しにくい」)

採点表は規約への適合を測っているだけで、体感の見やすさ・操作性は測れていない。
ここでは「スマホで歩きながら店を探す」時に実際にやる動作を、指の操作として試す。

  I1 ピンチで地図が拡大するか (指2本)
  I2 ダブルタップで拡大するか
  I3 ホイール／トラックパッドで拡大するか
  I4 1本指でドラッグして地図が動くか
  I5 拡大の段数と、歩ける倍率まで何回押すか
  I6 最初の画面に何店見えるか / 見える文字の大きさ
  I7 地図が動かせる・拡大できることが分かる手がかりがあるか
"""
import io, os, socket, subprocess, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

STATE = r"""() => {
  const m = document.getElementById('map').getScreenCTM();
  const vp = document.getElementById('viewport');
  const r = vp.getBoundingClientRect();
  const shown = e => { const cs = getComputedStyle(e);
    return cs.display !== 'none' && cs.visibility !== 'hidden'; };
  let inView = 0, labels = 0;
  const sizes = {};
  for (const h of document.querySelectorAll('g.hit')) {
    const st = h.querySelector('.star'), t = h.querySelector('text[data-main-label="1"]');
    const b = st.getBoundingClientRect();
    const cx = b.left+b.width/2, cy = b.top+b.height/2;
    if (cx>=r.left && cx<=r.right && cy>=r.top && cy<=r.bottom) inView++;
    if (t && shown(t) && t.getBoundingClientRect().width > 1) {
      labels++;
      const px = Math.round(parseFloat(getComputedStyle(t).fontSize)
                            * Math.hypot(m.a, m.b));
      sizes[px] = (sizes[px]||0)+1;
    }
  }
  const st0 = document.querySelector('.star');
  return {scale:+Math.hypot(m.a,m.b).toFixed(4),
          zoom: +(visualViewport ? visualViewport.scale : 1).toFixed(3),
          scrollTop: Math.round(vp.scrollTop), scrollLeft: Math.round(vp.scrollLeft),
          inView, labels, labelPx: sizes,
          starPx: st0 ? +st0.getBoundingClientRect().width.toFixed(1) : null,
          touchAction: getComputedStyle(vp).touchAction};
}"""


def serve():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(p), "--bind", "127.0.0.1"],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    u = "http://127.0.0.1:%d/index.html" % p
    for _ in range(30):
        try:
            urllib.request.urlopen(u, timeout=1).read(1); return srv, u
        except Exception:
            time.sleep(1)
    srv.terminate(); raise SystemExit("!! サーバ起動失敗")


def pinch(pg, cx, cy, spread):
    """指2本を広げる。CDP の Input.dispatchTouchEvent を直接使う。"""
    cdp = pg.context.new_cdp_session(pg)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        d = 40 + spread * frac
        pts = [{"x": cx - d, "y": cy, "id": 1}, {"x": cx + d, "y": cy, "id": 2}]
        cdp.send("Input.dispatchTouchEvent",
                 {"type": "touchStart" if frac == 0.0 else "touchMove",
                  "touchPoints": pts})
        pg.wait_for_timeout(60)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    pg.wait_for_timeout(500)


def main():
    srv, base = serve()
    found = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            ctx = br.new_context(viewport={"width": 390, "height": 844},
                                 has_touch=True, is_mobile=True,
                                 device_scale_factor=3)
            pg = ctx.new_page()
            pg.goto(base, wait_until="load"); pg.wait_for_timeout(1600)
            a = pg.evaluate(STATE)
            print("=" * 84)
            print("開いた直後 (390x844・指あり)")
            print("=" * 84)
            print("   地図の倍率 %.4f px/m / 表示域に★ %d件 / ラベル %d件"
                  % (a["scale"], a["inView"], a["labels"]))
            print("   ★の大きさ %.1fpx / ラベルの画面上の大きさ %s"
                  % (a["starPx"], " ".join("%spx×%d" % (k, v)
                                           for k, v in sorted(a["labelPx"].items(),
                                                              key=lambda x: -int(x[0])))))
            print("   #viewport の touch-action: %s" % a["touchAction"])

            vp = pg.evaluate("""()=>{const r=document.getElementById('viewport')
              .getBoundingClientRect();
              return {cx:Math.round(r.left+r.width/2), cy:Math.round(r.top+r.height/2)};}""")

            # I1 ピンチ
            pinch(pg, vp["cx"], vp["cy"], 160)
            b = pg.evaluate(STATE)
            ok1 = abs(b["scale"] - a["scale"]) > 0.01
            print()
            print("I1 ピンチで広げた後: 地図の倍率 %.4f (%s) / ページ全体の拡大 %.3f倍"
                  % (b["scale"], "地図が拡大した" if ok1 else "地図は変わらない", b["zoom"]))
            if not ok1:
                found.append("ピンチで地図が拡大しない (指2本を広げても倍率 %.4f のまま)" % b["scale"])

            # I2 ダブルタップ
            pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
            c0 = pg.evaluate(STATE)
            pg.touchscreen.tap(vp["cx"], vp["cy"])
            pg.wait_for_timeout(80)
            pg.touchscreen.tap(vp["cx"], vp["cy"])
            pg.wait_for_timeout(600)
            c = pg.evaluate(STATE)
            ok2 = abs(c["scale"] - c0["scale"]) > 0.01
            print("I2 ダブルタップ後: 地図の倍率 %.4f (%s)"
                  % (c["scale"], "拡大した" if ok2 else "変わらない"))
            if not ok2:
                found.append("ダブルタップで地図が拡大しない")
            pg.keyboard.press("Escape")

            # I3 ホイール
            pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
            d0 = pg.evaluate(STATE)
            pg.mouse.move(vp["cx"], vp["cy"])
            pg.mouse.wheel(0, -400)
            pg.wait_for_timeout(500)
            d = pg.evaluate(STATE)
            ok3 = abs(d["scale"] - d0["scale"]) > 0.01
            print("I3 ホイールを上へ: 地図の倍率 %.4f (%s) / 縦スクロール %d→%d"
                  % (d["scale"], "拡大した" if ok3 else "変わらない (画面が動いただけ)",
                     d0["scrollTop"], d["scrollTop"]))
            if not ok3:
                found.append("ホイール／トラックパッドで地図が拡大しない (PCで見る人が困る)")

            # I4 1本指ドラッグ
            pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
            e0 = pg.evaluate(STATE)
            cdp = pg.context.new_cdp_session(pg)
            cdp.send("Input.dispatchTouchEvent",
                     {"type": "touchStart",
                      "touchPoints": [{"x": vp["cx"], "y": vp["cy"], "id": 1}]})
            for k in range(1, 6):
                cdp.send("Input.dispatchTouchEvent",
                         {"type": "touchMove",
                          "touchPoints": [{"x": vp["cx"], "y": vp["cy"] - k*30, "id": 1}]})
                pg.wait_for_timeout(50)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(500)
            e = pg.evaluate(STATE)
            ok4 = e["scrollTop"] != e0["scrollTop"]
            # 対照実験: 同じやり方で お店一覧 (確実にスクロールする箱) が動くか。
            # 動かないなら私の擬似操作が効いていないだけで、地図の問題ではない。
            pg.evaluate("()=>document.getElementById('listbtn').click()")
            pg.wait_for_timeout(500)
            lp = pg.evaluate("""()=>{const r=document.getElementById('listrows')
              .getBoundingClientRect();
              return {cx:Math.round(r.left+r.width/2), cy:Math.round(r.top+40),
                      top:document.getElementById('listrows').scrollTop,
                      sc:document.getElementById('listpanel').scrollTop};}""")
            cdp.send("Input.dispatchTouchEvent",
                     {"type": "touchStart",
                      "touchPoints": [{"x": lp["cx"], "y": lp["cy"], "id": 1}]})
            for k in range(1, 6):
                cdp.send("Input.dispatchTouchEvent",
                         {"type": "touchMove",
                          "touchPoints": [{"x": lp["cx"], "y": lp["cy"] - k*30, "id": 1}]})
                pg.wait_for_timeout(50)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(500)
            lp2 = pg.evaluate("""()=>({top:document.getElementById('listrows').scrollTop,
              sc:document.getElementById('listpanel').scrollTop})""")
            ctrl = (lp2["top"] != lp["top"]) or (lp2["sc"] != lp["sc"])
            print("I4 1本指で上へドラッグ: 地図の縦スクロール %d→%d (%s)"
                  % (e0["scrollTop"], e["scrollTop"], "地図が動いた" if ok4 else "動かない"))
            print("   対照 (お店一覧を同じやり方でドラッグ): %s"
                  % ("動いた → 擬似操作は効いている" if ctrl
                     else "動かない → 擬似操作が効いていないので この検査は不成立"))
            if not ok4 and ctrl:
                found.append("1本指のドラッグで地図が動かない")
            pg.keyboard.press("Escape")

            # I5 ボタンで歩ける倍率まで何回
            pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
            n, sc = 0, pg.evaluate(STATE)["scale"]
            steps = [sc]
            while sc < 2.0 and n < 12:
                pg.evaluate("()=>document.querySelectorAll('.zoomctl button')[0].click()")
                pg.wait_for_timeout(320)
                sc = pg.evaluate(STATE)["scale"]; steps.append(round(sc, 3)); n += 1
            print("I5 ＋ボタンで歩ける倍率(2.0)まで %d回: %s"
                  % (n, " → ".join("%.2f" % x for x in steps)))
            if n > 3:
                found.append("歩ける倍率まで＋ボタンを%d回押す必要がある" % n)

            # I7 手がかり
            pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
            hint = pg.evaluate("""() => {
              const txt = document.body.innerText || '';
              return {hasHint: /動かせ|スクロール|拡大|ピンチ|ズーム|指で|さがす/.test(txt),
                      zoomBtns: document.querySelectorAll('.zoomctl button').length,
                      zoomLabels: [...document.querySelectorAll('.zoomctl button')]
                        .map(b => (b.getAttribute('aria-label')||b.textContent||'').trim())};}""")
            print("I7 拡大・移動の手がかり: ズームボタン%d個 %s"
                  % (hint["zoomBtns"], hint["zoomLabels"]))
            ctx.close(); br.close()
    finally:
        srv.terminate()
    print()
    print("=" * 84)
    if found:
        print("操作感の指摘: %d件" % len(found))
        for x in found:
            print("   " + x)
    else:
        print("操作感の指摘: 0件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
