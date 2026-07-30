#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""レンズG — 画面に出ている中身が、実データと一致しているか

ここまでの検査は「文字が読めるか・押せるか・位置が正しいか」を見てきた。
だが客が一番早く気づく間違いは「開いた店と違う中身が出ている」ことで、そこは無検査だった。

  G1 60店すべて、詳細シートの店名・住所・分類が実データと一致するか
  G2 こどもの声の件数表示が、その店の実データと一致するか
  G3 お店一覧の行を押すと、その店の詳細が出るか
  G4 公式ページのリンク先が実データと一致するか (リンクは開かない・href だけ見る)

外部への通信は一切しない。ページ内の表示と GEO を突き合わせるだけ。
"""
import io, os, socket, subprocess, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

DETAIL = r"""async () => {
  const norm = s => (s||'').replace(/\s+/g,' ').trim();
  const bad = [];
  const hits = [...document.querySelectorAll('g.hit')];
  for (const h of hits) {
    const i = +h.dataset.i, sp = GEO.shops[i];
    // 一覧から開く (地図の★は密集地でチューザーになるため)
    document.getElementById('listbtn').click();
    await new Promise(r=>setTimeout(r,180));
    const row = [...document.querySelectorAll('#listrows > *')]
      .find(x => norm(x.textContent).startsWith(norm(sp.name)));
    if (!row) { bad.push({n:sp.name, why:'お店一覧に行が無い'});
                document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                await new Promise(r=>setTimeout(r,120)); continue; }
    row.click();
    // 詳細シートは横スワイプの並びなので、切り替えが終わるまで待つ。
    // 待たずに読むと手前のカードを拾い、全店で「隣の店の中身」になる
    // (2026-07-31: これで20件以上の誤検出を出した)。
    await new Promise(r=>setTimeout(r,520));
    const dp = document.getElementById('detailPanel');
    if (!dp || dp.getAttribute('aria-hidden') === 'true') {
      bad.push({n:sp.name, why:'一覧の行を押しても詳細が出ない'});
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
      await new Promise(r=>setTimeout(r,120)); continue;
    }
    // 画面の中心に一番近いカードが「いま見えているカード」。
    // 横に重なっているだけのカードを DOM 順で拾わない。
    const mid = innerWidth / 2;
    let card = null, best = Infinity;
    for (const c of dp.querySelectorAll('.detail-card')) {
      const r = c.getBoundingClientRect();
      if (r.width < 1) continue;
      const d = Math.abs((r.left + r.right) / 2 - mid);
      if (d < best) { best = d; card = c; }
    }
    if (!card) { bad.push({n:sp.name, why:'詳細のカードが見えない'});
                 document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                 await new Promise(r=>setTimeout(r,120)); continue; }
    const gotName = norm((card.querySelector('h2')||{}).textContent);
    const gotAddr = norm((card.querySelector('.detail-address')||{}).textContent)
                      .replace(/^[^\p{L}\p{N}]+/u,'');
    const gotCat  = norm((card.querySelector('.detail-cat')||{}).textContent);
    const link = card.querySelector('a.detail-link');
    const gotHref = link ? link.getAttribute('href') : null;
    const voiceBtn = card.querySelector('button.detail-status.voice');
    const gotVoice = voiceBtn ? norm(voiceBtn.textContent) : null;

    if (gotName !== norm(sp.name))
      bad.push({n:sp.name, why:'店名が違う: 「'+gotName+'」'});
    if (sp.addr && gotAddr && norm(sp.addr) !== gotAddr)
      bad.push({n:sp.name, why:'住所が違う: 実「'+norm(sp.addr)+'」画面「'+gotAddr+'」'});
    if (sp.addr && !gotAddr)
      bad.push({n:sp.name, why:'住所が出ていない (実データにはある)'});
    const vn = (sp.voices||[]).length;
    if (vn && !gotVoice) bad.push({n:sp.name, why:'こどもの声'+vn+'件があるのにボタンが無い'});
    if (!vn && gotVoice) bad.push({n:sp.name, why:'こどもの声が無いのにボタンがある'});
    if (vn && gotVoice) {
      const m = gotVoice.match(/(\d+)/);
      if (!m || +m[1] !== vn)
        bad.push({n:sp.name, why:'こどもの声の件数が違う: 実'+vn+'件 画面「'+gotVoice+'」'});
    }
    const hasUrl = sp.url && sp.url !== '#';
    if (hasUrl && !gotHref) bad.push({n:sp.name, why:'公式ページがあるのにリンクが無い'});
    if (!hasUrl && gotHref) bad.push({n:sp.name, why:'公式ページが無いのにリンクがある'});
    if (hasUrl && gotHref && gotHref !== sp.url)
      bad.push({n:sp.name, why:'リンク先が違う: 実「'+sp.url+'」画面「'+gotHref+'」'});
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await new Promise(r=>setTimeout(r,120));
  }
  return {checked: hits.length, bad};
}"""


def main():
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
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page(viewport={"width": 390, "height": 844})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base, wait_until="load"); pg.wait_for_timeout(1600)
            r = pg.evaluate(DETAIL)
            print("=" * 88)
            print("レンズG — 画面の中身と実データの突き合わせ (%d店)" % r["checked"])
            print("=" * 88)
            if r["bad"]:
                print("食い違い: %d件" % len(r["bad"]))
                for b in r["bad"]:
                    print("   %-26s %s" % (b["n"], b["why"]))
            else:
                print("食い違い: 0件")
            print("   JSエラー: %d件%s" % (len(errs), " " + errs[0][:60] if errs else ""))
            pg.close(); br.close()
    finally:
        srv.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
