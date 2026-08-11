# -*- coding: utf-8 -*-
"""前と変わっていないかを見る (gate は「違反していないか」しか見ない)。

2026-08-10 に3回、gate が緑のまま見た目を劣化させた:
  ・既定の端末で見出しが 19.2px → 18px に縮んだ
  ・検索欄が端末の文字設定に一切追従しなくなった (clamp の min==max)
  ・チップが行頭「・」で折り返すようになった
どれも「規則違反ではない劣化」なので、違反を数える検査では永久に出ない。

そこで、画面に出ている値そのものを台帳に取って、変わったら必ず人の目に出す。
変えたいなら台帳を更新する (= 変更を意図として記録する)。黙って変わることを無くす。

  python tools/v2-build/baseline.py            # いまと台帳を比べる (差分があれば exit 1)
  python tools/v2-build/baseline.py --update   # いまの値を台帳に焼く (意図した変更の時だけ)

対象は「今日壊した種類」= 文字の大きさ・太さ・色・行の高さ・押すものの大きさ。
位置は動いて当然なので入れない (騒がしくすると読まれなくなる)。
"""
import argparse, io, json, os, socket, subprocess, sys, time

# tools/v2-build/baseline.py → tools/v2-build → tools → リポジトリ直下
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")

ap = argparse.ArgumentParser()
ap.add_argument("--update", action="store_true", help="いまの値を台帳に焼く")
ap.add_argument("--url", default=None)
A = ap.parse_args()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright   # noqa: E402

# 端末 x 文字サイズ。今日の劣化は「既定16px」と「200%」の両方で起きた。
CASES = [(390, 844, 16), (390, 844, 32), (320, 568, 16), (320, 568, 32)]

STATES = [
    ("入口", "()=>true"),
    ("一覧", "async()=>{const lb=document.getElementById('listbtn'); if(!lb) return false; lb.click();"
             "await new Promise(r=>setTimeout(r,600));return true;}"),
    ("詳細", "async()=>{const r=document.querySelector('#listrows .lrow');"
             "if(!r)return false;r.click();await new Promise(r2=>setTimeout(r2,900));return true;}"),
    ("地図", "async()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));"
             "await new Promise(r=>setTimeout(r,400));"
             "const b=document.getElementById('mapbtn'); if(!b) return false;"
             "if(b.getAttribute('aria-expanded')!=='true')b.click();"
             "await new Promise(r=>setTimeout(r,900));return true;}"),
]

# 台帳に載せる要素。増やしすぎると差分が騒がしくなるので、意味のある単位だけ。
WATCH = [
    "header h1", ".shop-total-summary", "header p", ".chip .lbl", ".searchbar input",
    "#searchstatus", "#mapbtn", "#listbtn", ".strip-shop-name", ".strip-distance",
    ".lrow .lname", ".lrow .laddr", ".detail-card h2", ".detail-fact-value",
    ".detail-fact-label", ".detail-nav button", ".detail-guide", ".detail-voice",
    ".empty-help-title", ".empty-help-lead", ".far-section h2", "#mapback", "#wholebtn",
]

JS = """(sels)=>{
  const out={};
  for (const s of sels){
    const e=document.querySelector(s);
    if(!e) continue;
    const cs=getComputedStyle(e), b=e.getBoundingClientRect();
    if(!(b.width>0&&b.height>0)) continue;
    const lh=parseFloat(cs.lineHeight);
    out[s]={
      文字:Math.round(parseFloat(cs.fontSize)*10)/10,
      太さ:cs.fontWeight,
      色:cs.color,
      行:lh?Math.round(lh/parseFloat(cs.fontSize)*100)/100:null,
      幅:Math.round(b.width), 高:Math.round(b.height),
      行数:(()=>{const r=document.createRange();r.selectNodeContents(e);
        const t=new Set([...r.getClientRects()].map(x=>Math.round(x.top)));
        return t.size||1;})()
    };
  }
  return out;
}"""


def measure(url):
    got = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for w, h, fs in CASES:
            ctx = br.new_context(viewport={"width": w, "height": h})
            pg = ctx.new_page()
            if fs != 16:
                c = ctx.new_cdp_session(pg); c.send("Page.enable")
                c.send("Page.setFontSizes", {"fontSizes": {"standard": fs, "fixed": fs}})
            pg.goto(url); pg.wait_for_load_state("networkidle")
            pg.evaluate("()=>document.fonts.ready"); pg.wait_for_timeout(600)
            for nm, act in STATES:
                try:
                    if pg.evaluate(act) is False:
                        continue
                except Exception as e:
                    print("  ! %dx%d 文字%d / %s を作れない: %s"
                          % (w, h, fs, nm, str(e).splitlines()[0][:80]))
                    continue
                pg.wait_for_timeout(200)
                for sel, val in pg.evaluate(JS, WATCH).items():
                    got["%dx%d 文字%d / %s / %s" % (w, h, fs, nm, sel)] = val
            ctx.close()
        br.close()
    return got


url, srv = A.url, None
if not url:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d/index.html" % port
    time.sleep(1.2)
try:
    now = measure(url)
finally:
    if srv:
        srv.terminate()

if A.update or not os.path.exists(BASE):
    io.open(BASE, "w", encoding="utf-8").write(json.dumps(now, ensure_ascii=False, indent=1, sort_keys=True))
    print("台帳を更新しました (%d項目) → %s" % (len(now), os.path.relpath(BASE, ROOT)))
    sys.exit(0)

old = json.loads(io.open(BASE, encoding="utf-8").read())
changed, gone, added = [], [], []
for k, v in sorted(now.items()):
    if k not in old:
        added.append(k); continue
    diff = {f: (old[k].get(f), v.get(f)) for f in v if old[k].get(f) != v.get(f)}
    # 幅と高さは中身の量で動くので、1px の揺れは黙らせる
    diff = {f: d for f, d in diff.items()
            if f not in ("幅", "高") or abs((d[0] or 0) - (d[1] or 0)) > 1}
    if diff:
        changed.append((k, diff))
for k in old:
    if k not in now:
        gone.append(k)

if not (changed or gone or added):
    print("台帳と一致 (%d項目)。前と変わっていません。" % len(now))
    sys.exit(0)

print("== 前と変わったもの ==")
for k, d in changed:
    print("  %s" % k)
    for f, (a, b) in d.items():
        print("      %s: %s → %s" % (f, a, b))
for k in gone:
    print("  ✗ 消えた: %s" % k)
for k in added:
    print("  + 増えた: %s" % k)
print("\n変えたつもりが無いなら直す。意図した変更なら --update で台帳に焼く。")
sys.exit(1)
