#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズE — ゲートが一度も見ていない画面状態を測る

ゲート (N20-N27) が測るのは「開いた直後」と「お店一覧を開いた状態」だけ。
実際に客が触るのはその先で、そこは無検査だった:

  U1 詳細シート     店を押した先。文字の大きさ・押しやすさ・はみ出し
  U2 チューザー     密集地で複数候補が出た状態
  U3 検索結果       文字を打った状態
  U4 横向き         端末を寝かせた状態 (縦しか測っていない)
  U5 横スクロール   本文が画面幅を超えていないか
  U6 文字の切れ     チップ・一覧行・詳細で文字が省略記号で消えていないか

合否は出さず実測値を出す。閾値で締めるべきものはゲート側へ昇格させる。
"""
import io, os, socket, subprocess, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SHOT = os.path.join(ROOT, "tools", "v2-build", "_shots")

TAP_MIN = 44.0
TEXT_MIN = 14.0
ATTRIB_MIN = 12.0

DEVICES = [("小型Android", 360, 640), ("iPhone SE", 375, 667),
           ("iPhone 14", 390, 844), ("iPhone 14 Plus", 428, 926),
           ("横向き (小)", 640, 360), ("横向き (14)", 844, 390)]

# 帰属表示・注記は12px床。それ以外は14px床。
ATTRIB_HINT = "OpenStreetMap ODbL 出典 地図データ ライセンス 国土地理院".split()

MEASURE = r"""(state) => {
  const shown = e => { const cs = getComputedStyle(e);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > .05
        && e.getAttribute('aria-hidden') !== 'true'; };
  // 「画面に映っているか」まで見る。閉じたパネルは display:none ではなく画面外へ
  // ずらしてあるだけなので、祖先の表示状態だけを見ると中身を全部拾ってしまう
  // (2026-07-31: 詳細シートの60店分のスライドを数えて289件の誤検出を出した)。
  // 面積の半分以上が画面の中にあるものだけを「映っている」とする。
  const vis = e => { if (!e) return false;
    for (let n = e; n && n !== document.documentElement; n = n.parentElement)
      if (!shown(n)) return false;
    const r = e.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return false;
    const iw = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
    const ih = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
    if (iw <= 0 || ih <= 0) return false;
    return (iw * ih) >= .5 * (r.width * r.height); };
  const label = e => (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 24) || '(無題)';

  // 押せるもの。地図の中の★(g.hit)は除く — 密集地で指が複数店を覆うのは
  // 物理的に避けられず、ゲート N24 が「拡大すれば単一ボタンで押せる」で別に見ている。
  const taps = [...document.querySelectorAll('button,a[href],input,select,[role="button"],[tabindex]')]
    .filter(e => vis(e) && !e.closest('svg')).map(e => { const r = e.getBoundingClientRect();
      return {nm:label(e), w:+r.width.toFixed(1), h:+r.height.toFixed(1)}; });

  // 文字。帰属表示・注記の枠 (footer/.credits/.foot) だけ12px床、それ以外は14px床。
  // ゲート N21 と同じ構造の規則にする (語句の一覧で判定しない)。
  const texts = [];
  for (const e of document.querySelectorAll('body *')) {
    if (!vis(e)) continue;
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    if (e.closest('svg')) continue;           // 地図の中はゲートN21が別に測る
    texts.push({nm:label(e), fs:+parseFloat(getComputedStyle(e).fontSize).toFixed(1),
                attrib: !!e.closest('footer, .credits, .foot')});
  }

  // 文字の切れ (省略記号や横あふれ)。clientWidth が極小の要素は
  // 読み上げ用の隠し要素なので除く (幅1pxを「切れている」と誤検出した)。
  const clipped = [];
  for (const e of document.querySelectorAll('body *')) {
    if (!vis(e) || e.closest('svg')) continue;
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own || e.clientWidth < 10) continue;
    if (e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'auto'
        && getComputedStyle(e).overflowX !== 'scroll')
      clipped.push({nm:label(e), need:e.scrollWidth, has:e.clientWidth});
  }

  return {state,
    taps: taps.filter(t => t.w < 44 || t.h < 44),
    tapCount: taps.length,
    smallText: texts.filter(t => t.fs < (t.attrib ? 12 : 14)),
    textCount: texts.length,
    clipped,
    pageScrollX: document.documentElement.scrollWidth > innerWidth + 1
                 ? {need:document.documentElement.scrollWidth, has:innerWidth} : null,
    bodyH: document.body.getBoundingClientRect().height};
}"""

OPEN_DETAIL = r"""async () => {
  const hits = [...document.querySelectorAll('g.hit')];
  // チューザーが出ない店 (単一ボタン) を選ぶ
  let target = hits.find(h => { try { return nearby(GEO.shops[+h.dataset.i]).length <= 1; }
                               catch(e){ return false; } }) || hits[0];
  target.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  await new Promise(r => setTimeout(r, 450));
  const dp = document.getElementById('detailPanel');
  return {opened: !!(dp && dp.getAttribute('aria-hidden') === 'false'),
          name: GEO.shops[+target.dataset.i].name};
}"""

OPEN_CHOOSER = r"""async () => {
  const hits = [...document.querySelectorAll('g.hit')];
  let target = hits.find(h => { try { return nearby(GEO.shops[+h.dataset.i]).length > 1; }
                               catch(e){ return false; } });
  if (!target) return {opened:false, name:null, n:0};
  const n = nearby(GEO.shops[+target.dataset.i]).length;
  target.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  await new Promise(r => setTimeout(r, 450));
  const ch = document.getElementById('chooser');
  return {opened: !!(ch && ch.classList.contains('show')),
          name: GEO.shops[+target.dataset.i].name, n};
}"""

ESC = r"""async () => { document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  await new Promise(r => setTimeout(r, 300)); return true; }"""

SEARCH = r"""async () => { const q = document.getElementById('q');
  q.value = 'なか'; q.dispatchEvent(new Event('input', {bubbles:true}));
  await new Promise(r => setTimeout(r, 400)); return true; }"""


def main():
    os.makedirs(SHOT, exist_ok=True)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d/index.html" % port
    for _ in range(30):
        try:
            urllib.request.urlopen(base, timeout=1).read(1); break
        except Exception:
            time.sleep(1)
    else:
        srv.terminate(); print("!! サーバ起動失敗"); return 2
    findings = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for nm, w, h in DEVICES:
                pg = br.new_page(viewport={"width": w, "height": h})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(base, wait_until="load")
                pg.wait_for_timeout(1500)
                print("=" * 84)
                print("%s %dx%d" % (nm, w, h))
                rows = []
                rows.append(pg.evaluate(MEASURE, "開いた直後"))
                pg.screenshot(path=os.path.join(SHOT, "%dx%d_1_open.png" % (w, h)))

                d = pg.evaluate(OPEN_DETAIL)
                if d["opened"]:
                    rows.append(pg.evaluate(MEASURE, "詳細シート (%s)" % d["name"]))
                    pg.screenshot(path=os.path.join(SHOT, "%dx%d_2_detail.png" % (w, h)))
                else:
                    findings.append((nm, "詳細シートが開かない (%s)" % d["name"]))
                pg.evaluate(ESC)

                c = pg.evaluate(OPEN_CHOOSER)
                if c["opened"]:
                    rows.append(pg.evaluate(MEASURE, "チューザー (%s 他%d件)" % (c["name"], c["n"])))
                    pg.screenshot(path=os.path.join(SHOT, "%dx%d_3_chooser.png" % (w, h)))
                    pg.evaluate(ESC)
                elif c["name"]:
                    findings.append((nm, "チューザーが開かない (%s)" % c["name"]))

                pg.evaluate("()=>document.getElementById('listbtn').click()")
                pg.wait_for_timeout(400)
                rows.append(pg.evaluate(MEASURE, "お店一覧"))
                pg.screenshot(path=os.path.join(SHOT, "%dx%d_4_list.png" % (w, h)))
                pg.evaluate(ESC)

                pg.evaluate(SEARCH)
                rows.append(pg.evaluate(MEASURE, "検索中"))
                pg.screenshot(path=os.path.join(SHOT, "%dx%d_5_search.png" % (w, h)))

                for r in rows:
                    bits = []
                    if r["taps"]:
                        bits.append("押しにくい%d件 (%s)" % (len(r["taps"]),
                            " / ".join("%s %.0fx%.0f" % (t["nm"], t["w"], t["h"]) for t in r["taps"][:3])))
                    small = r["smallText"]
                    if small:
                        bits.append("小さい文字%d件 (%s)" % (len(small),
                            " / ".join("%s %.1fpx%s" % (t["nm"], t["fs"], "[帰属]" if t["attrib"] else "")
                                       for t in small[:3])))
                    if r["clipped"]:
                        bits.append("文字が切れ%d件 (%s)" % (len(r["clipped"]),
                            " / ".join("%s %d>%d" % (c["nm"], c["need"], c["has"]) for c in r["clipped"][:3])))
                    if r["pageScrollX"]:
                        bits.append("横スクロールが出る (%d > %d)"
                                    % (r["pageScrollX"]["need"], r["pageScrollX"]["has"]))
                    print("   %-28s 押せるもの%3d / 文字%3d   %s"
                          % (r["state"], r["tapCount"], r["textCount"],
                             " | ".join(bits) if bits else "問題なし"))
                    for b in bits:
                        findings.append((nm + " " + r["state"], b))
                if errs:
                    print("   JSエラー %d件: %s" % (len(errs), errs[0][:70]))
                    findings.append((nm, "JSエラー %d件" % len(errs)))
                pg.close()
            br.close()
    finally:
        srv.terminate()
    print("=" * 84)
    if findings:
        print("見つかった件数: %d" % len(findings))
        for a, b in findings:
            print("   %-30s %s" % (a, b))
    else:
        print("見つかった件数: 0")
    print("画面の絵: %s" % SHOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
