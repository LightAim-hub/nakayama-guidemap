#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズF — 条件が変わっても壊れないか / 中身が食い違っていないか

ここまでの検査は「良い条件で開いた時」だけを見ている。実際に商店街で使う時は
電波が悪く、端末の文字設定も人それぞれで、操作は順番に積み重なる。

  F1 Web フォントが届かない時    (電波が悪い / 遮断環境)
  F2 端末の文字設定が大きい時    (125% / 150%)
  F3 画面の表示と中身が一致するか (カテゴリの件数・一覧の行数・検索)
  F4 絞り込みと検索を重ねた時     (状態が戻るか)

合否は出さず実測値を出す。締めるべきものは採点表へ昇格させる。
"""
import io, os, socket, subprocess, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


OPEN_MAP = """async () => {
  const b = document.getElementById('mapbtn');
  if (b && b.getAttribute('aria-expanded') !== 'true') {
    b.click(); await new Promise(r => setTimeout(r, 700));
  }
  return !!document.getElementById('viewport');
}"""

MEASURE = r"""() => {
  const shown = e => { const cs = getComputedStyle(e);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > .05; };
  const vp = document.getElementById('viewport').getBoundingClientRect();
  let stars = 0, labels = 0, voiceShown = 0, voiceIn = 0, badges = 0, voiceTotal = 0;
  const rects = [], missing = [];
  for (const h of document.querySelectorAll('g.hit')) {
    const sp = GEO.shops[+h.dataset.i];
    const st = h.querySelector('.star');
    const t = h.querySelector('text[data-main-label="1"]');
    const vg = h.querySelector('g.voice-badge');
    if (st && shown(st)) stars++;
    const tv = !!(t && shown(t) && t.getBoundingClientRect().width > 1);
    if (tv) { labels++; rects.push({n:sp.name, r:t.getBoundingClientRect()}); }
    if (!(sp.voices||[]).length) continue;
    voiceTotal++;
    if (vg && shown(vg)) badges++;
    const b = st.getBoundingClientRect();
    const cx = b.left+b.width/2, cy = b.top+b.height/2;
    if (!(cx>=vp.left && cx<=vp.right && cy>=vp.top && cy<=vp.bottom)) continue;
    voiceIn++;
    if (tv) voiceShown++; else missing.push(sp.name);
  }
  let cross = 0;
  for (let i=0;i<rects.length;i++) for (let j=i+1;j<rects.length;j++){
    const a=rects[i].r, b=rects[j].r;
    if (Math.min(a.right,b.right)-Math.max(a.left,b.left) > .5 &&
        Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top) > .5) cross++;
  }
  // getComputedStyle().fontFamily は「宣言した名前」を返すだけで、
  // 実際に読み込めたかは分からない (最初の実装はこれで遮断の成否を測れていなかった)。
  // document.fonts.check で実物が使えるかを見る。
  const fontUsed = (document.fonts && document.fonts.check)
    ? (document.fonts.check('16px "Yusei Magic"') ? 'Yusei Magic' : '代替 (未読込)')
    : '不明';
  return {stars, labels, voiceShown, voiceIn, badges, voiceTotal, cross, missing, fontUsed,
          total: GEO.shops.length,
          mapH: Math.round(vp.height), ratio:+(vp.height/innerHeight).toFixed(3),
          scale:+Math.hypot(...(()=>{const m=document.getElementById('map').getScreenCTM();
                                    return [m.a,m.b];})()).toFixed(4)};
}"""

UIFIT = r"""() => {
  const shown = e => { const cs = getComputedStyle(e);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > .05; };
  const vis = e => { for (let n=e;n&&n!==document.documentElement;n=n.parentElement)
      if (!shown(n)) return false;
    const r = e.getBoundingClientRect();
    if (!(r.width>0&&r.height>0)) return false;
    const iw=Math.min(r.right,innerWidth)-Math.max(r.left,0);
    const ih=Math.min(r.bottom,innerHeight)-Math.max(r.top,0);
    return iw>0&&ih>0&&(iw*ih)>=.5*(r.width*r.height); };
  const small = [], off = [];
  for (const e of document.querySelectorAll('button,a[href],input,[role="button"]')) {
    if (e.closest('svg') || !vis(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 44 || r.height < 44)
      small.push({nm:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,16),
                  w:Math.round(r.width), h:Math.round(r.height)});
    if (r.right > innerWidth+.5 || r.left < -.5)
      off.push((e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,16));
  }
  return {small, off,
          pageScrollX: document.documentElement.scrollWidth > innerWidth+1
            ? document.documentElement.scrollWidth : 0,
          chipRows: new Set([...document.querySelectorAll('.chip')]
            .filter(vis).map(c=>Math.round(c.getBoundingClientRect().top))).size,
          chipsVisible: [...document.querySelectorAll('.chip')].filter(vis).length};
}"""

CONTENT = r"""async () => {
  const out = {};
  out.shops = GEO.shops.length;
  out.voiceReal = GEO.shops.filter(s => (s.voices||[]).length).length;
  const chip = [...document.querySelectorAll('.chip')]
    .find(c => /こどもの声/.test(c.textContent||''));
  out.voiceChipTxt = chip ? chip.textContent.trim() : '(なし)';
  const m = out.voiceChipTxt.match(/(\d+)/);
  out.voiceChipNum = m ? +m[1] : null;
  // 一覧の行数
  document.getElementById('listbtn').click();
  await new Promise(r=>setTimeout(r,450));
  out.listRows = document.querySelectorAll('#listrows > *').length;
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  await new Promise(r=>setTimeout(r,300));
  // 全店を名前で検索して当たるか
  const q = document.getElementById('q');
  const miss = [];
  for (const s of GEO.shops) {
    q.value = s.name;
    q.dispatchEvent(new Event('input', {bubbles:true}));
    await new Promise(r=>setTimeout(r,25));
    const hit = [...document.querySelectorAll('g.hit')]
      .some(h => GEO.shops[+h.dataset.i].name === s.name && !h.classList.contains('dim'));
    if (!hit) miss.push(s.name);
  }
  q.value = ''; q.dispatchEvent(new Event('input',{bubbles:true}));
  await new Promise(r=>setTimeout(r,300));
  out.searchMiss = miss;
  return out;
}"""

FLOW = r"""async () => {
  const out = {};
  const undim = () => [...document.querySelectorAll('g.hit')]
    .filter(h => !h.classList.contains('dim')).length;
  out.start = undim();
  const chip = [...document.querySelectorAll('.chip')]
    .find(c => /こどもの声/.test(c.textContent||''));
  chip.click(); await new Promise(r=>setTimeout(r,400));
  out.afterFilter = undim();
  const q = document.getElementById('q');
  q.value = 'ケーキ'; q.dispatchEvent(new Event('input',{bubbles:true}));
  await new Promise(r=>setTimeout(r,400));
  out.afterFilterAndSearch = undim();
  q.value = ''; q.dispatchEvent(new Event('input',{bubbles:true}));
  await new Promise(r=>setTimeout(r,400));
  out.afterClearSearch = undim();
  chip.click(); await new Promise(r=>setTimeout(r,400));
  out.afterClearFilter = undim();
  out.restored = out.afterClearFilter === out.start;
  return out;
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


def main():
    srv, base = serve()
    found = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()

            print("=" * 88)
            print("F1 Web フォントが届かない時 (電波が悪い / 遮断環境)")
            print("=" * 88)
            print("  %-12s %-16s %6s %6s %8s %8s %6s" %
                  ("端末", "使われた書体", "★", "ラベル", "声ラベル", "声バッジ", "重なり"))
            # この端末には Yusei Magic がローカル導入されているため、ネットワークを
            # 止めても代替書体の経路には入らない (document.fonts.check が true のまま)。
            # 「文字の形が変わってもラベル配置が成り立つか」を見たいので、
            # 書体を明確に別物へ差し替えて測る。
            SWAP = ("text[data-main-label='1'], text.distance-label, .shoplabel"
                    "{font-family: 'Times New Roman', serif !important;}")
            for w, h in [(360, 640), (390, 844)]:
                for block in (False, True):
                    pg = br.new_page(viewport={"width": w, "height": h})
                    errs, blocked = [], []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    if block:
                        # 実際に何件止めたかを数える。止まっていない検査を
                        # 「壊れなかった」と読むのが一番危ない。
                        def _abort(route):
                            blocked.append(route.request.url)
                            route.abort()
                        pg.route("**/fonts.googleapis.com/**", _abort)
                        pg.route("**/fonts.gstatic.com/**", _abort)
                    pg.goto(base, wait_until="load"); pg.wait_for_timeout(600)
                    try: pg.evaluate(OPEN_MAP)
                    except Exception: pass
                    pg.wait_for_timeout(1800)
                    m = pg.evaluate(MEASURE)
                    # 同じ条件でもう一度開いて、配置が毎回同じかを見る
                    pg2 = br.new_page(viewport={"width": w, "height": h})
                    if block:
                        pg2.route("**/fonts.googleapis.com/**", lambda r: r.abort())
                        pg2.route("**/fonts.gstatic.com/**", lambda r: r.abort())
                    pg2.goto(base, wait_until="load"); pg2.wait_for_timeout(600)
                    try: pg2.evaluate(OPEN_MAP)
                    except Exception: pass
                    pg2.wait_for_timeout(1800)
                    m2 = pg2.evaluate(MEASURE)
                    pg2.close()
                    tag = "%dx%d%s" % (w, h, "(遮断)" if block else "")
                    print("  %-12s %-16s %6d %6d %6d/%-2d %6d/%-2d %6d   止めた%d件%s%s"
                          % (tag, m["fontUsed"], m["stars"], m["labels"],
                             m["voiceShown"], m["voiceIn"], m["badges"], m["voiceTotal"],
                             m["cross"], len(blocked),
                             "" if m2["labels"] == m["labels"] else "  ← 2回目は%d件" % m2["labels"],
                             "  JSエラー%d" % len(errs) if errs else ""))
                    if block and not blocked:
                        found.append("%s フォント遮断が効いていない (検査が成立していない)" % tag)
                    if m2["labels"] != m["labels"]:
                        found.append("%s 同じ条件で開き直すとラベル数が変わる (%d → %d)"
                                     % (tag, m["labels"], m2["labels"]))
                    if block:
                        # 書体を別物に差し替えて、配置が組み直されるかを見る
                        pg.add_style_tag(content=SWAP)
                        pg.evaluate("()=>window.dispatchEvent(new Event('resize'))")
                        pg.wait_for_timeout(900)
                        m3 = pg.evaluate(MEASURE)
                        print("  %-12s %-16s %6d %6d %6d/%-2d %6d/%-2d %6d   書体を差し替え"
                              % ("  ↑書体差替", "Times/serif", m3["stars"], m3["labels"],
                                 m3["voiceShown"], m3["voiceIn"], m3["badges"],
                                 m3["voiceTotal"], m3["cross"]))
                        # 2026-08-14: 店数を 60 で直書きしていた。商店街モニュメントを消して
                        # 59 になった時に、実害が無いのにここだけ落ちる。GEO から取る。
                        if m3["stars"] != m3["total"]:
                            found.append("%s 書体差替で★が%d/%d件"
                                         % (tag, m3["stars"], m3["total"]))
                        if m3["voiceShown"] != m3["voiceIn"]:
                            found.append("%s 書体差替で表示域内の声ラベルが%d/%d (%s)"
                                         % (tag, m3["voiceShown"], m3["voiceIn"],
                                            "／".join(m3["missing"])))
                        if m3["badges"] != m3["voiceTotal"]:
                            found.append("%s 書体差替で声バッジが%d/%d"
                                         % (tag, m3["badges"], m3["voiceTotal"]))
                        if m3["cross"]:
                            found.append("%s 書体差替でラベルの重なり%d件" % (tag, m3["cross"]))
                    if block:
                        if m["stars"] != m["total"]:
                            found.append("%s ★が%d/%d件" % (tag, m["stars"], m["total"]))
                        if m["voiceShown"] != m["voiceIn"]:
                            found.append("%s 表示域内の声ラベルが%d/%d (%s)"
                                         % (tag, m["voiceShown"], m["voiceIn"], "／".join(m["missing"])))
                        if m["badges"] != m["voiceTotal"]:
                            found.append("%s 声バッジが%d/%d" % (tag, m["badges"], m["voiceTotal"]))
                        if m["cross"]:
                            found.append("%s ラベルの重なり%d件" % (tag, m["cross"]))
                        if errs:
                            found.append("%s JSエラー%d件: %s" % (tag, len(errs), errs[0][:60]))
                    pg.close()

            print()
            print("=" * 88)
            print("F2 端末の文字設定が大きい時")
            print("=" * 88)
            print("  %-16s %6s %8s %8s %8s %8s" %
                  ("端末/倍率", "地図px", "地図比率", "チップ", "段", "押しにくい"))
            for w, h in [(360, 640), (390, 844)]:
                for pct in (100, 125, 150):
                    pg = br.new_page(viewport={"width": w, "height": h})
                    pg.goto(base, wait_until="load"); pg.wait_for_timeout(400)
                    try: pg.evaluate(OPEN_MAP)
                    except Exception: pass
                    pg.wait_for_timeout(1100)
                    if pct != 100:
                        pg.evaluate("p=>{document.documentElement.style.fontSize=(16*p/100)+'px';}", pct)
                        pg.wait_for_timeout(900)
                    m = pg.evaluate(MEASURE); u = pg.evaluate(UIFIT)
                    tag = "%dx%d %d%%" % (w, h, pct)
                    print("  %-16s %6d %8.3f %8d %8d %8d%s"
                          % (tag, m["mapH"], m["ratio"], u["chipsVisible"], u["chipRows"],
                             len(u["small"]),
                             "  横スクロール%d" % u["pageScrollX"] if u["pageScrollX"] else ""))
                    if pct != 100:
                        if u["chipsVisible"] < 6:
                            found.append("%s カテゴリが%d個しか見えない" % (tag, u["chipsVisible"]))
                        if u["small"]:
                            found.append("%s 押しにくい%d件 (%s)" % (tag, len(u["small"]),
                                " / ".join("%s %dx%d" % (x["nm"], x["w"], x["h"]) for x in u["small"][:3])))
                        if u["off"]:
                            found.append("%s 画面外に出た操作要素 %s" % (tag, "／".join(u["off"][:3])))
                        if u["pageScrollX"]:
                            found.append("%s 横スクロールが出る (%dpx)" % (tag, u["pageScrollX"]))
                        if m["mapH"] < 200:
                            found.append("%s 地図が%dpxしかない" % (tag, m["mapH"]))
                    pg.close()

            print()
            print("=" * 88)
            print("F3 画面の表示と中身が一致するか")
            print("=" * 88)
            pg = br.new_page(viewport={"width": 390, "height": 844})
            pg.goto(base, wait_until="load"); pg.wait_for_timeout(1500)
            c = pg.evaluate(CONTENT)
            print("  店の数 %d / こどもの声 実データ %d件 / チップの表示「%s」"
                  % (c["shops"], c["voiceReal"], c["voiceChipTxt"]))
            print("  お店一覧の行 %d / 名前で検索して出ない店 %d件"
                  % (c["listRows"], len(c["searchMiss"])))
            if c["voiceChipNum"] != c["voiceReal"]:
                found.append("カテゴリの表示「%s」が実データ%d件と食い違う"
                             % (c["voiceChipTxt"], c["voiceReal"]))
            if c["listRows"] != c["shops"]:
                found.append("お店一覧の行が%d件で店の数%dと食い違う" % (c["listRows"], c["shops"]))
            for n in c["searchMiss"]:
                found.append("名前で検索しても出ない店: %s" % n)

            print()
            print("=" * 88)
            print("F4 絞り込みと検索を重ねた時")
            print("=" * 88)
            f = pg.evaluate(FLOW)
            print("  最初 %d → 絞り込み %d → +検索 %d → 検索解除 %d → 絞り込み解除 %d (戻った=%s)"
                  % (f["start"], f["afterFilter"], f["afterFilterAndSearch"],
                     f["afterClearSearch"], f["afterClearFilter"], f["restored"]))
            if not f["restored"]:
                found.append("絞り込みと検索を解除しても元に戻らない (%d → %d)"
                             % (f["start"], f["afterClearFilter"]))
            if f["afterFilter"] != c["voiceReal"]:
                found.append("こどもの声で絞り込むと%d件 (実データは%d件)"
                             % (f["afterFilter"], c["voiceReal"]))
            pg.close()
            br.close()
    finally:
        srv.terminate()
    print()
    print("=" * 88)
    if found:
        print("第2周の指摘: %d件" % len(found))
        for x in found:
            print("   " + x)
    else:
        print("第2周の指摘: 0件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
