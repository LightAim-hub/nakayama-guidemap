#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズH — UI/UX 規約 (ui-ux-pro-max) を1項目ずつ実測する

規約を読むだけでは何も分からないので、公開中のページに当てて測る。
対象は「スマホで歩きながら店を探す」用途に効くものだけ。
LP構成・配色・書体の提案は、この案件では採らない (手描きの世界観が要件)。

  H1  文字と背景の明暗差 (4.5:1 以上・大きい文字は3:1)
  H2  キーボードの通り道 (焦点が見えるか・順序が見た目と合うか・行き止まりが無いか)
  H3  アイコンだけのボタンに読み上げ名があるか
  H4  意味のある要素が button/a/label で書かれているか
  H5  押せるもの同士の間隔 (8px 以上)
  H6  動きを減らす設定 (prefers-reduced-motion) を尊重しているか
  H7  読み込みで画面が飛び跳ねないか (画像に寸法があるか)
  H8  非同期の変化が読み上げられるか (aria-live)
  H9  飾りのアイコンが読み上げから隠されているか
  H10 入力欄にラベルがあるか
  H11 本文の文字の大きさと行間
  H12 絵文字をアイコン代わりに使っていないか
"""
import io, os, socket, subprocess, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

DEVICES = [("小型Android", 360, 640), ("iPhone 14", 390, 844)]

COMMON = r"""
const shown = e => { const cs = getComputedStyle(e);
  return cs.display !== 'none' && cs.visibility !== 'hidden'
      && parseFloat(cs.opacity) > .05 && e.getAttribute('aria-hidden') !== 'true'; };
const vis = e => { for (let n=e;n&&n!==document.documentElement;n=n.parentElement)
    if (!shown(n)) return false;
  const r = e.getBoundingClientRect();
  if (!(r.width>0&&r.height>0)) return false;
  const iw=Math.min(r.right,innerWidth)-Math.max(r.left,0);
  const ih=Math.min(r.bottom,innerHeight)-Math.max(r.top,0);
  return iw>0&&ih>0&&(iw*ih)>=.5*(r.width*r.height); };
const nameOf = e => (e.getAttribute('aria-label') || e.getAttribute('title')
  || (e.labels && e.labels[0] && e.labels[0].textContent) || e.textContent || '').trim();
const sel = e => { const p=e.parentElement;
  const cn = x => x && typeof x.className==='string' && x.className.trim()
    ? '.'+x.className.trim().split(/\s+/).slice(0,2).join('.') : '';
  return e.id ? '#'+e.id : (cn(p)?cn(p)+' > ':'')+e.tagName.toLowerCase()+cn(e); };
const parseColor = s => {
  const m = (s||'').match(/rgba?\(([^)]+)\)/); if (!m) return null;
  const p = m[1].split(',').map(v=>parseFloat(v));
  return {r:p[0], g:p[1], b:p[2], a:p.length>3?p[3]:1}; };
const lum = c => { const f = v => { v/=255; return v<=.03928 ? v/12.92
    : Math.pow((v+.055)/1.055, 2.4); };
  return .2126*f(c.r)+.7152*f(c.g)+.0722*f(c.b); };
const ratio = (a,b) => { const l1=lum(a), l2=lum(b);
  return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05); };
const bgOf = e => {
  for (let n=e; n; n=n.parentElement) {
    const c = parseColor(getComputedStyle(n).backgroundColor);
    if (c && c.a > .5) return c;
    if (n === document.body) break;
  }
  // SVG の中は地図の紙色
  if (e.closest('svg')) {
    const paper = getComputedStyle(document.documentElement)
      .getPropertyValue('--paper').trim();
    if (paper) { const d=document.createElement('div'); d.style.color=paper;
      document.body.appendChild(d);
      const c=parseColor(getComputedStyle(d).color); d.remove(); if (c) return c; }
  }
  return {r:255,g:255,b:255,a:1}; };
"""

AUDIT = COMMON + r"""
const out = {};

// ---- H1 文字と背景の明暗差 ----
out.contrast = [];
{
  const seen = new Set();
  for (const e of document.querySelectorAll('body *')) {
    // 地図の文字は表示域の外でも、動かせば見える。地図の中は画面内判定を課さない
    // (2026-07-31: 川の名前 3.56:1 を「画面外だから」と見落とした)。
    const inMap = !!e.closest('svg');
    if (!inMap && !vis(e)) continue;
    if (inMap && (getComputedStyle(e).display === 'none'
                  || e.getBoundingClientRect().width < 1)) continue;
    if (![...e.childNodes].some(n=>n.nodeType===3 && n.textContent.trim())) continue;
    const cs = getComputedStyle(e);
    const fg = parseColor(e.closest('svg') ? cs.fill : cs.color);
    if (!fg) continue;
    const bg = bgOf(e);
    const r = ratio(fg, bg);
    const px = parseFloat(cs.fontSize);
    const bold = (parseInt(cs.fontWeight)||400) >= 700;
    const large = px >= 24 || (px >= 18.66 && bold);
    const need = large ? 3.0 : 4.5;
    if (r < need) {
      const k = sel(e);
      if (seen.has(k)) continue; seen.add(k);
      out.contrast.push({sel:k, txt:(e.textContent||'').trim().slice(0,18),
        ratio:+r.toFixed(2), need, px:+px.toFixed(1),
        fg:[fg.r,fg.g,fg.b], bg:[bg.r,bg.g,bg.b]});
    }
  }
}

// ---- H3 / H4 / H9 / H10 ----
out.noName = []; out.fakeButton = []; out.decorative = []; out.noLabel = [];
for (const e of document.querySelectorAll('button,a[href],[role="button"],input,select')) {
  if (!vis(e)) continue;
  const nm = nameOf(e);
  if (e.tagName === 'INPUT' || e.tagName === 'SELECT') {
    const hasLabel = (e.labels && e.labels.length) || e.getAttribute('aria-label')
                   || e.getAttribute('aria-labelledby');
    if (!hasLabel) out.noLabel.push({sel:sel(e), ph:e.placeholder||''});
    continue;
  }
  if (!nm) out.noName.push({sel:sel(e), html:e.outerHTML.slice(0,60)});
  // SVG の地図の中は <button> を置けない。role=button + tabindex + 読み上げ名 +
  // キーボードで開けること、が揃っていれば正しい書き方なので不合格にしない
  // (2026-07-31: これを 29件の誤検出として出した)。
  const svgOk = e.closest('svg') && e.getAttribute('role') === 'button'
             && e.getAttribute('tabindex') !== null && nm;
  if (e.tagName !== 'BUTTON' && e.tagName !== 'A'
      && e.getAttribute('role') === 'button' && !svgOk)
    out.fakeButton.push({sel:sel(e), nm:nm.slice(0,18)});
}

// ---- H13 地図を飛ばす手段 (WCAG 2.4.1) ----
// 地図の★が Tab の通り道に入ると、フッタへ着くまでに60回押すことになる。
out.bypass = (() => {
  const tabbable = [...document.querySelectorAll(
    'button,a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter(vis);
  const inMap = tabbable.filter(e => e.closest('svg'));
  const skip = [...document.querySelectorAll('a[href^="#"]')]
    .filter(a => /とば|スキップ|skip|飛ば/i.test(a.textContent || a.getAttribute('aria-label') || ''));
  return {total: tabbable.length, inMap: inMap.length, skipLinks: skip.length};
})();
for (const e of document.querySelectorAll('svg[aria-hidden], svg:not([aria-hidden])')) {
  if (e.id === 'map') continue;
  if (!vis(e)) continue;
  const insideButton = e.closest('button, a[href], [role="button"]');
  if (insideButton && e.getAttribute('aria-hidden') !== 'true'
      && !e.querySelector('title'))
    out.decorative.push({sel:sel(e), inside:sel(insideButton)});
}

// ---- H5 押せるもの同士の間隔 ----
out.tight = [];
{
  const els = [...document.querySelectorAll('button,a[href],input,[role="button"]')]
    .filter(e => vis(e) && !e.closest('svg'))
    .map(e => ({nm:nameOf(e).slice(0,14), r:e.getBoundingClientRect()}));
  for (let i=0;i<els.length;i++) for (let j=i+1;j<els.length;j++) {
    const a=els[i].r, b=els[j].r;
    const ox = Math.max(0, Math.min(a.right,b.right)-Math.max(a.left,b.left));
    const oy = Math.max(0, Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
    if (ox>0 && oy>0) continue;                       // 重なりは別問題
    const dx = ox>0 ? 0 : Math.max(a.left-b.right, b.left-a.right);
    const dy = oy>0 ? 0 : Math.max(a.top-b.bottom, b.top-a.bottom);
    const gap = Math.hypot(Math.max(dx,0), Math.max(dy,0));
    if (gap < 8) out.tight.push({a:els[i].nm, b:els[j].nm, gap:+gap.toFixed(1)});
  }
}

// ---- H7 画像に寸法があるか ----
out.noDim = [];
for (const e of document.querySelectorAll('img')) {
  if (!e.getAttribute('width') || !e.getAttribute('height')) {
    const cs = getComputedStyle(e);
    const fixed = cs.aspectRatio !== 'auto'
      || (cs.height !== 'auto' && parseFloat(cs.height) > 0);
    if (!fixed) out.noDim.push({sel:sel(e), src:(e.getAttribute('src')||'').slice(-28)});
  }
}

// ---- H8 aria-live ----
out.live = [...document.querySelectorAll('[aria-live],[role="status"],[role="alert"]')]
  .map(e => ({sel:sel(e), v:e.getAttribute('aria-live')||e.getAttribute('role')}));
out.searchStatus = (() => { const e = document.getElementById('searchstatus');
  return e ? {exists:true, live:e.getAttribute('aria-live')||e.getAttribute('role')||null} : {exists:false}; })();

// ---- H11 本文の文字と行間 ----
out.body = (() => { const cs = getComputedStyle(document.body);
  const px = parseFloat(cs.fontSize);
  const lh = cs.lineHeight === 'normal' ? null : parseFloat(cs.lineHeight)/px;
  return {px:+px.toFixed(1), lh: lh ? +lh.toFixed(2) : null}; })();
out.smallBody = [];
for (const e of document.querySelectorAll('p, li, td, .lrow span, .detail-card p')) {
  if (!vis(e)) continue;
  const cs = getComputedStyle(e);
  const px = parseFloat(cs.fontSize);
  const lh = cs.lineHeight === 'normal' ? 1.2 : parseFloat(cs.lineHeight)/px;
  if (px < 16 || lh < 1.4)
    out.smallBody.push({sel:sel(e), px:+px.toFixed(1), lh:+lh.toFixed(2),
                        txt:(e.textContent||'').trim().slice(0,16)});
}

// ---- H12 絵文字をアイコン代わりに使っていないか ----
out.emoji = [];
{
  const EMO = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/u;
  for (const e of document.querySelectorAll('button, a[href], [role="button"], .chip')) {
    if (!vis(e)) continue;
    const t = e.textContent || '';
    if (EMO.test(t)) out.emoji.push({sel:sel(e), txt:t.trim().slice(0,18)});
  }
}

// ---- viewport meta ----
out.viewport = (document.querySelector('meta[name="viewport"]')||{}).content || '(なし)';
out.lang = document.documentElement.getAttribute('lang') || '(なし)';
out.title = document.title;
return out;
"""

FOCUS = COMMON + r"""
// ---- H2 キーボードの通り道 ----
const items = [...document.querySelectorAll(
  'button,a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')]
  .filter(e => vis(e));
// 焦点の見た目は子要素に付くことがある (この地図は .hit:focus-visible .star に
// drop-shadow と stroke-width を当てている)。親の outline だけを見ると
// 「焦点が見えない」を大量に誤検出する — 2026-07-31 に29件出した。
// 自分と子孫の、焦点表示に使われうる性質をまとめて比べる。
const snap = e => {
  const parts = [];
  for (const n of [e, ...e.querySelectorAll('*')].slice(0, 12)) {
    const c = getComputedStyle(n);
    parts.push([c.outlineStyle, c.outlineWidth, c.outlineColor, c.boxShadow,
                c.borderColor, c.backgroundColor, c.filter, c.stroke,
                c.strokeWidth, c.opacity, c.transform].join(','));
  }
  return parts.join('|');
};
const res = [];
for (const e of items) {
  const b0 = snap(e);
  e.focus({preventScroll:true});
  const b1 = snap(e);
  const after = getComputedStyle(e);
  const r = e.getBoundingClientRect();
  res.push({sel:sel(e), nm:nameOf(e).slice(0,16), changed: b0 !== b1,
            outline: after.outlineStyle + ' ' + after.outlineWidth,
            x:Math.round(r.left), y:Math.round(r.top)});
  e.blur();
}
return {count: items.length, res};
"""

MOTION = r"""() => {
  const out = [];
  for (const e of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(e);
    const td = parseFloat(cs.transitionDuration) || 0;
    const ad = parseFloat(cs.animationDuration) || 0;
    if (td > 0.01 || ad > 0.01) {
      const cn = typeof e.className==='string' && e.className.trim()
        ? '.'+e.className.trim().split(/\s+/)[0] : e.tagName.toLowerCase();
      out.push({sel:(e.id?'#'+e.id:cn), td:+td.toFixed(3), ad:+ad.toFixed(3)});
    }
  }
  const seen = new Set(), uniq = [];
  for (const o of out) { if (seen.has(o.sel)) continue; seen.add(o.sel); uniq.push(o); }
  return uniq;
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
    url = None
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        url, srv = sys.argv[1], None
    else:
        srv, url = serve()
    found = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for nm, w, h in DEVICES:
                pg = br.new_page(viewport={"width": w, "height": h})
                pg.goto(url, wait_until="load"); pg.wait_for_timeout(1600)
                A = pg.evaluate("() => {" + AUDIT + "}")
                F = pg.evaluate("() => {" + FOCUS + "}")
                print("=" * 90)
                print("%s %dx%d — %s" % (nm, w, h, A["title"]))
                print("=" * 90)
                print("  viewport: %s / lang: %s" % (A["viewport"], A["lang"]))
                print("  本文: %.1fpx / 行間 %s" % (A["body"]["px"], A["body"]["lh"]))

                def rep(key, label, fmt):
                    v = A.get(key) or []
                    print("  %-34s %s" % (label, ("%d件" % len(v)) if v else "なし"))
                    for x in v[:6]:
                        print("        " + fmt(x))
                        found.append("%s %s: %s" % (nm, label, fmt(x)))
                    if len(v) > 6:
                        print("        ...他 %d件" % (len(v) - 6))

                rep("contrast", "H1 明暗差が足りない文字",
                    lambda x: "%s「%s」 %.2f:1 (必要%.1f / %.1fpx) 文字rgb%s 背景rgb%s"
                              % (x["sel"], x["txt"], x["ratio"], x["need"], x["px"],
                                 tuple(x["fg"]), tuple(x["bg"])))
                rep("noName", "H3 読み上げ名の無いボタン", lambda x: "%s  %s" % (x["sel"], x["html"]))
                rep("fakeButton", "H4 button/a でない操作要素", lambda x: "%s (%s)" % (x["sel"], x["nm"]))
                rep("noLabel", "H10 ラベルの無い入力欄", lambda x: "%s (%s)" % (x["sel"], x["ph"]))
                rep("decorative", "H9 読み上げから隠れていない飾り",
                    lambda x: "%s (%s の中)" % (x["sel"], x["inside"]))
                rep("tight", "H5 押せるもの同士が8px未満",
                    lambda x: "「%s」と「%s」が %.1fpx" % (x["a"], x["b"], x["gap"]))
                rep("noDim", "H7 寸法の無い画像", lambda x: "%s (%s)" % (x["sel"], x["src"]))
                rep("smallBody", "H11 本文16px未満 or 行間1.4未満",
                    lambda x: "%s「%s」 %.1fpx / 行間%.2f" % (x["sel"], x["txt"], x["px"], x["lh"]))
                rep("emoji", "H12 絵文字をアイコンに使用",
                    lambda x: "%s「%s」" % (x["sel"], x["txt"]))

                bp = A["bypass"]
                print("  %-34s 操作要素%d件中 地図の★が%d件 / 飛ばすリンク%d件%s"
                      % ("H13 地図を飛ばす手段", bp["total"], bp["inMap"], bp["skipLinks"],
                         "" if bp["skipLinks"] else "  ← キーボードだと★を全部通る"))
                if bp["inMap"] > 10 and not bp["skipLinks"]:
                    found.append("%s H13 地図の★が%d件Tabの通り道にあり、飛ばすリンクが無い"
                                 % (nm, bp["inMap"]))

                ss = A["searchStatus"]
                print("  %-34s %s" % ("H8 検索結果の読み上げ (aria-live)",
                      ("あり (%s)" % ss["live"]) if ss.get("live") else
                      ("要素はあるが aria-live 無し" if ss.get("exists") else "要素なし")))
                if ss.get("exists") and not ss.get("live"):
                    found.append("%s H8 検索結果に aria-live が無い" % nm)

                nofocus = [x for x in F["res"] if not x["changed"]]
                print("  %-34s %d件 / 操作要素%d件"
                      % ("H2 焦点が見えない操作要素", len(nofocus), F["count"]))
                for x in nofocus[:6]:
                    print("        %s (%s) outline=%s" % (x["sel"], x["nm"], x["outline"]))
                    found.append("%s H2 焦点が見えない: %s (%s)" % (nm, x["sel"], x["nm"]))
                # タブ順が見た目の順と合うか (上→下、同じ行なら左→右)
                order = F["res"]
                bad_order = []
                for i in range(len(order) - 1):
                    a, b = order[i], order[i+1]
                    if b["y"] < a["y"] - 24:
                        bad_order.append("%s → %s (y %d → %d)" % (a["nm"], b["nm"], a["y"], b["y"]))
                print("  %-34s %s" % ("H2 タブ順が見た目と逆行",
                                      ("%d件" % len(bad_order)) if bad_order else "なし"))
                for x in bad_order[:4]:
                    print("        " + x)
                    found.append("%s H2 タブ順の逆行: %s" % (nm, x))
                pg.close()

            # ---- H6 動きを減らす設定 ----
            print()
            print("=" * 90)
            print("H6 動きを減らす設定 (prefers-reduced-motion) を尊重しているか")
            print("=" * 90)
            for pref in ("no-preference", "reduce"):
                pg = br.new_page(viewport={"width": 390, "height": 844})
                pg.emulate_media(reduced_motion=pref)
                pg.goto(url, wait_until="load"); pg.wait_for_timeout(1400)
                mv = pg.evaluate(MOTION)
                print("  %-16s 動きのある要素 %d種  %s"
                      % (pref, len(mv), " / ".join("%s %.2fs" % (m["sel"], max(m["td"], m["ad"]))
                                                   for m in mv[:5])))
                if pref == "reduce":
                    if mv:
                        found.append("動きを減らす設定でも %d種の要素が動く (%s)"
                                     % (len(mv), "／".join(m["sel"] for m in mv[:4])))
                pg.close()
            br.close()
    finally:
        if srv:
            srv.terminate()
    print()
    print("=" * 90)
    if found:
        print("UI/UX 規約に対する指摘: %d件" % len(found))
        for x in found:
            print("   " + x)
    else:
        print("UI/UX 規約に対する指摘: 0件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
