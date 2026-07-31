# -*- coding: utf-8 -*-
"""eyes.py — 全状態の絵を撮って1枚に並べる。数字の検査より先に回すもの。

なぜ要るか (2026-07-31):
  gate.py の N1-N44 が全部0件で PASS した状態のまま、ボスに
  「マップの方見切れてない? 操作間が悪い ボタン単一が押しにくい」と言われた。
  原因は単純で、地図を開いた画面もスクロールした先も一度も見ていなかったから。
  採点表は「思いついた項目」しか捕まえない。思いついていない欠陥は、絵を見ないと出ない。

使い方:
  python tools/v2-build/eyes.py          # 全端末
  python tools/v2-build/eyes.py A        # 390x844 だけ
  → _eyes/sheet_<端末>_1.png と _2.png を必ず全部 目で見る。見ないなら回す意味がない。

規律: 完了と言う前に、この12状態 x 端末を撮って、全部見る。
      gate.py が PASS でも、絵に問題があればそれは PASS ではない。
"""
import os, sys, io
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_eyes")
URL = "file:///" + ROOT.replace("\\", "/") + "/index.html"

DEV = [("A", 390, 844), ("S", 360, 640), ("L", 428, 926), ("W", 844, 390)]

def jfont(sz):
    for p in [r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except Exception: pass
    return ImageFont.load_default()

def open_map(pg):
    pg.evaluate("""() => { const b=document.getElementById('mapbtn');
        if (b && b.getAttribute('aria-expanded')!=='true') b.click(); }""")
    pg.wait_for_timeout(800)

def close_map(pg):
    pg.evaluate("""() => { const b=document.getElementById('mapbtn');
        if (b && b.getAttribute('aria-expanded')==='true') b.click(); }""")
    pg.wait_for_timeout(600)

def scroll_strip(pg, frac):
    pg.evaluate("""(f) => { const v=document.getElementById('stripview');
        v.scrollTop = (v.scrollHeight - v.clientHeight) * f; }""", frac)
    pg.wait_for_timeout(400)

def shots(pg, tag):
    got = []
    def snap(name):
        p = os.path.join(OUT, "%s_%s.png" % (tag, name))
        pg.screenshot(path=p)
        got.append((name, p))

    scroll_strip(pg, 0.0); snap("01-二列 先頭")
    scroll_strip(pg, 0.35); snap("02-二列 35%")
    scroll_strip(pg, 0.70); snap("03-二列 70%")
    scroll_strip(pg, 1.0); snap("04-二列 最後")
    scroll_strip(pg, 0.0)

    # 検索
    pg.fill("#q", "ケーキ"); pg.wait_for_timeout(500); snap("05-検索中")
    pg.fill("#q", ""); pg.wait_for_timeout(400)

    # 絞り込み(声)
    pg.evaluate("""() => { const c=document.querySelector('.chip.voice-filter'); if(c) c.click(); }""")
    pg.wait_for_timeout(500); snap("06-声で絞込")
    pg.evaluate("""() => { const c=document.querySelector('.chip.voice-filter');
        if(c && c.getAttribute('aria-pressed')==='true') c.click(); }""")
    pg.wait_for_timeout(400)

    # 詳細(二列のカードから)
    pg.evaluate("""() => { const r=document.querySelector('#strip .strip-row:not([hidden])'); if(r) r.click(); }""")
    pg.wait_for_timeout(800); snap("07-店の詳細")
    pg.evaluate("""() => { const b=document.getElementById('detailClose'); if(b) b.click(); }""")
    pg.wait_for_timeout(500)

    # 一覧
    pg.evaluate("""() => { const b=document.getElementById('listbtn');
        if(b && b.getAttribute('aria-expanded')!=='true') b.click(); }""")
    pg.wait_for_timeout(700); snap("08-お店一覧")
    pg.evaluate("""() => { const b=document.getElementById('listclose'); if(b) b.click(); }""")
    pg.wait_for_timeout(500)

    # === 地図(今まで一度も見ていなかった領域) ===
    open_map(pg); snap("09-地図 開いた直後")

    pg.evaluate("""() => { const v=document.getElementById('viewport');
        v.scrollTop = v.scrollHeight * 0.5; }""")
    pg.wait_for_timeout(500); snap("10-地図 中ほど")

    for _ in range(3):
        pg.evaluate("""() => { const b=document.getElementById('zin'); if(b) b.click(); }""")
        pg.wait_for_timeout(350)
    snap("11-地図 拡大3回")

    # 地図で店をタップ
    pg.evaluate("""() => { const h=document.querySelector('#map .hit:not(.dim)'); if(h) h.dispatchEvent(
        new MouseEvent('click', {bubbles:true})); }""")
    pg.wait_for_timeout(900); snap("12-地図から詳細")

    # 2026-08-01 追加。採点表の総なめに「地図で絞り込み中」を足した時、
    # 絵の側に足し忘れると同じ穴が空く。状態は採点表と揃える。
    pg.evaluate("""() => { const b=document.getElementById('detailClose'); if(b) b.click(); }""")
    pg.wait_for_timeout(500)
    pg.evaluate("""() => { const c=document.querySelector('.chip.voice-filter');
        if(c && c.getAttribute('aria-pressed')!=='true') c.click(); }""")
    pg.wait_for_timeout(800); snap("13-地図で絞り込み中")
    pg.evaluate("""() => { const c=document.querySelector('.chip.voice-filter');
        if(c && c.getAttribute('aria-pressed')==='true') c.click(); }""")
    pg.wait_for_timeout(500)
    pg.evaluate("""() => { const b=document.getElementById('detailClose'); if(b) b.click(); }""")
    pg.wait_for_timeout(500)
    close_map(pg)
    return got


def sheet(items, path, cols=4, scale=1.0, title=""):
    ims = []
    for name, p in items:
        im = Image.open(p).convert("RGB")
        if scale != 1.0:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        ims.append((name, im))
    if not ims: return None
    cw = max(i.width for _, i in ims); ch = max(i.height for _, i in ims)
    lab = 26; pad = 8
    rows = (len(ims) + cols - 1) // cols
    W = cols * (cw + pad) + pad
    H = rows * (ch + lab + pad) + pad + 30
    sh = Image.new("RGB", (W, H), (30, 30, 34))
    d = ImageDraw.Draw(sh); f = jfont(17); ft = jfont(20)
    d.text((pad, 6), title, font=ft, fill=(255, 235, 150))
    for k, (name, im) in enumerate(ims):
        r, c = divmod(k, cols)
        x = pad + c * (cw + pad); y = 30 + pad + r * (ch + lab + pad)
        d.text((x + 2, y), name, font=f, fill=(255, 255, 255))
        sh.paste(im, (x, y + lab))
        d.rectangle([x, y + lab, x + im.width, y + lab + im.height], outline=(120, 200, 255), width=2)
    sh.save(path)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    with sync_playwright() as p:
        br = p.chromium.launch()
        for tag, w, h in DEV:
            if only and tag != only: continue
            pg = br.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg.goto(URL); pg.wait_for_timeout(1600)
            got = shots(pg, tag)
            pg.close()
            got.sort()
            n = len(got)
            half = (n + 1) // 2
            sheet(got[:half], os.path.join(OUT, "sheet_%s_1.png" % tag), cols=3,
                  title="%s  %dx%d  (1/2)" % (tag, w, h))
            sheet(got[half:], os.path.join(OUT, "sheet_%s_2.png" % tag), cols=3,
                  title="%s  %dx%d  (2/2)" % (tag, w, h))
            print("%s %dx%d : %d枚" % (tag, w, h, n))
        br.close()
    print(OUT)

main()
