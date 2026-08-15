#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""なかやまマップ 単一合格ゲート — 「地図を見ながら歩いて、正しくその店に行けるか」

ボスの合格定義 (2026-07-30):
  「使いやすいな見やすいなって思うのと同時に、この店舗はここの向かい側あってるね
    みたいな、そのマップを見ながら歩いた時に正しくその店に行けるようにしないといけない」

= 正しい位置関係 と 見やすさ が同時に成り立つこと。片方だけでは不合格。

店ごとに N1..N52 を判定し、全部通った店だけ「歩ける (NAVIGABLE)」とする。
1件でも落ちれば exit 1。

  N1..N10  位置関係と歩きズームでの見やすさ
  N11..N15 概観ズーム (開いた瞬間の画面) での見やすさ  ← 2026-07-30 追加
  N16      座標の出典 (src) の書き換え検出              ← 2026-07-30 追加
  N17      固定UI (お店一覧/ズーム) が店名を覆わない    ← 2026-07-30 追加
  N18-N19  こどもの声バッジ / 信号アイコン               ← 2026-07-30 追加
  N20-N24  UI/UX (押しやすさ・文字の大きさ・配置)        ← 2026-07-31 追加

usage:
  python tools/v2-build/gate.py [--url http://127.0.0.1:PORT/index.html] [--json out.json]
  (--url 省略時は index.html を file:// で開く)
"""
import argparse, io, json, math, os, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

ap = argparse.ArgumentParser()
ap.add_argument("--url", default=None)
ap.add_argument("--json", default=None)
ap.add_argument("--target", default=os.path.join(ROOT, "index.html"))
ap.add_argument("--no-browser", action="store_true")
# 2026-08-10: 直している最中の反復が高い。1項目直すたびに端末11通りを回していた。
# --devices で絞れば数十秒で戻ってくる。ただし絞った実行は合格判定を名乗らせない
# (「絞って測った」と明示して exit 2 にする。公開前は必ず全部で回す)。
ap.add_argument("--devices", default=None,
                help="絞って測る。例: 320x568 / 320x568@32 / 390x844@24,320x568")
A = ap.parse_args()


# 2026-07-31: 主役が「通り沿いの二列表示」になり、地図は「地図で見る」の奥へ移った。
# 地図の検査 (N1-N19 / N26 / N35-N39) は地図を開いた状態で測る。開かずに測ると
# 閉じた地図を見て158件出す (実際に起きた)。UI の検査は既定の二列表示で測る。
OPEN_MAP = """async () => {
  const b = document.getElementById('mapbtn');
  if (b && b.getAttribute('aria-expanded') !== 'true') {
    b.click();
    await new Promise(r => setTimeout(r, 700));
  }
  return !!document.getElementById('viewport');
}"""


def _open_map(page):
    """地図表示に切り替える。切り替えられなければ False。"""
    try:
        return bool(page.evaluate(OPEN_MAP))
    except Exception:
        return False


# 地図を開いた画面を測る。地図の面積比だけでなく
#   ・何が地図の上に乗っているか ・見出しと閉じる手段があるか
#   ・画面の中にある店名が縁で切れていないか
# を返す。「比率は通るのに中身が切れている」を捕まえるため。
# N61 方位記号の針が本当に北を向いているか (2026-08-10)
# あみさん「右下のコンパスが全然方角あってない」。実測 92.8度ずれ。
# 「投影を rot_deg 回したぶん戻す」と考えて符号を逆にしていた。正しくは
# 「北へ1m進むと画面がどっちへ動くか」。針の向きは画面から実測し、
# 期待値は GEO の投影式から出す (どちらも人の思い込みを挟まない)。
COMPASS_JS = """() => {
  const n = document.getElementById('compassNeedle');
  const p = (typeof GEO !== 'undefined' && GEO.meta && GEO.meta.proj) ? GEO.meta.proj : null;
  if (!n || !p) return {ok: false, why: !n ? '針が無い' : '投影が無い'};
  const svg = n.ownerSVGElement;
  const m = n.getCTM();
  const pt = (x, y) => { const q = svg.createSVGPoint(); q.x = x; q.y = y; return q.matrixTransform(m); };
  const c = pt(22, 22), tip = pt(22, 5);          // 中心 → 北の先端
  const actual = (Math.atan2(tip.x - c.x, -(tip.y - c.y)) * 180 / Math.PI + 360) % 360;
  // 投影: x = mx*cos+my*sin, y = mx*sin-my*cos。北 = (mx,my)=(0,1)
  const R = p.rot_deg * Math.PI / 180;
  const nx = Math.sin(R), ny = -Math.cos(R);
  const want = (Math.atan2(nx, -ny) * 180 / Math.PI + 360) % 360;
  let d = Math.abs(actual - want); if (d > 180) d = 360 - d;
  return {ok: true, actual: Math.round(actual * 10) / 10, want: Math.round(want * 10) / 10,
          off: Math.round(d * 10) / 10};
}"""
MAP_FRAME_JS = """() => {
  const MAP_PAD = 6;
  const vp = document.getElementById('viewport');
  if (!vp) return {ok:false};
  const v = vp.getBoundingClientRect();
  const R = {vp:[v.x,v.y,v.width,v.height], screen:[innerWidth,innerHeight], occ:[], cut:[]};

  // 地図の矩形に重なって見えている要素を、地図より手前(z)にあるものだけ拾う
  const cands = ['header','#controls','footer.credit','.zoomctl','#srcinfo','#editbar',
                 '.strip-guide','#stripview','.detail-panel','#listpanel',
                 // 2026-08-01: 地図に浮く飾り・説明も対象にする。現在地の断り書きが
                 // 出っぱなしで下のタップを塞いでいたのを見逃していた。
                 '.geo-hint','#geoHint','.map-hint','.map-note','.mapfloat',
                 '.locate-note','#locationStatus','[role="status"]'];
  for (const sel of cands) {
    for (const e of document.querySelectorAll(sel)) {
      const c = getComputedStyle(e);
      if (c.display==='none' || c.visibility==='hidden' || +c.opacity===0) continue;
      const r = e.getBoundingClientRect();
      if (r.width<1 || r.height<1) continue;
      const ox = Math.max(0, Math.min(r.right, v.right) - Math.max(r.x, v.x));
      const oy = Math.max(0, Math.min(r.bottom, v.bottom) - Math.max(r.y, v.y));
      if (ox<=0 || oy<=0) continue;
      // 2026-08-01 精密化。当初は「地図の上に何かが1pxでも乗ったら不合格」にしていたが、
      // それだと Google マップや Uber Eats が普通にやっている「隅に浮く丸ボタン
      // (現在地・拡大縮小)」まで禁止してしまい、実装は全部を下帯に押し込むしかなくなる。
      // ボスが「見切れてる」と言ったのは 横いっぱいの帯が216px乗っていたからで、
      // 隅の44pxの丸ボタンのことではない。
      // 不合格にするのは (a) 横いっぱいに広がる帯 (b) 地図の面積を大きく食うもの。
      const spansWidth = ox >= v.width * 0.60;
      const eatsArea   = (ox*oy) >= (v.width * v.height) * 0.12;
      // 小さくても「ずっと居座って下のタップを塞ぐ」ものは別問題。
      // 2026-08-01: 現在地の断り書き (204x32px・面積3.4%) が地図の左上に出っぱなしで、
      // pointer-events:auto のまま下の店へのタップを塞いでいた。
      // 面積が小さいので (a)(b) では引っかからない。押せるもの (button/a/[role=button]) は
      // 操作なので除く。それ以外の飾り・説明は タップを通す (pointer-events:none) こと。
      const isControl = e.matches('button, a[href], [role="button"], input, select, textarea')
                        || !!e.querySelector('button, a[href], [role="button"], input');
      const blocksTap = !isControl && c.pointerEvents !== 'none';
      if (!spansWidth && !eatsArea && !blocksTap) continue;
      R.occ.push({sel, area: Math.round(ox*oy), rect:[Math.round(r.x),Math.round(r.y),
                  Math.round(r.width),Math.round(r.height)],
                  why: spansWidth ? '横いっぱいの帯'
                       : (eatsArea ? '地図の面積を12%以上食う'
                                   : '出っぱなしで下のタップを塞ぐ'),
                  z:c.zIndex});
    }
  }
  // 地図が本当に見えている縦幅 = viewport から 上下の覆いを引いたもの
  let top = v.y, bot = v.bottom;
  for (const o of R.occ) {
    const [x,y,w,h] = o.rect;
    if (x <= v.x+1 && x+w >= v.right-1) {          // 横いっぱいに覆うものだけ帯として扱う
      if (y <= top+1 && y+h > top) top = y+h;
      if (y+h >= bot-1 && y < bot) bot = y;
    }
  }
  R.band = [Math.round(top), Math.round(bot)];
  R.openRatio = +(Math.max(0, bot-top) / innerHeight).toFixed(3);

  // N52 地図(SVG)が地図の枠を埋めているか。埋めていないと下が空いて
  // 「枠の中で地図が見切れている」ように見える。
  const svg = document.getElementById('map');
  if (svg) {
    const sr = svg.getBoundingClientRect();
    R.svgH = Math.round(sr.height);
    R.frameH = Math.round(Math.max(0, bot - top));
    R.fillRatio = R.frameH > 0 ? +(sr.height / R.frameH).toFixed(3) : 0;
    R.deadPx = Math.max(0, R.frameH - Math.round(sr.height));
  }

  // 見出しと「地図を閉じる/戻る」手段が、地図の帯の外(上か下の固定部)にあるか
  const vis = e => { if(!e) return false; const c=getComputedStyle(e);
    if (c.display==='none'||c.visibility==='hidden'||+c.opacity===0) return false;
    const r=e.getBoundingClientRect();
    return r.width>0 && r.height>0 && r.bottom>0 && r.top<innerHeight; };
  R.heading = [...document.querySelectorAll('h1,h2,[role="heading"],.map-title')]
    .filter(vis).map(e=>e.textContent.trim().slice(0,24));
  const back = [...document.querySelectorAll('button,a[href],[role="button"]')]
    .filter(vis).filter(e => /戻|閉じ|一覧|通り沿い|地図をとじ/.test(
      (e.getAttribute('aria-label')||'') + ' ' + e.textContent));
  R.back = back.map(e => { const r=e.getBoundingClientRect();
    return {t:(e.getAttribute('aria-label')||e.textContent).trim().slice(0,20),
            cy:Math.round(r.top+r.height/2)}; });

  // 画面の中にある店名が、縁で切れていないか / 覆いに隠れていないか
  // 判定の基準は「地図として見えている帯」であって画面ぜんぶではない。
  // 2026-07-31 の最初の版は画面座標 (0..innerHeight) で外れを判定していたため、
  // 帯の外へスクロールして隠れている (= overflow で見えない) ラベルまで
  // 「切れている」と数えて26件の偽陽性を出した。帯にかかるものだけを見る。
  for (const t of document.querySelectorAll('#map text')) {
    const r = t.getBoundingClientRect();
    const s = (t.textContent||'').trim();
    if (!s || r.width<1) continue;
    // 2026-08-08: 文字幅を測るためだけの見えない text (opacity .001) を
    // 「隠れた店名」と数えて偽陽性を出した。目に映らないものは判定しない。
    const cs = getComputedStyle(t);
    if (+cs.opacity <= .05 || cs.visibility === 'hidden') continue;
    if (r.bottom <= top || r.top >= bot) continue;        // 帯に全くかからない = 見えていない
    if (r.right <= v.x || r.x >= v.right) continue;
    let why = null;
    if (r.x < v.x - 0.5) why = '左で切れる';
    else if (r.right > v.right + 0.5) why = '右で切れる';
    else if (r.top < top - 0.5) why = '上の縁で切れる';
    else if (r.bottom > bot + 0.5) why = '下の覆いに隠れる';
    else if (r.x < v.x+MAP_PAD || r.right > v.right-MAP_PAD
             || r.top < top+MAP_PAD || r.bottom > bot-MAP_PAD) why = '縁ぎりぎり';
    if (why) R.cut.push({t:s.slice(0,22), why,
      rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]});
  }
  return R;
}"""

# 同じ側で縦に隣り合うカードの隙間。0pxで接していると1枚の板に見えて押し分けられない。
STRIP_GAP_JS = """() => {
  const by = {west:[], east:[]};
  for (const e of document.querySelectorAll('#strip .strip-row')) {
    if (e.hidden) continue;
    const r = e.getBoundingClientRect();
    if (r.height < 1) continue;
    by[e.dataset.side||'east'].push({top:r.top, bot:r.bottom,
      n:((e.querySelector('.strip-shop-name')||e).textContent||'').trim().slice(0,18)});
  }
  const out = [];
  for (const side of ['west','east']) {
    const a = by[side].sort((x,y)=>x.top-y.top);
    for (let i=1;i<a.length;i++)
      out.push({side, gap:+(a[i].top-a[i-1].bot).toFixed(1), a:a[i-1].n, b:a[i].n});
  }
  out.sort((x,y)=>x.gap-y.gap);
  return {pairs: out.length, tight: out.filter(x=>x.gap < 8).slice(0, 40),
          min: out.length ? out[0].gap : null};
}"""

# 絞り込んだとき、該当が1画面にいくつ見えるか。「11件」と出ているのに
# 画面には1件しか無い状態を捕まえる。
FILTER_VIEW_JS = """async () => {
  const wait = ms => new Promise(r=>setTimeout(r,ms));
  const box = () => { const v=document.getElementById('stripview');
    return v ? v.getBoundingClientRect() : null; };
  const seen = () => { const vb = box(); if(!vb) return {t:0,v:0};
    const rows=[...document.querySelectorAll('#strip .strip-row, #stripfar .strip-row')]
      .filter(r=>!r.hidden);
    let vis=0;
    for (const r of rows){ const b=r.getBoundingClientRect();
      if (b.bottom>vb.top+2 && b.top<vb.bottom-2 && b.height>1) vis++; }
    const sv=document.getElementById('stripview');
    const first=rows.length?rows[0].getBoundingClientRect():null;
    return {t:rows.length, v:vis, scrollTop:Math.round(sv.scrollTop),
            svTop:Math.round(vb.top), svH:Math.round(vb.height),
            firstTop:first?Math.round(first.top):null,
            rowH:first?Math.round(first.height):null,
            helpH:(()=>{const e=document.getElementById('emptyHelp');
              return e&&!e.hidden?Math.round(e.getBoundingClientRect().height):0;})()}; };
  const out = [];
  const vf = document.querySelector('.chip.voice-filter');
  if (vf) { vf.click(); await wait(700);
    const s = seen(); out.push({how:'こどもの声で絞り込み', total:s.t, visible:s.v});
    vf.click(); await wait(500); }
  const chips = [...document.querySelectorAll('.chip')].filter(c=>!c.classList.contains('voice-filter'));
  if (chips.length) { chips[0].click(); await wait(700);
    const s = seen();
    out.push({how:'「'+(chips[0].textContent||'').trim().slice(0,10)+'」で絞り込み',
              total:s.t, visible:s.v, dbg:s});
    chips[0].click(); await wait(500); }
  const q = document.getElementById('q');
  if (q) { q.value='中山'; q.dispatchEvent(new Event('input',{bubbles:true})); await wait(800);
    const s = seen(); out.push({how:'「中山」で検索', total:s.t, visible:s.v, dbg:s});
    q.value=''; q.dispatchEvent(new Event('input',{bubbles:true})); await wait(500);
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await wait(300); }
  return out;
}"""

# 通りの帯の中の飾り (道路名・信号) が、どの絞り込み状態でも重なっていないか。
STRIP_DECOR_JS = """async () => {
  const wait = ms => new Promise(r=>setTimeout(r,ms));
  const scan = how => {
    const els = [...document.querySelectorAll('#strip .strip-road-label, #strip .strip-signal')]
      .filter(e => { const c=getComputedStyle(e);
        if (c.display==='none'||c.visibility==='hidden') return false;
        const r=e.getBoundingClientRect(); return r.width>1 && r.height>1; })
      .map(e => { const r=e.getBoundingClientRect();
        return {t:(e.textContent||'').trim().slice(0,12) || '信号',
                kind:e.classList.contains('strip-signal') ? '信号' : '道路名',
                x:r.x, y:r.y, w:r.width, h:r.height}; });
    const bad = [];
    for (let i=0;i<els.length;i++) for (let j=i+1;j<els.length;j++) {
      const a=els[i], b=els[j];
      const ox=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x);
      const oy=Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y);
      if (ox>0.5 && oy>0.5)
        bad.push({how, a:a.kind+'「'+a.t+'」', b:b.kind+'「'+b.t+'」',
                  ox:+ox.toFixed(0), oy:+oy.toFixed(0)});
    }
    return {how, count:els.length, bad};
  };
  const out = [scan('絞り込みなし')];
  const vf = document.querySelector('.chip.voice-filter');
  if (vf) { vf.click(); await wait(700); out.push(scan('こどもの声で絞り込み'));
            vf.click(); await wait(500); }
  const q = document.getElementById('q');
  if (q) { q.value='ケーキ'; q.dispatchEvent(new Event('input',{bubbles:true}));
           await wait(700); out.push(scan('「ケーキ」で検索'));
           q.value=''; q.dispatchEvent(new Event('input',{bubbles:true}));
           await wait(500);
           document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
           await wait(300); }
  return out;
}"""

# 歩きながら探す人が打ちそうな言葉。店名にその字が無くても引っかかるべき。
SEARCH_WORDS_JS = """async (words) => {
  const wait = ms => new Promise(r=>setTimeout(r,ms));
  const q = document.getElementById('q');
  if (!q) return [];
  const out = [];
  for (const w of words) {
    q.value = w; q.dispatchEvent(new Event('input',{bubbles:true}));
    await wait(420);
    const got = [...document.querySelectorAll('#strip .strip-row, #stripfar .strip-row')]
      .filter(r=>!r.hidden)
      .map(r=>((r.querySelector('.strip-shop-name')||r).textContent||'').trim());
    out.push({w, hits:got.length, names:got.slice(0, 20)});
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await wait(120);
  }
  q.value=''; q.dispatchEvent(new Event('input',{bubbles:true}));
  await wait(400);
  return out;
}"""


OUT = []
def P(*a):
    OUT.append(" ".join(str(x) for x in a))

# 建物が無い敷地 (建物内判定の除外)。公園はポリゴンで別途判定する。
OPEN_SITES = {"たきみち公園", "なかやまとびのこ公園", "中山山の神公園",
              "中山小学校", "中山中学校", "中山ドライブスクール",
              "中山鳥瀧不動尊（目の神様）", "商店街モニュメント",
              # 2026-08-04 ボス指示で追加した屋外の地点 (坂の上の眺め)。建物は無い。
              "中山の坂の上"}

# 歩きながら見るズーム。1m が画面2px = 通り1本が26px で見える倍率。
WALK_PX_PER_M = 2.0
MIN_STAR_PX = 6.0          # これ未満の★は見えない
SETBACK = 2.0              # 道路の帯からこれだけ離れていること

# ---- 2026-07-30 追加 (N11-N15): 概観ズーム側の「見やすさ」 ----
# 歩きズームだけを見ていたため、最初に見える倍率で「通りが読めない / ★が通りより太い /
# ラベルが他店の★を内包する」を取りこぼしていた。バーは上がる方向にのみ変更している。
# 床の決め方 (勘で置かず、他の床から逆算している):
#   ★は 6px 未満だと見えない (MIN_STAR_PX)。★ ≤ 0.60 × 道路幅 を満たすには
#   道路幅 ≥ 10px が必要で、10px では★がちょうど6pxで余裕がない。12px なら★7.2px。
ROAD_FLOOR_PX = 12.0       # バス通りが通りとして読める最小の描画幅
# 2026-08-01 全面改訂。
# 元は STAR_ROAD_MAX = 0.60 (★ ≤ 道路幅の0.60倍) で、道路12px から ★7.2px が決まっていた。
# 理由は「★が通りより太いと通りを覆う」。これが誤りだった。
#   ・実測すると ★7.2px に対して店名は11〜18px。地図の主役である店の印が、文字の半分以下。
#   ・ボスの指摘「星がちっちゃくて見にくい」はここ。
#   ・Google マップも Uber Eats も、ピンは20〜30px あって道路に堂々と重なる。
#     それで位置が狂わないのは「ピンのアンカー点が正確な位置を指す」から。
#     正確さは 印を小さくすることで担保するものではない。アンカーで担保する。
#   ・「通りを覆う」は作り手の美意識であって、利用者の困りごとではない。
#     利用者の困りごとは「見えない・押せる場所が分からない」。
# よって: 下限 (見える大きさ) を主にし、上限は暴走よけの緩い枠にする。
# 「どちら側の店か」は N15 の第1段 (★の中心が帯の外) で引き続き厳密に守る。
# これがボスの受け入れ条件「この店舗はここの向かい側あってるね」の担保。
STAR_MIN_VISIBLE_PX = 14.0 # 既定ズームで★がこれ未満だと、指で押す対象として見えない
STAR_ROAD_MAX = 2.0        # ★の幅 / バス通りの描画幅 の上限 (暴走よけ)
# 「自分の★が明確に最近傍」= 他のどの★より25%以上近い。
# 0.55 (=2倍近い) にすると、人が問題なく読めるラベルまで非表示を強いるので採らない。
# ボスの訴えは「どの星がどの店名か分からない」なので、順序が明確なら足りる。
LABEL_MARGIN_MAX = 0.80
# ★の先端が帯にかすってよい量 (m)。現実が近い店 (中心線から9.2m 等) では
# 可読な大きさの★は必ず縁に触れる。乗っている (中心が内側) は N15 で別に不合格。
# 実測の最大は1.2m。2.0m を上限にして、これ以上悪化したら不合格になるようにする。
# 2026-08-01: ★を見える大きさ(14px以上)にすると、体は帯に重なる。
# Google マップのピンも道路に重なる。重なること自体は利用者の困りごとではない。
# 守るのは「中心がどちら側にあるか」(N15 の第1段)。食い込み量の上限は
# ★が14pxになった分だけ緩める (7.2px→14px で半径が約2倍なので 2.0m→5.0m)。
MAX_STAR_ROAD_BITE = 5.0

# ---- 2026-07-30 追加 (N20-N23): UI/UX ----
# ボス指示「文字の大きさ・位置・ボタンの配置と押しやすさを、位置関係を変えずに」。
# 実測 (2026-07-30) の出発点:
#   押しやすさ: chip44 / 検索44 / お店一覧44 / ズーム44x44 / 閉じる44x44 / 一覧の行60 → 合格
#   文字      : カテゴリ名12.5 / お店一覧13.6 / 検索結果12.5 / 見出し下12.0 / フッタ10.9 → 不足
#   カテゴリ  : 6個中2個しか見えない (必要875px vs 画面360-428px)。
#              しかも「こどもの声（11店）」が最後尾で常に画面外
TAP_MIN_PX = 44.0          # WCAG 2.5.5 / Apple HIG。操作要素の最小
TEXT_MIN_PX = 14.0         # 高齢者も読める床
ATTRIB_MIN_PX = 12.0       # 帰属表示 (OpenStreetMap ODbL 等) だけはこの床
# 地図の大きさの床。当初 0.62 (比率のみ) にしたが、背の低い実機を試さずに置いた値だった。
# 実測 (2026-07-31): 360x640 では上下UIが295px = 画面の46%を占める。
#   header 38 + カテゴリ2段 101 + 検索 50 + フッタ 106 = 295px
# 62%を満たすには余白を243pxまで削る必要があり、チップを44px未満にしないと届かない
# (= N20 の押しやすさを壊す)。44pxの操作要素と帰属表示(ODbL)の表示を保ったまま
# 62%は達成不能なので、比率を下げるかわりに絶対値の床を併せて置いて歯止めにする。
MAP_MIN_RATIO = 0.52       # 画面の高さに対する地図の最小比率
MAP_MIN_PX = 330.0         # 地図の最小の高さ (実測 360x640 で345px)
# UI検査を回す実機サイズ。幅だけ変えて高さを844固定にしていたため、
# 360x640 (よくある小型Android) の実際の高さを一度も測っていなかった
# (2026-07-31 発覚: そこでは上下UIが295pxを占め地図が53.9%しかない)。
# 2026-08-10: いちばん狭い 320x568 が総なめに入っていなかった。
# 手順書は「320px幅で必ず検証する」と言っているのに、N20-N35/N43-N49/N57/N58 は
# 360px からしか見ていない。実際、320px で「地図で見 / る」と「（11店 / ）」が
# 割れているのに gate は PASS していた (目で見つけた)。
UI_DEVICES = [(320, 568), (360, 640), (375, 667), (390, 844), (428, 926)]
# 端末を寝かせた状態。文字の大きさと押しやすさは向きに関係なく成り立つべきなので
# N20/N21 はここでも見る。一方 N23 (地図の大きさ) は横向きだと前提が変わるので
# 縦向きだけで判定する — 横向きは「地図が主」でなく「一覧が主」の使い方になる。
UI_LANDSCAPE = [(640, 360), (844, 390)]
# 2026-08-10: 端末の「文字の大きさ」を一度も変えて見ていなかった。あみさんの
# 「スマホで拡大すると文字が大変」は、Android の文字設定 200% (16px→32px) で
# header が中身を刈り込んでいたもの。ブラウザのピンチ拡大と地図の＋は無傷だった。
# 全端末 x 全文字サイズは時間の割に増えないので、いちばん狭い端末と代表機だけを
# 24px (150%) と 32px (200%) で総なめする。ここは総なめ (N20-N35/N43-N49/N57-N59)
# だけを回し、16px 前提で較正した寸法の検査は縦横の既定サイズに任せる。
UI_FONT_ROWS = [(320, 568, 24), (320, 568, 32), (390, 844, 24), (390, 844, 32)]
# 総なめが集める箱の名前。1か所で持つ — 2026-08-09 の N57 と 08-10 の N58 は
# どちらも「判定は正しいのに、この並びへ足し忘れて戻り値を捨てていた」ため
# 何も捕まえずに PASS していた。増やす時はここだけ直せば全経路に届く。
SWEEP_KEYS = ("texts", "taps", "wrap", "clip", "contrast", "gaps", "emoji", "lone", "orphan", "cutbox", "rank")

# ---- 2026-07-31 追加 (N45-N50) ----
# ここまでの N1-N44 は「数えられるもの」だけを見ていた。地図を開いた画面を一度も
# 撮らずに通していたため、ボスに「マップの方見切れてない?」と言われるまで
#   ・地図に見出しが無い ・上下左右で店名が切れる ・帰属表示が地図に重なる
#   ・カード同士が0pxで接している ・絞り込み11件で1件しか見えない
# を全部素通りさせた。以下は「絵を見て分かること」を数字に落としたもの。
MAP_OCCLUDE_MAX_PX = 0.0    # 地図の上に他のUIが乗ってよい面積 (乗ってはいけない)
MAP_EDGE_PAD_PX = 6.0       # 画面の縁と店名の間に要る余白
MAP_OPEN_MIN_RATIO = 0.78   # 地図を開いたら画面の78%以上が地図
STRIP_GAP_MIN_PX = 8.0      # 二列のカード同士の縦の隙間 (押し間違い防止)
FILTER_VISIBLE_MIN = 6      # 絞り込んだとき1画面に見えるべき該当件数 (該当が少なければ全部)
# 語が「何かに当たればOK」では、全部に当てる実装で通ってしまう。
# 当たるべき店を名指しで書き、その店が結果に入っていることまで見る。
SEARCH_WORDS = [
    ("パン",   "BAKERY&BAKE EndRoll"),
    ("ケーキ", "Cake NAO"),
    ("歯医者", "歯科"),
    ("床屋",   "とこや"),
    ("薬",     "ウエルシア仙台中山店"),
    ("花",     "フラワー中山"),
    ("銀行",   "七十七銀行中山支店"),
    ("郵便",   "中山郵便局"),
    ("病院",   "クリニック"),
    # 「カフェ」の正解に "cafe" を置いていたが、60店に cafe も喫茶も無い。
    # 存在しない文字列を正解にしていた検査側の誤り (2026-07-31 訂正)。
    # 座って飲食できる先を探して打つ言葉なので、食べる・飲む の店に当たれば正しい。
    ("カフェ", "Cake NAO"),
]
SEARCH_HITS_MAX = 14       # 1語で14件超が返るなら絞れていない (全部に当てる実装よけ)

# N51 (2026-08-01 追加)。gate が PASS になった状態の絵を見たら、絞り込み中の
# 通りの帯の中で 道路名「中山バス通り」が何重にも重なって読めない字の塊になっていた。
# 詰めモードで帯が縮んでも、道路名と信号は元の間隔のまま置かれていたため。
# N29 は「入れ物からのはみ出し」、N44 は「押せるもの同士の重なり」しか見ておらず、
# 押せない飾りどうしの重なりを見る項目が無かった。
STRIP_DECOR_OVERLAP_MAX = 0    # 通りの中の道路名・信号どうしが重なってはいけない

# N52 (2026-08-01)。ボス指摘「なんで枠内というか地図が見切れてるんだろう」。
# 実測すると 390x844 で 地図の枠は744px あるのに 地図(SVG)は594px しかなく、
# 下に150pxの空白があった。SVG が width:100% / height:auto で、
# viewBox の縦横比(424:646)がそのまま高さを決めていたため、枠を埋めていない。
# 利用者から見れば「地図が枠の中で上に寄っていて、下がスカスカ」= 見切れて見える。
MAP_FILL_MIN_RATIO = 0.98      # 地図(SVG)は 地図の枠の高さの98%以上を埋めること
# 横向きの地図の床。実測 (2026-07-31) では 640x360 で地図が57px・844x390 で51px しかなく、
# 上下のUIが画面の87%を占めていた。この状態では地図として使えない。
# 横向きは横に余裕があるので、カテゴリと検索を横の列へ逃がせば縦は
#   ヘッダ38 + フッタ約100 = 138px で済み、640x360 なら地図222px (62%) が取れる計算。
# 余裕を見て 200px / 45% を床に置く。達成不能だと分かったら、縦向きの 0.62→0.52 と
# 同じように「なぜ届かないか」を書いたうえで下げる。勘で下げない。
LAND_MAP_MIN_PX = 200.0
LAND_MAP_MIN_RATIO = 0.45
# ラベル配置の所要時間の上限。2026-07-31 の Task R で、こどもの声の店を同時に解く
# 「打ち切りの無い再帰探索」が入った。いまの条件では12手で終わるが、店やバッジが増えて
# 制約が厳しくなると組み合わせ爆発する。地図が固まるのは最悪の壊れ方 (店名が消えるより悪い)
# なので、賢さでなく時間で歯止めをかける。ズーム操作1回あたりの最悪値で測る。
MAX_LAYOUT_MS = 400.0
# ---- 2026-07-31 追加 (N30-N34): UI/UX 規約 (skill ui-ux-pro-max) の実測 ----
# 規約を読むだけでは何も変わらないので、当てて測る。当てた結果は採点表に残す。
CONTRAST_MIN = 4.5         # WCAG 1.4.3。大きい文字 (24px以上 or 18.66px以上の太字) は3.0
CONTRAST_MIN_LARGE = 3.0
TAP_GAP_MIN_PX = 8.0       # 隣り合う操作要素の最小の間隔。近すぎると押し間違える
# ---- 2026-07-31 追加 (N35-N36): ボス指摘「見にくい・操作しにくい」の実測 ----
# 採点表は規約適合を測っていたが、体感の見やすさ・操作性は測れていなかった。
# 実測 (390x844): 画面に見える店名59件のうち40件が12px。UIの床は14pxなので
# 地図の文字だけが小さい。文字を14/17pxにしても失うラベルは2件だけ (59→57)。
MAP_LABEL_MIN_PX = 14.0
# 地図なのにピンチで拡大できず、ページ全体が5倍になる (実測)。
# 歩きながら片手で使うので、指で拡大できないのは致命的。
ZOOM_GESTURES = ("ピンチ", "ダブルタップ", "ホイール")
# 引き出し線の長さの上限。実測 (2026-07-31) では最長224px = 画面幅の62%で、
# 地図を横切る「配線」になり かえって読みにくかった。線は「少しずらした」ことが
# 分かる長さに留め、そこに届かない店は名前を出さない (拡大すれば出る)。
# こどもの声の店は看板機能で必ず名前が要る (N26) ので、少しだけ長い線を許す。
LEADER_MAX_PX = 90.0
LEADER_MAX_PX_VOICE = 130.0

# ---------------- GEO ----------------
src = io.open(A.target, encoding="utf-8").read()
G = json.loads(re.search(r"const GEO = (\{.*?\});\s*\n", src, re.S).group(1).replace("<\\/", "</"))
shops, roads, signals, parks = G["shops"], G["roads"], G["signals"], G["parks"]
meta = G["meta"]
SPINE = G["busway"][1]
_m = re.search(r"const STRIP_GAP_FLOOR\s*=\s*([\d.]+)", src)
STRIP_GAP = float(_m.group(1)) if _m else 8.0

# 描画幅を生成物から読む (固定値を置かない)
FILLW = {}
for m in re.finditer(r"class:'(road-[a-z-]+)-f', 'stroke-width':([\d.]+)", src):
    FILLW[m.group(1)] = float(m.group(2))
SPINE_W = FILLW.get("road-main", 13.0)
CLSMAP = {"minor": "road-minor", "mid": "road-mid", "major": "road-major",
          "service": "road-service", "path": "road-path"}


def road_w(r):
    if r.get("guide_spine"):
        return SPINE_W
    return FILLW.get(CLSMAP.get(r["cls"], "road-mid"), 9.0)


def seg_d(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def road_d(px, py, r):
    return min(seg_d(px, py, a[0], a[1], b[0], b[1]) for a, b in zip(r["pts"], r["pts"][1:]))


# 2026-08-10: 「向かい合わせのズレ」は、同じ側にカードが積み上がる所では
# どう並べても消せない。指の基準44px + 隙間 の積み上げが実際の間隔より広くなるため。
# 引き出し線を消した以上「線があるから免除」は使えないので、代わりに
# 「幾何が強いる最良の詰め方」を gate 側で組み直し、それより悪い時だけ落とす。
# 最良 = 順序を保ったまま理想位置との差を最小にする詰め方 (PAVA / 隣接違反プーリング)。
# アプリ側 stripPackColumn と同じ手を、実測した高さで独立に組み直している。
def _best_centers(col, gap):
    """col = [{'ideal':理想中心px, 'h':実測高さpx}, ...] を理想の順に。戻り = 最良中心"""
    if not col:
        return []
    cum = [0.0]
    for i in range(1, len(col)):
        cum.append(cum[i-1] + (col[i-1]["h"] + col[i]["h"]) / 2.0 + gap)
    blocks = []
    for i, it in enumerate(col):
        v = it["ideal"] - cum[i]
        blocks.append({"s": i, "e": i, "total": v, "n": 1, "v": v})
        while len(blocks) > 1 and blocks[-2]["v"] > blocks[-1]["v"]:
            b = blocks.pop(); a = blocks.pop()
            m = {"s": a["s"], "e": b["e"], "total": a["total"] + b["total"], "n": a["n"] + b["n"]}
            m["v"] = m["total"] / m["n"]
            blocks.append(m)
    out = [0.0] * len(col)
    for bl in blocks:
        for i in range(bl["s"], bl["e"] + 1):
            out[i] = bl["v"] + cum[i]
    return out


def spine_x(y):
    best = None
    for (x1, y1), (x2, y2) in zip(SPINE, SPINE[1:]):
        lo, hi = min(y1, y2), max(y1, y2)
        if lo <= y <= hi:
            t = 0.0 if abs(y2 - y1) < 1e-9 else (y - y1) / (y2 - y1)
            return x1 + t * (x2 - x1)
        d = min(abs(y - lo), abs(y - hi))
        if best is None or d < best[0]:
            best = (d, x1 if abs(y - y1) < abs(y - y2) else x2)
    return best[1]


def TX(s): return s.get("tx", s["x"])
def TY(s): return s.get("ty", s["y"])
def side(x, y): return 1 if x >= spine_x(y) else -1


def poly_inside(pl, x, y):
    c = False
    n = len(pl)
    for i in range(n):
        x1, y1 = pl[i]; x2, y2 = pl[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
                c = not c
    return c


# ---------------- 建物ポリゴン ----------------
BLD = []
bpath = os.path.join(HERE, "buildings_raw.json")
if os.path.exists(bpath):
    p = meta["proj"]
    R = math.radians(p["rot_deg"]); CA, SA = math.cos(R), math.sin(R)
    mnx, mny = meta["minx"], meta["miny"]

    def proj(lat, lng):
        mx = (lng - p["lon0"]) * p["cosf"] * 111320.0
        my = (lat - p["lat0"]) * 111320.0
        return mx * CA + my * SA - mnx, mx * SA - my * CA - mny

    W, H = meta["W"], meta["H"]
    for e in json.load(io.open(bpath, encoding="utf-8"))["elements"]:
        g = e.get("geometry")
        if not g:
            continue
        pts = [proj(q["lat"], q["lon"]) for q in g if q.get("lat") is not None]
        if len(pts) < 3:
            continue
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        if max(xs) < -60 or min(xs) > W + 60 or max(ys) < -60 or min(ys) > H + 60:
            continue
        BLD.append((min(xs), min(ys), max(xs), max(ys), pts))


def in_building(x, y):
    for x0, y0, x1, y1, pts in BLD:
        if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1 and poly_inside(pts, x, y):
            return True
    return False


# ---------------- 交差点 ----------------
def _ix(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -0.001 <= t <= 1.001 and -0.001 <= u <= 1.001:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


NODES = []
for i in range(len(roads)):
    si = list(zip(roads[i]["pts"], roads[i]["pts"][1:]))
    for j in range(i + 1, len(roads)):
        for a, b in si:
            for c, e in zip(roads[j]["pts"], roads[j]["pts"][1:]):
                q = _ix(a, b, c, e)
                if q:
                    NODES.append(q)
XN = []
for q in NODES:
    if not any(math.hypot(q[0] - r[0], q[1] - r[1]) < 12 for r in XN):
        XN.append(q)

SIG_OK = []       # 交差点に立っている信号 (waypointとして使える)
for sx, sy in signals:
    d = min((math.hypot(sx - q[0], sy - q[1]) for q in XN), default=1e9)
    SIG_OK.append(d <= 20)

# ---------------- ブラウザ側の実測 ----------------
REND = None
if not A.no_browser:
    url = A.url
    srv = None
    if not url:
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 2026-08-10: 静的検査は --target を読むのに、ブラウザ検査は常に
        # /index.html を測っていた。別ファイルを指定すると「静的は指定ファイル・
        # 実測は別ファイル」という食い違いが起き、指定側の欠陥を見逃す。
        _t = os.path.abspath(A.target)
        if os.path.dirname(_t) != os.path.abspath(ROOT):
            sys.exit("!! --target はリポジトリ直下のファイルを指定すること "
                     "(ブラウザ検査が同じファイルを測れない): %s" % A.target)
        url = "http://127.0.0.1:%d/%s" % (port, os.path.basename(_t))
        ok = False
        for _ in range(30):
            try:
                import urllib.request
                urllib.request.urlopen(url, timeout=1).read(1)
                ok = True; break
            except Exception:
                time.sleep(1)
        if not ok:
            srv.terminate(); srv = None; url = None
    if url:
        try:
            from playwright.sync_api import sync_playwright
            JS = """(walkPxPerM) => {
              const svg = document.getElementById('map');
              const s0 = Math.hypot(svg.getScreenCTM().a, svg.getScreenCTM().b);
              // 道路の実描画幅 (px)。通りとして読めるかを見るため
              const roadPx = {};
              for (const c of ['main','major','mid','minor']) {
                const el = document.querySelector('.road-' + c + '-f');
                if (el) roadPx[c] = +(parseFloat(getComputedStyle(el).strokeWidth) * s0).toFixed(2);
              }
              const rows = [...document.querySelectorAll('g.hit')].map(h => {
                const i = +h.dataset.i, s = GEO.shops[i];
                const st = h.querySelector('.star'), t = h.querySelector('text.shoplabel');
                const bb = st ? st.getBBox() : null;
                const m  = st ? st.getScreenCTM() : null;
                const sc = m ? Math.hypot(m.a, m.b) : 0;
                const tb = t ? t.getBBox() : null;
                const sr = st ? st.getBoundingClientRect() : null;
                const shown = !!(t && getComputedStyle(t).display !== 'none' && +getComputedStyle(t).opacity > 0);
                const tr = (shown && t) ? t.getBoundingClientRect() : null;
                return {i, name: s.name,
                        starPxNow:  bb ? +(bb.width * sc).toFixed(2) : 0,
                        starMapM:   bb && sc ? +(bb.width * sc / s0).toFixed(2) : 0,
                        labelShown: shown,
                        lx: s.lx, ly: s.ly,
                        starCx: sr ? +(sr.left + sr.width / 2).toFixed(1) : null,
                        starCy: sr ? +(sr.top + sr.height / 2).toFixed(1) : null,
                        labelRect: (tr && tr.width > 1)
                                   ? [+tr.left.toFixed(1), +tr.top.toFixed(1),
                                      +tr.right.toFixed(1), +tr.bottom.toFixed(1)] : null,
                        labelMapW: tb ? +tb.width.toFixed(1) : 0,
                        // 引き出し線で結ばれているラベルか (N14 の除外 / N37 の対象)
                        leader: !!(GEO.shops[i] && GEO.shops[i].labelLeader),
                        voice: !!(GEO.shops[i] && (GEO.shops[i].voices||[]).length),
                        // N39 ★が表示域の中にいるのに、名前が縁で切れていないか。
                        // 画面外の店の名前が見えないのは当たり前なので対象外。
                        starInView: (() => { if (!sr) return false;
                          const v = document.getElementById('viewport').getBoundingClientRect();
                          const cx = sr.left + sr.width/2, cy = sr.top + sr.height/2;
                          return cx >= v.left && cx <= v.right && cy >= v.top && cy <= v.bottom; })(),
                        labelCutPx: (() => { if (!tr || tr.width <= 1) return 0;
                          const v = document.getElementById('viewport').getBoundingClientRect();
                          return Math.round(Math.max(0, v.left - tr.left,
                                                     tr.right - v.right)); })(),
                        // 印が付いているだけで線が描かれていないと、
                        // 「どの★がどの店名か分からない」状態のまま N14/N4 を素通りする。
                        // 自分の★の近くから始まって自分のラベルで終わる線が
                        // 実際に見えているかを、ここで確かめる。
                        leaderDrawn: (() => {
                          if (!(GEO.shops[i] && GEO.shops[i].labelLeader)) return null;
                          if (!sr || !tr || tr.width <= 1) return false;
                          const scx = sr.left + sr.width/2, scy = sr.top + sr.height/2;
                          const paths = document.querySelectorAll(
                            '#map path.label-leader, #map .label-leader, #map path.faraway');
                          for (const q of paths) {
                            const cs = getComputedStyle(q);
                            if (cs.display === 'none' || cs.visibility === 'hidden'
                                || parseFloat(cs.opacity) <= .05) continue;
                            const b = q.getBoundingClientRect();
                            if (b.width < .5 && b.height < .5) continue;
                            // 線の外接矩形が ★ と ラベル の両方に触れていること
                            const near = (r2, x, y, pad) =>
                              x >= r2.left-pad && x <= r2.right+pad
                              && y >= r2.top-pad && y <= r2.bottom+pad;
                            const touchesStar = near(b, scx, scy, 6);
                            const touchesLabel =
                              Math.min(b.right, tr.right) - Math.max(b.left, tr.left) > -6 &&
                              Math.min(b.bottom, tr.bottom) - Math.max(b.top, tr.top) > -6;
                            if (touchesStar && touchesLabel) return true;
                          }
                          return false;
                        })()};
              });
              // ラベルbbox交差
              const vis = [...document.querySelectorAll('text.shoplabel')].filter(t =>
                getComputedStyle(t).display !== 'none' && t.getBoundingClientRect().width > 1);
              let cross = 0;
              const bx = vis.map(t => t.getBoundingClientRect());
              for (let i=0;i<bx.length;i++) for (let j=i+1;j<bx.length;j++){
                const ox = Math.min(bx[i].right,bx[j].right)-Math.max(bx[i].left,bx[j].left);
                const oy = Math.min(bx[i].bottom,bx[j].bottom)-Math.max(bx[i].top,bx[j].top);
                if (ox>0.5 && oy>0.5) cross++;
              }
              // 固定UI (position:fixed) が可視ラベルを覆っていないか。
              // 表示域の外に出ているぶんはクリップされて見えないだけなので除く
              // (パン可能な地図では端で切れるのは正常)。
              const vpr = document.getElementById('viewport').getBoundingClientRect();
              const fx = ['#listbtn', '.zoomctl', '#editbar', '#srcinfo']
                .map(q => document.querySelector(q))
                .filter(e => e && getComputedStyle(e).position === 'fixed'
                               && getComputedStyle(e).display !== 'none')
                .map(e => e.getBoundingClientRect());
              const covered = [];
              for (const t of document.querySelectorAll('text.shoplabel')) {
                if (getComputedStyle(t).display === 'none') continue;
                const b = t.getBoundingClientRect();
                if (b.width < 1) continue;
                const l = Math.max(b.left, vpr.left),  r2 = Math.min(b.right, vpr.right);
                const tp = Math.max(b.top, vpr.top),   bo = Math.min(b.bottom, vpr.bottom);
                if (r2 <= l || bo <= tp) continue;
                for (const f of fx) {
                  const ox = Math.min(r2, f.right) - Math.max(l, f.left);
                  const oy = Math.min(bo, f.bottom) - Math.max(tp, f.top);
                  if (ox > 1 && oy > 1)
                    covered.push({name: t.textContent.trim(),
                                  pct: Math.round(100 * ox * oy / ((r2 - l) * (bo - tp)))});
                }
              }
              // こどもの声バッジ / 信号アイコン。★と同じく「地図単位固定で大きすぎる」
              // 問題を持ちうるのに見ていなかった (2026-07-30 9周目で発覚)。
              const starList = [...document.querySelectorAll('g.hit')].map(h => {
                const st = h.querySelector('.star');
                if (!st) return null;
                const b = st.getBoundingClientRect();
                // 大きさ0 = 出ていない印。中心が (0,0) になり、押した所の判定が壊れる
                if (!(b.width > 0)) return null;
                return {n: GEO.shops[+h.dataset.i].name,
                        cx: b.left + b.width / 2, cy: b.top + b.height / 2, b: b};
              }).filter(Boolean);
              const badges = [...document.querySelectorAll('g.voice-badge')].map(g => {
                const b = g.getBoundingClientRect();
                const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
                const own = g.closest('g.hit');
                const on = own ? GEO.shops[+own.dataset.i].name : null;
                let bn = null, bd = 1e9, od = -1;
                for (const s of starList) {
                  const d = Math.hypot(s.cx - cx, s.cy - cy);
                  if (d < bd) { bd = d; bn = s.n; }
                  if (s.n === on) od = d;
                }
                return {own: on, nearest: bn, nearestPx: +bd.toFixed(1),
                        ownPx: +od.toFixed(1), wPx: +b.width.toFixed(1)};
              });
              const ovl = (a, b) => (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1)
                                 && (Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1);
              const sigBoxes = [...svg.querySelectorAll('rect')]
                .filter(r => r.getAttribute('rx') === '5.5' && r.getAttribute('width') === '22')
                .map(r => r.parentNode.getBoundingClientRect());
              const sigHit = [];
              for (const g of sigBoxes) {
                for (const s of starList) if (ovl(g, s.b)) sigHit.push({n: s.n, kind: '★'});
                for (const t of vis) if (ovl(g, t.getBoundingClientRect()))
                  sigHit.push({n: t.textContent.trim(), kind: 'ラベル'});
              }
              // N54 店名と印の位置関係。2026-08-09 ボス「特に店名と文字とアイコンの
              // 位置関係ね。それ毎回言われるのウザいし俺の責任になるから」。
              // 規則は実装の定数から取る (検査側で書き直すと必ずズレる)。
              //   横 = 印の中心から starTargetPx/2 + LABEL_GAP_PX、
              //        道に乗る時だけ +LABEL_FAR_COLUMN_PX の2列目
              //   縦 = 印と同じ高さ、埋まっている時だけ LABEL_ROW_STEP_PX 単位で1行上下
              // 距離の但し書き (.distance-label) は店名の2行目なので対象外。
              let slotBad = null, slotErr = null, slotChecked = 0;
              try {
                const gapOK = [starTargetPx()/2 + LABEL_GAP_PX];
                gapOK.push(gapOK[0] + LABEL_FAR_COLUMN_PX);
                // 斜めは廃止。名前は印の真横 (縦のずれ0) か 真下・真上 のみ。
                const dyOK = [0];
                // 斜めに置いた名前は「その名前の真上・真下に他店の印が無い」時だけ認める。
                // 2026-08-09 ボス指摘の正体 = 名前の下に別の店の印が来て、
                // どちらの店の名前か分からなくなっていたこと。
                const starPts = [];
                document.querySelectorAll('g.hit').forEach(hh => {
                  const ss = hh.querySelector('.star'); if (!ss) return;
                  const bb = ss.getBoundingClientRect(); if (!(bb.width > 0)) return;
                  starPts.push({i:+hh.dataset.i, x:bb.left+bb.width/2, y:bb.top+bb.height/2});
                });
                const columnClear = (i, r, reach) => !starPts.some(pt =>
                  pt.i !== i && pt.x >= r.left-2 && pt.x <= r.right+2 &&
                  pt.y > r.top-reach && pt.y < r.bottom+reach);
                slotBad = [];
                for (const t of document.querySelectorAll('text.shoplabel[data-main-label]')){
                  if (getComputedStyle(t).display === 'none') continue;
                  if (t.classList.contains('distance-label')) continue;
                  const r = t.getBoundingClientRect(); if (!(r.width > 1)) continue;
                  const h = t.closest('g.hit'); if (!h) continue;
                  const st = h.querySelector('.star'); if (!st) continue;
                  const sb = st.getBoundingClientRect(); if (!(sb.width > 0)) continue;
                  const cx = sb.left + sb.width/2, cy = sb.top + sb.height/2;
                  const nm = GEO.shops[+h.dataset.i].name;
                  const gap = (r.left + r.width/2 >= cx) ? r.left - cx : cx - r.right;
                  const dy = (r.top + r.height/2) - cy;
                  slotChecked++;
                  const sideways = (r.left > cx+1) || (r.right < cx-1);
                  if (!sideways){
                    // 真下・真上に置いた名前。横は印の中心にそろっていること
                    const off = Math.abs((r.left+r.right)/2 - cx);
                    if (off > 3.0)
                      slotBad.push(nm + ' 縦置きなのに横へ' + off.toFixed(1) + 'px');
                    continue;
                  }
                  const gd = Math.min(...gapOK.map(g => Math.abs(gap-g)));
                  const dd = Math.min(...dyOK.map(d => Math.abs(dy-d)));
                  if (gd > 2.0) slotBad.push(nm + ' 横' + gap.toFixed(1) + 'px');
                  else if (dd > 3.0) slotBad.push(nm + ' 縦' + dy.toFixed(1) + 'px');

                }
              } catch (e) { slotErr = String((e && e.message) || e); }
              // 印を押した時に その店が開くか。2026-08-08 に押し分けの判定を
              // nearby() (実座標で20m以内なら必ず選択窓) から
              // shopsByTapDistance() (押した所からの画面距離) へ変えた。
              // gate は nearby を呼び続けていて、例外を握り潰していたため
              // N24 が黙って対象0件になっていた。握り潰しは二度とやらない —
              // 測れなかった時は null ではなく理由を返し、Python 側で不合格にする。
              let tapSelf = null, tapErr = null;
              try {
                if (typeof shopsByTapDistance !== 'function')
                  throw new Error('shopsByTapDistance が無い');
                if (typeof starTargetPx !== 'function')
                  throw new Error('starTargetPx が無い');
                const ownR = starTargetPx() / 2;
                tapSelf = [];
                for (const s of starList) {
                  const ranked = shopsByTapDistance(s.cx, s.cy);
                  if (!ranked.length) { tapSelf.push({n: s.n, got: '(候補なし)'}); continue; }
                  if (ranked[0].d > ownR) { tapSelf.push({n: s.n, got: '選択窓'}); continue; }
                  if (ranked[0].shop.name !== s.n)
                    tapSelf.push({n: s.n, got: ranked[0].shop.name});
                }
              } catch (e) { tapErr = String((e && e.message) || e); }
              return {pxPerMeter:+s0.toFixed(4), rows, roadPx, labelCross:cross,
                      labelsVisible:vis.length, uiCovered:covered,
                      tapSelf, tapErr, tapChecked: starList.length,
                      slotBad, slotErr, slotChecked,
                      badges, sigW: sigBoxes.length ? +sigBoxes[0].width.toFixed(1) : 0,
                      sigCount: sigBoxes.length, sigHit, jsErrors:0,
                      // 2026-08-07: 「置けるはず」の判定を検査側でもう一度作ると、
                      // 本体の置き場ルールと必ずズレる (実際 フラワー中山 で食い違った)。
                      // 本体が「どの候補をなぜ捨てたか」を残しているので、それを読む。
                      labelReject: JSON.parse(JSON.stringify(window.__labelPriorityReject || {}))};
            }"""
            with sync_playwright() as pw:
                br = pw.chromium.launch()
                pg = br.new_page(viewport={"width": 390, "height": 844})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(url, wait_until="load")
                pg.wait_for_timeout(400)
                _open_map(pg)
                pg.wait_for_timeout(1500)
                REND = pg.evaluate(JS, WALK_PX_PER_M)
                REND["jsErrors"] = len(errs)
                # 歩きズーム: viewBox幅から逆算すると初期倍率の影響でずれるので、
                # 実DOM倍率を測りながら WALK_PX_PER_M に収束させる (Codex指摘のバグ修正)
                w = 390 / WALK_PX_PER_M
                for _ in range(6):
                    pg.evaluate("v=>document.getElementById('map').setAttribute('viewBox',v)",
                                "%f %f %f %f" % (400, 700, w, w * 844 / 390))
                    pg.wait_for_timeout(300)
                    got = pg.evaluate("""() => { const s=document.getElementById('map').getScreenCTM();
                                                return Math.hypot(s.a,s.b); }""")
                    if abs(got - WALK_PX_PER_M) / WALK_PX_PER_M < 0.02:
                        break
                    w = w * got / WALK_PX_PER_M
                REND["walk"] = pg.evaluate(JS, WALK_PX_PER_M)
                REND["walkPxPerMeter"] = round(got, 4)

                # ---- N55 引いた時も印が重ならないか ----
                # 印は指で押せるよう画面14px固定なので、引くと地図の上では大きくなり
                # (0.35px/m で 14px = 40m)、8.5m しか離れていない店は必ず重なる。
                # 重なる印は「この辺に◯店」の丸にまとめて解いている。
                # 数え落としが無いこと (丸の中の数 + 単独の印 = 全店) も一緒に見る。
                CLUSTERJS = r"""() => {
                  const vp = document.getElementById('viewport').getBoundingClientRect();
                  const inVp = r => r.left>=vp.left-.5 && r.right<=vp.right+.5
                                 && r.top>=vp.top-.5 && r.bottom<=vp.bottom+.5;
                  const marks = [];
                  document.querySelectorAll('g.hit').forEach(h => {
                    const st = h.querySelector('.star'); if (!st) return;
                    const b = st.getBoundingClientRect(); if (!(b.width > 0)) return;
                    marks.push({n: GEO.shops[+h.dataset.i].name, b, inv: inVp(b)});
                  });
                  const over = [];
                  const vis = marks.filter(m => m.inv);
                  for (let i=0;i<vis.length;i++) for (let j=i+1;j<vis.length;j++){
                    const a=vis[i].b, b=vis[j].b;
                    if (Math.min(a.right,b.right)-Math.max(a.left,b.left) > .5 &&
                        Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top) > .5)
                      over.push(vis[i].n + '×' + vis[j].n);
                  }
                  const cl = [...document.querySelectorAll('g.cluster')].map(g => {
                    const b = g.getBoundingClientRect();
                    const t = g.querySelector('text');
                    return {n: +(t ? t.textContent : 0), w:+b.width.toFixed(1),
                            h:+b.height.toFixed(1), label:g.getAttribute('aria-label')||''};
                  });
                  const svgEl = document.getElementById('map');
                  const m = svgEl.getScreenCTM();
                  return {scale:+Math.hypot(m.a,m.b).toFixed(3), over,
                          marks: marks.length, clusters: cl,
                          covered: marks.length + cl.reduce((a,c)=>a+c.n,0),
                          total: GEO.shops.length};
                }"""
                pg.evaluate("""async () => {
                  for (let i=0;i<18;i++){
                    const b=document.getElementById('zout');
                    if (!b || b.disabled) break;
                    b.click(); await new Promise(r=>setTimeout(r,140));
                  }}""")
                pg.wait_for_timeout(700)
                REND["zoomout"] = pg.evaluate(CLUSTERJS)

                # ---- UI/UX の実測 (N20-N24)。画面幅を変えて操作部だけ見る ----
                UIJS = """() => {
                  const out = {vw: innerWidth, taps: [], texts: [], offscreen: []};
                  const SEL = [['.chip','カテゴリ'], ['#q','検索入力'], ['#listbtn','お店一覧'],
                               ['.zoomctl button','ズーム'], ['#detailClose','詳細を閉じる'],
                               ['.chooser .copt','チューザーの選択肢'], ['#listrows > *','一覧の行']];
                  const shown = e => {
                    const cs = getComputedStyle(e);
                    return cs.display !== 'none' && cs.visibility !== 'hidden'
                           && parseFloat(cs.opacity) > 0.05;
                  };
                  for (const [q, nm] of SEL) {
                    document.querySelectorAll(q).forEach((e, i) => {
                      if (!shown(e)) return;
                      const b = e.getBoundingClientRect();
                      if (b.width < 1 && b.height < 1) return;
                      const cs = getComputedStyle(e);
                      out.taps.push({nm: nm + (i ? '#' + i : ''), w: +b.width.toFixed(0),
                                     h: +b.height.toFixed(0),
                                     fs: +parseFloat(cs.fontSize).toFixed(1),
                                     txt: (e.textContent || '').trim().slice(0, 12)});
                      // 画面に一切かかっていないものは「閉じたパネルの中身」。
                      // 閉じた詳細シートは display:none ではなく画面外へずらしてあるので、
                      // これを見ないと ✕ ボタンを毎回「画面外」と誤検出する (2026-07-31)。
                      const onScreen = Math.min(b.right, innerWidth) - Math.max(b.left, 0) > 0
                                    && Math.min(b.bottom, innerHeight) - Math.max(b.top, 0) > 0;
                      if (onScreen && (b.right > innerWidth + 0.5 || b.left < -0.5))
                        out.offscreen.push({nm: nm + '#' + i,
                                            txt: (e.textContent || '').trim().slice(0, 12)});
                    });
                  }
                  // 文字サイズ (帰属表示は別枠)
                  const T = [['header h1','見出し',0], ['header p','見出し下',0],
                             ['#q','検索入力',0], ['#searchstatus','検索結果',0],
                             ['.chip .lbl','カテゴリ名',0], ['#listbtn','お店一覧ボタン',0],
                             ['.detail-address','詳細の住所',0], ['footer,.credits,.foot','帰属表示',1]];
                  for (const [q, nm, attrib] of T) {
                    const e = document.querySelector(q); if (!e) continue;
                    // display:none の要素は誰も見ないので測らない
                    // (2026-07-31: header p が元から非表示で誤検出していた)
                    if (!shown(e)) continue;
                    out.texts.push({nm, fs: +parseFloat(getComputedStyle(e).fontSize).toFixed(1),
                                    attrib: !!attrib});
                  }
                  // N25 固定UIが帰属表示・注記を覆っていないか。
                  // OpenStreetMap の ODbL は帰属が読める状態を求める。
                  const fxb = ['#listbtn', '.zoomctl'].map(q => document.querySelector(q))
                    .filter(e => e && getComputedStyle(e).position === 'fixed' && shown(e))
                    .map(e => e.getBoundingClientRect());
                  out.credits = [];
                  for (const e of document.querySelectorAll('body *')) {
                    if (e.children.length || !shown(e)) continue;
                    const t = (e.textContent || '').trim();
                    if (t.length < 4) continue;
                    if (e.closest('#map, #listpanel, .detail-panel, .chooser, header, .filters, .searchbar')) continue;
                    if (e.closest('#listbtn, .zoomctl')) continue;
                    const b = e.getBoundingClientRect();
                    if (b.width < 2 || b.height < 2) continue;
                    for (const f of fxb) {
                      const ox = Math.min(b.right, f.right) - Math.max(b.left, f.left);
                      const oy = Math.min(b.bottom, f.bottom) - Math.max(b.top, f.top);
                      if (ox > 1 && oy > 1)
                        out.credits.push({txt: t.slice(0, 36),
                          pct: Math.round(100 * ox * oy / (b.width * b.height))});
                    }
                  }
                  const vp = document.getElementById('viewport').getBoundingClientRect();
                  out.mapRatio = +(vp.height / innerHeight).toFixed(3);
                  out.mapH = Math.round(vp.height);
                  out.vh = innerHeight;
                  // N26 こどもの声の店のラベルが既定ズームで出ているか。
                  // 本企画の看板機能なので、端末が小さくても消えてはいけない。
                  // 表示域の中だけを見ていたため、画面外に出た声の店が
                  // 名前を失っても気づけなかった (2026-07-31: 文字を14pxにした時に
                  // フラワー中山 が canvas 全体で消えたのを N26 が見逃した)。
                  // 動かせば見える所なので、canvas 全体で判定する。
                  // 2026-08-04: ボス指示で引き出し線(点線)を廃止した。密集部では
                  // 「自分の★がいちばん近い」を満たす置き場所が幾何的に無い店が出る
                  // (実測: 隣の★が画面上 8px の店がある)。名前を出せない代わりに
                  // 声バッジは必ず出す = 「どこに声があるか」は地図から読める。
                  // 名前もバッジも無いものだけを違反とする。
                  out.voiceHidden = [];
                  for (const h of document.querySelectorAll('g.hit')) {
                    const sp = GEO.shops[+h.dataset.i];
                    if (!(sp.voices && sp.voices.length)) continue;
                    const t = h.querySelector('text.shoplabel');
                    const vis = !!(t && getComputedStyle(t).display !== 'none'
                                   && t.getBoundingClientRect().width > 1);
                    const bg = h.querySelector('g.voice-badge');
                    const badgeVis = !!(bg && getComputedStyle(bg).display !== 'none'
                                        && bg.getBoundingClientRect().width > 1);
                    if (!vis && !badgeVis) out.voiceHidden.push(sp.name);
                  }
                  // 印を押した時に自分の店が開くか (押し分けの実測)。
                  // 例外は握り潰さない — 測れなければ理由を返して不合格にする。
                  out.tapSelf = null; out.tapErr = null;
                  try {
                    if (typeof shopsByTapDistance !== 'function')
                      throw new Error('shopsByTapDistance が無い');
                    const ownR = starTargetPx() / 2;
                    out.tapSelf = [];
                    for (const h of document.querySelectorAll('g.hit')) {
                      const st = h.querySelector('.star'); if (!st) continue;
                      const b = st.getBoundingClientRect(); if (!(b.width > 0)) continue;
                      const nm = GEO.shops[+h.dataset.i].name;
                      const ranked = shopsByTapDistance(b.left + b.width/2, b.top + b.height/2);
                      if (!ranked.length) { out.tapSelf.push({n: nm, got: '(候補なし)'}); continue; }
                      if (ranked[0].d > ownR) { out.tapSelf.push({n: nm, got: '選択窓'}); continue; }
                      if (ranked[0].shop.name !== nm)
                        out.tapSelf.push({n: nm, got: ranked[0].shop.name});
                    }
                  } catch (e) { out.tapErr = String((e && e.message) || e); }
                  return out;
                }"""
                # N27 ズームのたびに走るラベル配置が、時間内に終わるか。
                # layoutLabels を包んで実測する。包めていない (呼ばれた形跡が無い) 時は
                # 「測れた」ことにせず失敗として扱う — 0ms の偽合格を作らないため。
                TIMEJS = r"""async () => {
                  const orig = layoutLabels;
                  let worst = 0, calls = 0;
                  window.layoutLabels = function(){
                    const t0 = performance.now();
                    const r = orig.apply(this, arguments);
                    worst = Math.max(worst, performance.now()-t0); calls++;
                    return r;
                  };
                  const btns = [...document.querySelectorAll('.zoomctl button')];
                  const frame = () => new Promise(r =>
                    requestAnimationFrame(() => requestAnimationFrame(r)));
                  for (const b of btns) {
                    for (let i=0;i<3;i++){
                      b.click(); await frame(); await new Promise(r=>setTimeout(r,120));
                    }
                  }
                  window.layoutLabels = orig;
                  return {worst:+worst.toFixed(1), calls, buttons:btns.length};
                }"""
                # N20/N21 を「画面の状態ごとの総なめ」にする。
                # 2026-07-31 まで、手で選んだ8個のセレクタの *最初の1個ずつ* しか測っておらず、
                # 詳細シート・チューザー・一覧の住所・横向きを一度も測っていなかった。
                # 見えている文字と操作要素を全部拾う (地図の中の★は N24 の領分なので除く)。
                SWEEPJS = r"""(state) => {
                  const shown = e => { const cs = getComputedStyle(e);
                    return cs.display !== 'none' && cs.visibility !== 'hidden'
                        && parseFloat(cs.opacity) > .05 && e.getAttribute('aria-hidden') !== 'true'; };
                  // 閉じたパネルは display:none ではなく画面外へずらしてあるだけなので、
                  // 祖先の表示状態だけを見ると中身を全部拾ってしまう。面積の半分以上が
                  // 画面の中にあるものだけを「映っている」とする。
                  const vis = e => {
                    for (let n = e; n && n !== document.documentElement; n = n.parentElement)
                      if (!shown(n)) return false;
                    const r = e.getBoundingClientRect();
                    if (!(r.width > 0 && r.height > 0)) return false;
                    const iw = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
                    const ih = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
                    if (iw <= 0 || ih <= 0) return false;
                    return (iw * ih) >= .5 * (r.width * r.height); };
                  const sel = e => { const p = e.parentElement;
                    const cn = x => x && typeof x.className === 'string' && x.className.trim()
                      ? '.' + x.className.trim().split(/\s+/).slice(0,2).join('.') : '';
                    return e.id ? '#'+e.id
                      : (cn(p) ? cn(p)+' > ' : '') + e.tagName.toLowerCase() + cn(e); };
                  const texts = [], taps = [];
                  for (const e of document.querySelectorAll('body *')) {
                    if (e.closest('svg') || !vis(e)) continue;
                    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
                    const attrib = !!e.closest('footer, .credits, .foot');
                    const fs = +parseFloat(getComputedStyle(e).fontSize).toFixed(1);
                    if (fs < (attrib ? 12 : 14))
                      texts.push({state, sel:sel(e), fs, attrib,
                                  txt:(e.textContent||'').trim().slice(0,18)});
                  }
                  // 2026-08-10: 地図の中の文字を丸ごと除外していたので、何pxでも通っていた。
                  // SVG の font-size は変形前の値。画面上の実寸で測る。
                  for (const e of document.querySelectorAll('svg text, svg tspan')) {
                    // 地図は動かせるので、いま画面の中にあるかは問わない。
                    // 大きさは画面内にあるかどうかで変わらないし、遠い店の但し書きは
                    // 寄せて初めて出る。画面内だけ見ていたので永久に対象外だった。
                    if (!shown(e)) continue;
                    { let _p = e.parentElement, _ok = true;
                      while (_p && _p !== document.documentElement) { if (!shown(_p)) { _ok = false; break; }
                        _p = _p.parentElement; }
                      if (!_ok) continue; }
                    const _r = e.getBoundingClientRect();
                    if (!(_r.width > 0 && _r.height > 0)) continue;
                    if (!(e.textContent || '').trim()) continue;
                    const own = e.tagName.toLowerCase() === 'tspan'
                      || ![...e.children].some(c => c.tagName.toLowerCase() === 'tspan');
                    if (!own) continue;
                    const sv = e.ownerSVGElement; if (!sv) continue;
                    const m = sv.getScreenCTM(); if (!m) continue;
                    const k = Math.hypot(m.a, m.b);
                    const fs = +(parseFloat(getComputedStyle(e).fontSize) * k).toFixed(1);
                    if (fs < 14)
                      texts.push({state, sel:'地図の ' + (e.getAttribute('class') || e.tagName),
                                  fs, attrib:false, txt:(e.textContent||'').trim().slice(0,18)});
                  }
                  for (const e of document.querySelectorAll(
                        'button,a[href],input,select,[role="button"],[tabindex]')) {
                    if (e.closest('svg') || !vis(e)) continue;
                    const r = e.getBoundingClientRect();
                    if (r.width < 44 || r.height < 44)
                      taps.push({state, sel:sel(e), w:+r.width.toFixed(1), h:+r.height.toFixed(1),
                                 txt:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,18)});
                  }
                  // N28 ボタン・チップのラベルが語の途中で改行されていないか。
                  // 日本語の本文はどこで折り返しても正しいが、短いラベルが
                  // 「食べる・飲｜む・食料」のように切れると壊れて見える。
                  // 中点・読点・空白・括弧での改行は自然なので許す。
                  const OK_BREAK = '・、，  （(）)／/';
                  const wrap = [];
                  // 行の頭に置いてはいけない字。2026-08-10: 「食べる・飲む / ・食料」と
                  // 中黒で行が始まっていた。OK_BREAK に「・」があるため、中黒の直前で
                  // 折れるのを「折れてよい所」と読んでいた。折ってよいのは中黒の後ろだけ。
                  const NO_LINE_START = '・、。，．）)」』】〉》！？!?ーぁぃぅぇぉっゃゅょゎ々…‥';
                  for (const e of document.querySelectorAll(
                        'button, .chip, .chip .lbl, [role="button"]')) {
                    if (!vis(e)) continue;
                    if (e.closest('#viewport')) continue;   // 地図のラベルは N54/N56 の担当
                    // 一覧の行・二列カードは N57 の担当。ここで重ねて見ると、
                    // 店名と住所という別々の行を1つの文字列として繋いでしまい、
                    // 「air｜泉区」のような存在しない改行を報告する。
                    if (e.matches('.strip-row, .lrow') || e.closest('.strip-row, .lrow, #listrows')) continue;
                    // 2026-08-10: 最初のテキストノードしか見ていなかったので、
                    // <wbr> で分割した2つ目以降のノードで起きる改行が視界の外だった。
                    const nodes = [];
                    const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
                    for (let nd = tw.nextNode(); nd; nd = tw.nextNode())
                      if (nd.textContent.length) nodes.push(nd);
                    const full = nodes.map(nd => nd.textContent).join('');
                    if (full.trim().length < 2) continue;
                    // <wbr> の直後は「ここで折ってよい」と作者が宣言した位置。
                    // その位置で折れたことを違反として数えない (行頭禁則だけは別に見る)。
                    const okAt = new Set();
                    {
                      let g = 0;
                      for (const nd of nodes) {
                        // 文字が span で包まれている場合もあるので、包みの手前も見る
                        let anchor = nd;
                        while (anchor && anchor !== e && !anchor.previousSibling) anchor = anchor.parentNode;
                        let prev = anchor ? anchor.previousSibling : null;
                        while (prev && prev.nodeType === 3 && !prev.textContent.trim())
                          prev = prev.previousSibling;
                        if (prev && prev.nodeName === 'WBR') okAt.add(g);
                        g += nd.textContent.length;
                      }
                    }
                    const rg = document.createRange();
                    let prevTop = null, prevCh = null, gi = 0;
                    for (const nd of nodes) {
                      const txt = nd.textContent;
                      for (let i = 0; i < txt.length; i++, gi++) {
                        rg.setStart(nd, i); rg.setEnd(nd, i+1);
                        const b = rg.getBoundingClientRect();
                        if (!b.height) { prevCh = txt[i]; continue; }
                        if (prevTop !== null && b.top > prevTop + 2) {
                          const before = prevCh, after = txt[i];
                          const around = full.slice(Math.max(0, gi-3), gi) + '｜' + full.slice(gi, gi+3);
                          if (NO_LINE_START.includes(after))
                            wrap.push({state, sel:sel(e), txt:full.trim().slice(0,20),
                                       at: around, why:'行頭に置けない字'});
                          else if (!okAt.has(gi)
                                   && !OK_BREAK.includes(before) && !OK_BREAK.includes(after))
                            wrap.push({state, sel:sel(e), txt:full.trim().slice(0,20),
                                       at: around, why:'語の途中'});
                        }
                        prevTop = b.top; prevCh = txt[i];
                      }
                    }
                  }
                  // N29 文字が入れ物からはみ出していないか (検索の説明文など)。
                  // 幅の引き算で見積もると外す。入力欄の中の文字領域は
                  // 「幅 - 余白 - 枠」より狭く、2026-07-31 は見積もりで「収まっている」と
                  // 判定した所が実際には15px切れていた。実際に文字を入れて溢れを測る。
                  const clip = [];
                  for (const e of document.querySelectorAll('input')) {
                    if (!vis(e) || !e.placeholder) continue;
                    const before = e.value;
                    e.value = e.placeholder;                 // 入力イベントは発生しない
                    const need = e.scrollWidth, has = e.clientWidth;
                    e.value = before;                        // 数字は戻す前に取る
                    if (need - has > 0)
                      clip.push({state, sel:sel(e), txt:e.placeholder, need, has});
                  }
                  // ---- N30 文字と背景の明暗差 (WCAG 1.4.3) ----
                  const pc = s => { const m=(s||'').match(/rgba?\(([^)]+)\)/); if(!m) return null;
                    const p=m[1].split(',').map(parseFloat);
                    return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}; };
                  const lum = c => { const f=v=>{v/=255;
                      return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4);};
                    return .2126*f(c.r)+.7152*f(c.g)+.0722*f(c.b); };
                  const cr = (a,b) => { const l1=lum(a), l2=lum(b);
                    return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05); };
                  let paperC = null;
                  {
                    const d = document.createElement('div');
                    d.style.color = getComputedStyle(document.documentElement)
                      .getPropertyValue('--paper').trim();
                    document.body.appendChild(d);
                    paperC = pc(getComputedStyle(d).color); d.remove();
                  }
                  const bgOf = e => {
                    for (let n=e; n; n=n.parentElement) {
                      const c = pc(getComputedStyle(n).backgroundColor);
                      if (c && c.a > .5) return c;
                      if (n === document.body) break;
                    }
                    if (e.closest('svg') && paperC) return paperC;
                    return {r:255,g:255,b:255,a:1};
                  };
                  const contrast = [];
                  for (const e of document.querySelectorAll('body *')) {
                    // 地図の文字は表示域の外でも動かせば見えるので画面内判定を課さない
                    const inMap = !!e.closest('svg');
                    if (!inMap && !vis(e)) continue;
                    if (inMap && (getComputedStyle(e).display === 'none'
                                  || e.getBoundingClientRect().width < 1)) continue;
                    if (![...e.childNodes].some(n=>n.nodeType===3 && n.textContent.trim())) continue;
                    const cs = getComputedStyle(e);
                    const fg = pc(inMap ? cs.fill : cs.color);
                    if (!fg || fg.a < .5) continue;
                    const px = parseFloat(cs.fontSize);
                    const bold = (parseInt(cs.fontWeight)||400) >= 700;
                    const need = (px >= 24 || (px >= 18.66 && bold)) ? 3.0 : 4.5;
                    const r = cr(fg, bgOf(e));
                    if (r < need)
                      contrast.push({state, sel:sel(e), txt:(e.textContent||'').trim().slice(0,16),
                                     ratio:+r.toFixed(2), need, px:+px.toFixed(1)});
                  }
                  // ---- N31 押せるもの同士の間隔 ----
                  const gaps = [];
                  {
                    // 上に何か乗っていて実際には押せないものは対象外。
                    // 横向きで一覧を開くと、検索欄とお店一覧ボタンはパネルの裏に隠れる。
                    // 隠れているものとの隙間を測ると幽霊の隣接を数えることになる
                    // (2026-07-31: これで3回、同じ場所を追いかけ回した)。
                    // 2026-08-04: スクロールする入れ物からはみ出した部分は切り取られていて
                    // 指は届かない。切り取り後の (=実際に触れる) 形で測る。
                    // これを見ていなかったため、画面外に切れたボタンと下帯が
                    // 「重なっている」と誤って出ていた。
                    const clipRect = e => {
                      let r = e.getBoundingClientRect();
                      for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
                        const cs = getComputedStyle(n);
                        if (cs.overflow === 'visible' && cs.overflowX === 'visible'
                            && cs.overflowY === 'visible') continue;
                        const c = n.getBoundingClientRect();
                        const left = Math.max(r.left, c.left), right = Math.min(r.right, c.right);
                        const top = Math.max(r.top, c.top), bottom = Math.min(r.bottom, c.bottom);
                        r = {left, right, top, bottom, width:right-left, height:bottom-top};
                      }
                      return r;
                    };
                    const els = [...document.querySelectorAll(
                        'button,a[href],input,[role="button"]')]
                      .filter(e => vis(e) && !e.closest('svg'))
                      .filter(e => { const r = e.getBoundingClientRect();
                        const hit = document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
                        return !!(hit && (hit === e || e.contains(hit))); })
                      .map(e => ({nm:(e.getAttribute('aria-label')||e.textContent||'')
                                     .trim().slice(0,14), r:clipRect(e)}))
                      .filter(o => o.r.width > 0.5 && o.r.height > 0.5);
                    for (let i=0;i<els.length;i++) for (let j=i+1;j<els.length;j++) {
                      const a=els[i].r, b=els[j].r;
                      const ox = Math.min(a.right,b.right)-Math.max(a.left,b.left);
                      const oy = Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
                      if (ox>0 && oy>0) {
                        // N44 重なり。N31 は「隙間」だけを見て重なりを除外していたが、
                        // その別問題の検査を作っていなかった (2026-07-31: 二列表示で
                        // 17組のカードが重なっているのを素通りさせた)。
                        if (ox>1 && oy>1)
                          gaps.push({state, a:els[i].nm, b:els[j].nm,
                                     gap:-1, ox:+ox.toFixed(0), oy:+oy.toFixed(0)});
                        continue;
                      }
                      const dx = ox>0 ? 0 : Math.max(a.left-b.right, b.left-a.right, 0);
                      const dy = oy>0 ? 0 : Math.max(a.top-b.bottom, b.top-a.bottom, 0);
                      const g = Math.hypot(dx, dy);
                      // 隙間0 = 一覧の行が接している普通の設計。行そのものが的なので
                      // 押し間違いにならない。危ないのは「少しだけ空いている」場合。
                      if (g >= .5 && g < 8)
                        gaps.push({state, a:els[i].nm, b:els[j].nm, gap:+g.toFixed(1),
                                   // どこにあったのか分からないと原因を追えない (2026-08-04)
                                   ra:[Math.round(a.left),Math.round(a.top),Math.round(a.right),Math.round(a.bottom)],
                                   rb:[Math.round(b.left),Math.round(b.top),Math.round(b.right),Math.round(b.bottom)]});
                    }
                  }
                  // ---- N34 絵文字をアイコン代わりに使っていないか ----
                  const emoji = [];
                  {
                    // 色付きで描かれる絵文字だけを見る。✕ (U+2715) や → は
                    // 昔からの約物で、端末ごとに絵が変わることもないので対象外。
                    const EMO = /[\u{1F000}-\u{1FAFF}]|[\u{2190}-\u{2BFF}]\u{FE0F}/u;
                    for (const e of document.querySelectorAll(
                        'button, a[href], [role="button"], .chip')) {
                      if (!vis(e) || e.closest('svg')) continue;
                      const t = e.textContent || '';
                      const m = t.match(EMO);
                      if (m) emoji.push({state, sel:sel(e), txt:t.trim().slice(0,16), ch:m[0]});
                    }
                  }
                  // ---- N33 キーボードで地図を飛ばせるか / タブ順が見た目と合うか ----
                  const tabbable = [...document.querySelectorAll(
                    'button,a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')]
                    .filter(vis);
                  const bypass = {
                    total: tabbable.length,
                    inMap: tabbable.filter(e => e.closest('svg')).length,
                    skip: [...document.querySelectorAll('a[href^="#"]')]
                      .filter(a => /とば|スキップ|skip|飛ば/i
                        .test(a.textContent || a.getAttribute('aria-label') || '')).length,
                    // CSS の order で見た目の順を入れ替えている操作要素は、
                    // Tab の順が見た目と食い違う (2026-07-31: こどもの声チップが該当)
                    reordered: tabbable
                      .filter(e => { const o = getComputedStyle(e).order;
                                     return o && o !== '0' && o !== 'normal'; })
                      .map(e => ({sel:sel(e),
                                  nm:(e.getAttribute('aria-label')||e.textContent||'')
                                       .trim().slice(0,16),
                                  order:getComputedStyle(e).order})),
                  };
                  // N57 一覧の店名が語の途中で折り返されていないか。
                  // 2026-08-09: 「ウジエスーパー中 / 山店」のように行の境目が語の途中に
                  // 来ていた (ボスの実機写真)。一度直したのに割れ方が変わって同じ日に
                  // 再発したので検査に入れる。
                  // 判定 = 行の境目にある2文字が「同じ文字種で、もとの名前で隣り合っている」なら不合格。
                  //   中｜山  → どちらも漢字で隣り合う → 語の途中 → 不合格
                  //   ー｜中  → カタカナと漢字の境目 → 自然な折り返し → 合格
                  //   バー｜祭 → もとの名前では間に空白 → 合格
                  // 「1文字だけの行」で数えると「ウジエスーパー中 / 山店」を取りこぼす
                  // (1行目8文字・2行目2文字なので、1文字の行が無い)。2026-08-09 に実際に外した。
                  const charKind = ch => /[ァ-ヺーヽヾ・]/.test(ch) ? 'kana'
                    : /[ぁ-ゟ一-鿿々〆ヵヶ]/.test(ch) ? 'jp'
                    : /[0-9A-Za-z]/.test(ch) ? 'latin' : 'other';
                  // 判定 = 本体が決めた「かたまり」(span) の中で行が変わっていないか。
                  // 長い外来語は枠に入らないのでどこかで折るしかなく、境目そのものは
                  // 責められない。責めるべきは**かたまりの内側で折れること**で、
                  // それが「ウジエスーパー中 / 山店」「リハビリステーショ / ン」の正体。
                  // 折ってよい位置の定義は本体 (setStripShopName) が持っている。
                  // 検査側で定義し直すと必ずズレるので、span の切れ目をそのまま使う。
                  const lone = [];
                  for (const e of document.querySelectorAll('.strip-shop-name')) {
                    if (!vis(e)) continue;
                    const full = e.textContent.trim();
                    // かたまり自体が1文字 = 折り返した時にその1文字が行に取り残される。
                    // 「ウジエスーパー / 中 / 山店」がこれだった (ボスの実機写真)。
                    // かたまりの内側では折れていないので、下の判定では見えない。
                    // もとの名前で独立した語 (「ダイニングバー 祭」の「祭」) は正しい。
                    const words = new Set(full.split(/\s+/));
                    for (const sp of e.querySelectorAll('span')) {
                      const one = sp.textContent;
                      if ([...one].length === 1 && !words.has(one))
                        lone.push({state, txt: full.slice(0,22), line: '「'+one+'」だけのかたまり'});
                    }
                    for (const sp of e.querySelectorAll('span')) {
                      const t = sp.firstChild;
                      if (!t || t.nodeType !== 3) continue;
                      const txt = t.textContent;
                      if (txt.length < 2) continue;
                      const rg = document.createRange();
                      let prevTop = null, at = null;
                      for (let i = 0; i < txt.length; i++) {
                        rg.setStart(t, i); rg.setEnd(t, i + 1);
                        const b = rg.getBoundingClientRect();
                        if (!(b.width > 0)) continue;
                        const top = Math.round(b.top);
                        if (prevTop !== null && top > prevTop + 1){
                          at = txt[i-1] + '｜' + txt[i];
                          break;
                        }
                        prevTop = top;
                      }
                      if (at) lone.push({state, txt: full.slice(0,22), line: at});
                    }
                  }
                  // N58 ボタンの文字に「1文字だけの行」ができていないか。
                  // 2026-08-10: 見出しの戻るボタンが「✕ 通りへもど / る」と割れ、
                  // 「る」が1文字だけ最後の行に落ちていた (3回目の同型指摘)。
                  // N28 が捕まえられなかった理由 = 要素の**最初のテキストノードしか**見ておらず、
                  // `✕ 通り<wbr>へもどる` の2つ目のノードにある「もど｜る」が視界の外だった。
                  // ここでは要素の中の全テキストノードを論理順につなぎ、行ごとに数える。
                  // もとの文で独立している語 (「✕ 通りへもどる」の「✕」) は正しいので除く。
                  const orphan = [];
                  // 2026-08-10: ボタンとチップしか見ていなかったので、詳細の案内文
                  // 「左右にスワイプして次 / へ」の1文字落ちを素通りしていた (目で発見)。
                  // 短い案内・見出しも同じ規則で見る。
                  for (const e of document.querySelectorAll(
                      'button, [role="button"], .chip, .detail-guide, .detail-eyebrow,'
                      + ' .detail-cat, .empty-help-title, .strip-credit-contact, h1, h2')) {
                    if (!vis(e)) continue;
                    if (e.closest('.strip-row, .lrow, #listrows, #strip')) continue; // N57 の担当
                    const nodes = [];
                    const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
                    for (let n = tw.nextNode(); n; n = tw.nextNode())
                      if (n.textContent.length) nodes.push(n);
                    const full = nodes.map(n => n.textContent).join('');
                    if (full.trim().length < 3) continue;
                    const words = new Set(full.trim().split(/\s+/));
                    const rg = document.createRange();
                    const lines = new Map();
                    for (const n of nodes) {
                      const t = n.textContent;
                      for (let i = 0; i < t.length; i++) {
                        if (!t[i].trim()) continue;
                        rg.setStart(n, i); rg.setEnd(n, i + 1);
                        const b = rg.getBoundingClientRect();
                        if (!(b.width > 0 || b.height > 0)) continue;
                        const key = Math.round(b.top);
                        if (!lines.has(key)) lines.set(key, []);
                        lines.get(key).push(t[i]);
                      }
                    }
                    if (lines.size < 2) continue;
                    for (const [, chars] of lines) {
                      if (chars.length !== 1) continue;
                      if (words.has(chars[0])) continue; // もとから独立した1文字は正しい
                      orphan.push({state, sel: sel(e), txt: full.trim().slice(0, 24),
                                   ch: chars[0], lines: lines.size});
                    }
                  }
                  // N59 箱が中身の文字を切っていないか。
                  // 端末の文字設定を大きくすると、高さを px で決め打ちした箱 (header 等) が
                  // 中の見出しを黙って刈り込む。2026-08-10 あみさん「拡大すると文字が大変」。
                  // 見る軸ごとに判定する: はみ出た側が hidden/clip の時だけ違反。
                  // スクロールできる箱 (auto/scroll) と読み上げ専用の 1px 箱は対象外。
                  const cutbox = [];
                  for (const e of document.querySelectorAll('*')) {
                    if (!vis(e)) continue;
                    const b = e.getBoundingClientRect();
                    if (b.width <= 2 || b.height <= 2) continue;   // .sr-only
                    const cs = getComputedStyle(e);
                    if (cs.textOverflow === 'ellipsis') continue;  // 切れたと分かる形なので別扱い
                    if (!(e.innerText || '').trim()) continue;
                    const dw = e.scrollWidth - e.clientWidth;
                    const dh = e.scrollHeight - e.clientHeight;
                    const hidX = /hidden|clip/.test(cs.overflowX), hidY = /hidden|clip/.test(cs.overflowY);
                    const w = hidX && dw > 2 ? dw : 0, h = hidY && dh > 2 ? dh : 0;
                    if (!w && !h) continue;
                    cutbox.push({state, sel: sel(e), txt: (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 24),
                                 dw: w, dh: h});
                  }
                  // N60 同じ行の中で、店名が住所より小さくなっていないか。
                  // 端末の文字設定に上限をつけて崩れを止める直し方は、上限をつけ忘れた
                  // 文字だけが伸び続けて主従が入れ替わる。2026-08-10 実測: 200%の端末で
                  // 店名18px / 住所28px になり、住所の方が目立っていた。
                  const rank = [];
                  for (const row of document.querySelectorAll('.lrow, .strip-row')) {
                    if (!vis(row)) continue;
                    const nm = row.querySelector('.lname, .strip-shop-name');
                    // 2026-08-10: '.strip-shop-addr' は存在しないクラスで、二列カード側が
                    // まるごと空振りしていた (N57/N58 と同型の3度目)。相方は .strip-distance。
                    const ad = row.querySelector('.laddr, .strip-distance');
                    if (!nm || !ad || !vis(nm) || !vis(ad)) continue;
                    const n = parseFloat(getComputedStyle(nm).fontSize);
                    const a = parseFloat(getComputedStyle(ad).fontSize);
                    if (n >= a - 0.05) continue;
                    rank.push({state, sel: sel(row), txt: (nm.innerText || '').trim().slice(0, 20),
                               name: Math.round(n * 10) / 10, addr: Math.round(a * 10) / 10});
                  }
                  return {texts, taps, wrap, clip, contrast, gaps, emoji, bypass, lone, orphan, cutbox, rank};
                }"""
                # 画面の状態を作る手順。詳細シートは単一ボタンで開ける店、
                # チューザーは複数候補が出る店を選ぶ。
                STATES = [
                  # 印の真ん中を押す = 現行の判定①。その店の詳細が開くのが正。
                  ("詳細シート", r"""async () => {
                     const h=document.querySelector('g.hit');
                     if(!h) return false;
                     const st=h.querySelector('.star'); const b=st.getBoundingClientRect();
                     st.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1,
                       clientX:b.left+b.width/2, clientY:b.top+b.height/2}));
                     await new Promise(r=>setTimeout(r,700));
                     return document.body.classList.contains('detail-open'); }"""),
                  # 選択窓。指では ほぼ到達しない状態になったが (2026-08-08 実測:
                  # 印の中点1770通りのうち、選択窓の条件を満たすのは3通り)、
                  # 出た時の見た目は検査する。到達性は N24 側で別に測る。
                  ("チューザー", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     if (typeof showChooser !== 'function') return false;
                     const list=GEO.shops.slice(0,3);
                     showChooser(list, list[0]);
                     await new Promise(r=>setTimeout(r,450));
                     return document.getElementById('chooser').classList.contains('show'); }"""),
                  ("お店一覧", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     document.getElementById('listbtn').click();
                     await new Promise(r=>setTimeout(r,450)); return true; }"""),
                  ("検索中", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     const q=document.getElementById('q'); q.value='なか';
                     q.dispatchEvent(new Event('input',{bubbles:true}));
                     await new Promise(r=>setTimeout(r,450)); return true; }"""),
                  # 2026-08-01 追加。ここまで総なめの対象は「詳細シート・チューザー・
                  # お店一覧・検索中」の4つだけで、地図を開いた状態が入っていなかった。
                  # そのため地図モードの上帯 (見出し・戻る・絞り込みバッジ) と
                  # 下帯 (帰属・一覧・戻る・ズーム) は一度も N20/N21/N28-N31/N34 に
                  # かかっておらず、360x640 で「お店一覧」が「お店一/覧」と
                  # 語の途中で折れているのを素通りさせた。最後に置く (地図は最後に閉じる)。
                  ("地図", r"""async () => {
                     document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                     await new Promise(r=>setTimeout(r,300));
                     const q=document.getElementById('q');
                     if(q){ q.value=''; q.dispatchEvent(new Event('input',{bubbles:true})); }
                     const b=document.getElementById('mapbtn');
                     if(!b) return false;
                     if(b.getAttribute('aria-expanded')!=='true') b.click();
                     await new Promise(r=>setTimeout(r,800)); return true; }"""),
                  ("地図で絞り込み中", r"""async () => {
                     const b=document.getElementById('mapbtn');
                     if(!b) return false;
                     if(b.getAttribute('aria-expanded')!=='true'){ b.click();
                       await new Promise(r=>setTimeout(r,700)); }
                     const c=document.querySelector('.chip.voice-filter');
                     if(!c) return false;
                     if(c.getAttribute('aria-pressed')!=='true') c.click();
                     await new Promise(r=>setTimeout(r,700)); return true; }"""),
                ]
                UI = []
                _rows = [(w, h, 16) for w, h in UI_DEVICES + UI_LANDSCAPE] + UI_FONT_ROWS
                if A.devices:
                    _want = []
                    for _spec in A.devices.split(","):
                        _spec = _spec.strip()
                        if not _spec:
                            continue
                        _wh, _, _fs = _spec.partition("@")
                        _w, _, _h = _wh.partition("x")
                        _want.append((int(_w), int(_h), int(_fs) if _fs else None))
                    _rows = [r for r in _rows
                             if any(r[0] == w and r[1] == h and (f is None or r[2] == f)
                                    for w, h, f in _want)]
                    if not _rows:
                        sys.exit("!! --devices に一致する端末が無い: %s" % A.devices)
                for uw, uh, ufs in _rows:
                    up = br.new_page(viewport={"width": uw, "height": uh})
                    if ufs != 16:
                        # 端末の「文字の大きさ」設定。ブラウザのページ拡大ではないので
                        # 見た目は伸びず、rem と既定サイズの文字だけが伸びる。
                        _cdp = up.context.new_cdp_session(up)
                        _cdp.send("Page.enable")
                        _cdp.send("Page.setFontSizes", {"fontSizes": {"standard": ufs, "fixed": ufs}})
                    up.goto(url, wait_until="load")
                    up.wait_for_timeout(1200)
                    sweep = {"texts": [], "taps": [], "wrap": [], "clip": [], "contrast": [],
                             "gaps": [], "emoji": [], "lone": [], "orphan": [], "cutbox": [], "rank": []}
                    base = up.evaluate(SWEEPJS, "開いた直後")
                    for _k in SWEEP_KEYS:
                        sweep[_k] += base[_k]
                    sweep["bypass"] = base["bypass"]
                    # 状態を作れなかったら「対象が無い」ではなく「測れなかった」。
                    # 黙って continue すると、その画面が総なめから消える
                    # (2026-08-08 実測: nearby() の廃止でチューザーが対象0件のまま
                    #  PASS し続けていた)。作れなかった状態は控えて不合格にする。
                    sweep["missing"] = []
                    for st, act in STATES:
                        if up.evaluate(act) is False:
                            sweep["missing"].append(st)
                            continue
                        r = up.evaluate(SWEEPJS, st)
                        for _k in SWEEP_KEYS:
                            sweep[_k] += r[_k]
                    if ufs != 16:
                        # どの文字サイズで出た違反かを状態名に焼いておく。
                        # 場所が「320x568 お店一覧」だけだと、既定の文字で再現できず
                        # 「直ってない」と誤読される。
                        for _k in SWEEP_KEYS:
                            for _it in sweep[_k]:
                                _it["state"] = "文字%dpx %s" % (ufs, _it.get("state", ""))
                        # 2026-08-10: 文字サイズ行で寸法検査を全部飛ばしていたが、
                        # header を height:auto にした以上、高さ予算が痩せるのは
                        # まさに文字を大きくした時。主の内容の高さだけは必ず測る。
                        up.evaluate("""async () => {
                            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                            const q=document.getElementById('q');
                            if(q){ q.value=''; q.dispatchEvent(new Event('input',{bubbles:true})); }
                            const c=document.querySelector('.chip.voice-filter');
                            if(c && c.getAttribute('aria-pressed')==='true') c.click();
                            const b=document.getElementById('mapbtn');
                            if(b && b.getAttribute('aria-expanded')==='true') b.click();
                            await new Promise(r=>setTimeout(r,700)); }""")
                        _main = up.evaluate("""() => {
                          const e = document.getElementById('stripview')
                                || document.getElementById('strip')
                                || document.getElementById('viewport');
                          if (!e) return {r:0, px:0};
                          const h = e.getBoundingClientRect().height;
                          return {r:+(h/innerHeight).toFixed(3), px:Math.round(h)};
                        }""")
                        _seen = up.evaluate("""() => {
                          const sv = document.getElementById('stripview');
                          if (!sv) return 0;
                          const b = sv.getBoundingClientRect();
                          return [...document.querySelectorAll('.strip-row')].filter(e => {
                            if (e.hidden) return false;
                            const r = e.getBoundingClientRect();
                            return r.height > 0 && r.bottom > b.top + 4 && r.top < b.bottom - 4;
                          }).length;
                        }""")
                        UI.append({"vw": uw, "vh": uh, "portrait": uh > uw,
                                   "fontPx": ufs, "offscreen": [], "sweep": sweep,
                                   "mainRatio": _main["r"], "mainPx": _main["px"],
                                   "shopsInView": _seen})
                        up.close()
                        continue
                    up.evaluate("""async () => {
                        document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
                        const q=document.getElementById('q');
                        if(q){ q.value=''; q.dispatchEvent(new Event('input',{bubbles:true})); }
                        // 総なめの最後が地図モード + 絞り込みなので、必ず元へ戻す。
                        // 戻さないと この後の N22/N23/N25/N26 を地図が開いたまま測ってしまう。
                        const c=document.querySelector('.chip.voice-filter');
                        if(c && c.getAttribute('aria-pressed')==='true') c.click();
                        const b=document.getElementById('mapbtn');
                        if(b && b.getAttribute('aria-expanded')==='true') b.click();
                        await new Promise(r=>setTimeout(r,700)); }""")
                    # 既存の測定 (N22/N23/N25/N26) は「開いた直後 + お店一覧」で行う
                    up.evaluate("()=>document.getElementById('listbtn').click()")
                    up.wait_for_timeout(350)
                    u = up.evaluate(UIJS)
                    u["strip"] = up.evaluate("""() => {
                      const rows = [...document.querySelectorAll('.strip-row')].map(e => {
                        const r = e.getBoundingClientRect();
                        return {i:+e.dataset.i, side:e.dataset.side, y:+e.dataset.y,
                                top:+r.top.toFixed(1), h:+r.height.toFixed(1),
                                far: !!e.closest('#stripfar'),
                                // ずらして置いたことを引き出し線で見せているか (N42)
                                disp: e.classList.contains('displaced')};
                      });
                      // 押すもののうち「操作」だけ (一覧の行は中身なので対象外)
                      const ctl = ['#q', '.chip', '#mapbtn', '#listbtn', '.zoomctl button']
                        .flatMap(q => [...document.querySelectorAll(q)])
                        .filter(e => { const c = getComputedStyle(e);
                          if (c.display === 'none' || c.visibility === 'hidden') return false;
                          // 閉じた地図の中のボタンは矩形が (0,0) になる。
                          // 見えていないものを「上にある」と数えない (2026-07-31)。
                          const r = e.getBoundingClientRect();
                          return r.width > 0 && r.height > 0
                                 && r.bottom > 0 && r.top < innerHeight; })
                        .map(e => { const r = e.getBoundingClientRect();
                          return {nm:(e.getAttribute('aria-label')||e.textContent||'')
                                    .trim().slice(0,16),
                                  cy:+(r.top + r.height/2).toFixed(0)}; });
                      return {rows, ctl, h:innerHeight,
                              pxPerM:(typeof STRIP_PX_PER_M !== 'undefined'
                                      ? STRIP_PX_PER_M : null)};
                    }""")
                    # 2026-07-31: 主役が二列表示になったので、既定の画面で測るのは
                    # 「主の内容 (二列) の大きさ」。地図の大きさと こどもの声のラベルは
                    # 地図を開いた状態でないと測れない (閉じた地図を測って158件出した)。
                    u["mainRatio"] = up.evaluate("""() => {
                      const e = document.getElementById('stripview')
                            || document.getElementById('strip')
                            || document.getElementById('viewport');
                      if (!e) return 0;
                      return +(e.getBoundingClientRect().height / innerHeight).toFixed(3);
                    }""")
                    u["mainPx"] = up.evaluate("""() => {
                      const e = document.getElementById('stripview')
                            || document.getElementById('strip')
                            || document.getElementById('viewport');
                      return e ? Math.round(e.getBoundingClientRect().height) : 0;
                    }""")
                    # N48 二列のカード同士の縦の隙間 (同じ側の隣どうし)
                    u["stripGaps"] = up.evaluate(STRIP_GAP_JS)
                    # N49 絞り込んだとき、該当が1画面にいくつ見えるか
                    u["filterView"] = up.evaluate(FILTER_VIEW_JS)
                    # N50 探しそうな言葉が引っかかるか
                    u["searchWords"] = up.evaluate(SEARCH_WORDS_JS, [w for w, _ in SEARCH_WORDS])
                    # N51 通りの中の飾り (道路名・信号) が重なっていないか
                    u["stripDecor"] = up.evaluate(STRIP_DECOR_JS)
                    if _open_map(up):
                        up.wait_for_timeout(900)
                        m2 = up.evaluate(UIJS)
                        u["mapRatio"] = m2["mapRatio"]
                        u["mapH"] = m2["mapH"]
                        u["voiceHidden"] = m2["voiceHidden"]
                        # N45-N47 地図の画面。開いた地図を実際に測る (2026-07-31 追加)
                        u["mapFrame"] = up.evaluate(MAP_FRAME_JS)
                        u["compass"] = up.evaluate(COMPASS_JS)
                    u["vw"] = uw
                    u["vh"] = uh
                    u["portrait"] = uh > uw
                    u["sweep"] = sweep
                    u["layout"] = up.evaluate(TIMEJS)
                    UI.append(u)
                    up.close()
                REND["ui"] = UI
                # N33 追加: 指で届く範囲とキーボードで届く範囲が一致しているか。
                # お店一覧を開いた状態で、外のカテゴリ・検索は指では押せて一覧に効く
                # (2026-07-31 実測: 60→11→1→60)。ところが Tab はパネルの中に
                # 閉じ込められていて、キーボードだけの人はその機能に届かない。
                kp = br.new_page(viewport={"width": 390, "height": 844})
                kp.goto(url, wait_until="load")
                kp.wait_for_timeout(1200)
                kp.evaluate("()=>document.getElementById('listbtn').click()")
                kp.wait_for_timeout(450)
                LIVE_OUTSIDE = """() => {
                  const out = [];
                  for (const e of document.querySelectorAll('button,a[href],input,[role="button"]')) {
                    if (e.closest('#listpanel') || e.closest('svg')) continue;
                    if (e.hasAttribute('inert') || e.closest('[inert]')) continue;
                    if (e.closest('[aria-hidden="true"]')) continue;
                    const cs = getComputedStyle(e);
                    if (cs.display === 'none' || cs.visibility === 'hidden'
                        || cs.pointerEvents === 'none') continue;
                    const r = e.getBoundingClientRect();
                    if (r.width < 1 || r.height < 1) continue;
                    const hit = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                    if (hit && (hit === e || e.contains(hit)))
                      out.push((e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,16));
                  }
                  return out;
                }"""
                live_outside = kp.evaluate(LIVE_OUTSIDE)
                kp.evaluate("()=>{const c=document.getElementById('listclose'); if(c) c.focus();}")
                reached = set()
                for _ in range(40):
                    kp.keyboard.press("Tab")
                    w = kp.evaluate("""() => { const a = document.activeElement;
                      if (!a || a === document.body) return null;
                      return {inPanel: !!a.closest('#listpanel'),
                              nm:(a.getAttribute('aria-label')||a.textContent||'').trim().slice(0,16)};}""")
                    if w and not w["inPanel"]:
                        reached.add(w["nm"])
                REND["keyboardParity"] = {"liveOutside": live_outside,
                                          "reachedByTab": sorted(reached)}
                kp.close()
                # ---- N35 地図の店名の大きさ / N36 指で拡大できるか ----
                # 指のある端末として開き直す。ここだけ別の文脈が要る。
                mctx = br.new_context(viewport={"width": 390, "height": 844},
                                      has_touch=True, is_mobile=True,
                                      device_scale_factor=3)
                mp = mctx.new_page()
                mp.goto(url, wait_until="load")
                mp.wait_for_timeout(400)
                _open_map(mp)
                mp.wait_for_timeout(1500)
                MAPTXT = """() => {
                  const m = document.getElementById('map').getScreenCTM();
                  const sc = Math.hypot(m.a, m.b);
                  const small = {};
                  for (const h of document.querySelectorAll('g.hit')) {
                    const t = h.querySelector('text[data-main-label="1"]');
                    if (!t) continue;
                    const cs = getComputedStyle(t);
                    if (cs.display === 'none' || t.getBoundingClientRect().width < 1) continue;
                    const px = +(parseFloat(cs.fontSize) * sc).toFixed(1);
                    if (px < 14) small[px] = (small[px] || 0) + 1;
                  }
                  return {scale:+sc.toFixed(4), small};
                }"""
                REND["mapText"] = mp.evaluate(MAPTXT)
                vpc = mp.evaluate("""()=>{const r=document.getElementById('viewport')
                  .getBoundingClientRect();
                  return {cx:Math.round(r.left+r.width/2), cy:Math.round(r.top+r.height/2)};}""")
                SC = "()=>{const m=document.getElementById('map').getScreenCTM();" \
                     "return +Math.hypot(m.a,m.b).toFixed(4);}"
                base_sc = mp.evaluate(SC)
                zoom_ok = {}
                # ピンチ (指2本を広げる)
                cdp = mctx.new_cdp_session(mp)
                for i, frac in enumerate((0.0, .25, .5, .75, 1.0)):
                    d = 40 + 160 * frac
                    cdp.send("Input.dispatchTouchEvent",
                             {"type": "touchStart" if i == 0 else "touchMove",
                              "touchPoints": [{"x": vpc["cx"]-d, "y": vpc["cy"], "id": 1},
                                              {"x": vpc["cx"]+d, "y": vpc["cy"], "id": 2}]})
                    mp.wait_for_timeout(60)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                mp.wait_for_timeout(500)
                zoom_ok["ピンチ"] = abs(mp.evaluate(SC) - base_sc) > 0.01
                # ダブルタップ
                mp.reload(wait_until="load"); mp.wait_for_timeout(400)
                _open_map(mp); mp.wait_for_timeout(1400)
                b2 = mp.evaluate(SC)
                mp.touchscreen.tap(vpc["cx"], vpc["cy"]); mp.wait_for_timeout(80)
                mp.touchscreen.tap(vpc["cx"], vpc["cy"]); mp.wait_for_timeout(600)
                zoom_ok["ダブルタップ"] = abs(mp.evaluate(SC) - b2) > 0.01
                # ホイール (PC・トラックパッド)
                mp.reload(wait_until="load"); mp.wait_for_timeout(400)
                _open_map(mp); mp.wait_for_timeout(1400)
                b3 = mp.evaluate(SC)
                mp.mouse.move(vpc["cx"], vpc["cy"])
                mp.mouse.wheel(0, -400)
                mp.wait_for_timeout(500)
                zoom_ok["ホイール"] = abs(mp.evaluate(SC) - b3) > 0.01
                REND["zoomGestures"] = zoom_ok
                mp.close(); mctx.close()
                # N32 動きを減らす設定を尊重しているか。0.08秒でも「尊重していない」
                # には違いないが、影響の大小は別に見えるよう秒数も残す。
                rp = br.new_page(viewport={"width": 390, "height": 844})
                rp.emulate_media(reduced_motion="reduce")
                rp.goto(url, wait_until="load")
                rp.wait_for_timeout(1200)
                REND["motion"] = rp.evaluate("""() => {
                  const out = [], seen = new Set();
                  for (const e of document.querySelectorAll('body *')) {
                    const cs = getComputedStyle(e);
                    const td = parseFloat(cs.transitionDuration) || 0;
                    const ad = parseFloat(cs.animationDuration) || 0;
                    if (td <= 0.01 && ad <= 0.01) continue;
                    const cn = e.id ? '#'+e.id
                      : (typeof e.className === 'string' && e.className.trim()
                         ? '.'+e.className.trim().split(/\s+/)[0] : e.tagName.toLowerCase());
                    if (seen.has(cn)) continue; seen.add(cn);
                    out.push({sel:cn, sec:+Math.max(td, ad).toFixed(3)});
                  }
                  return out;
                }""")
                rp.close()
                # N66 二列に並べた信号が、中山バス通り沿いのものだけか (2026-08-14 あみさん指摘)
                # 絞り込みが無く、別の道路の信号 (最遠622m) まで通りの線上に並んでいた。
                # 実DOMの .strip-signal を数える。ソースの正規表現では「本当に出ているか」は分からない。
                sp = br.new_page(viewport={"width": 390, "height": 844})
                sp.goto(url, wait_until="load")
                sp.wait_for_timeout(1200)
                REND["stripSignals"] = sp.evaluate("""() => {
                  const nodes = [...document.querySelectorAll('.strip-signal')];
                  return {shown: nodes.filter(n => !n.hidden).map(n => +n.dataset.y),
                          all: nodes.map(n => +n.dataset.y),
                          geo: (GEO.signals||[]).length};
                }""")
                # N70 二列に出ている店名 (除外指示の照合に使う)
                REND["stripNames"] = sp.evaluate("""() => {
                  return [...document.querySelectorAll('.strip-row .strip-shop-name')]
                    .map(e => (e.textContent||'').trim());
                }""")
                # N69 詳細シートの情報欄で、値の左端が全店そろっているか (2026-08-15)
                # 店を1つずつ開いて、ラベル列の実幅と値の左端を測る。
                REND["factCols"] = sp.evaluate("""async () => {
                  // ⚠ querySelector('.detail-facts') は常に DOM 先頭のカードを返すので、
                  //   店を切り替えながら1つずつ測ると**同じ要素を何度も測ることになる**
                  //   (2026-08-15: それで壊れた版が違反0で通った)。
                  //   まず全店ぶんのカードを作らせてから、**全部の .detail-facts を数える**。
                  for (const h of document.querySelectorAll('g.hit')){
                    h.dispatchEvent(new MouseEvent('click', {bubbles:true}));
                    await new Promise(r => setTimeout(r, 25));
                  }
                  await new Promise(r => setTimeout(r, 200));
                  const out = [];
                  for (const dl of document.querySelectorAll('.detail-facts')){
                    const dd = dl.querySelector('.detail-fact-value');
                    const dt = dl.querySelector('.detail-fact-label');
                    if (!dd || !dt) continue;
                    const card = dl.closest('.detail-card') || dl.parentElement;
                    const h2 = card ? card.querySelector('h2') : null;
                    // 詳細シートは横並びのスライドなので、絶対座標にはカルーセルのずれが乗る。
                    // 測るのは「その店の情報欄の中で、値が左から何pxか」= ラベル列の幅。
                    const base = dl.getBoundingClientRect().left;
                    out.push({name: h2 ? h2.textContent.trim() : '?',
                              labels: [...dl.querySelectorAll('.detail-fact-label')]
                                        .map(e => e.textContent.trim()).join('/'),
                              valueLeft: +(dd.getBoundingClientRect().left - base).toFixed(1),
                              labelLeft: +(dt.getBoundingClientRect().left - base).toFixed(1)});
                  }
                  return out;
                }""")
                sp.close()
                br.close()
        except Exception as e:
            P("!! ブラウザ実測に失敗: %s: %s" % (type(e).__name__, e))
            # 測れなかったものを「違反0件」と読むのが一番危ない。
            # 2026-07-31: UI検査が NameError で丸ごと落ちたのに PASS と出した。
            REND["measureError"] = "%s: %s" % (type(e).__name__, e)
        if srv:
            srv.terminate()

byname = {r["name"]: r for r in (REND["rows"] if REND else [])}
walkby = {r["name"]: r for r in (REND.get("walk", {}).get("rows", []) if REND else [])}

# ---------------- 店ごとの判定 ----------------
P("=" * 78)
P("歩行者ゲート — 「地図を見ながら歩いて正しくその店に行けるか」")
P("=" * 78)
P("道路の塗り幅:", json.dumps({**FILLW, "spine": SPINE_W}, ensure_ascii=False))
P("建物ポリゴン(canvas内): %d / 交差点: %d / 信号: %d (うち交差点上 %d)"
  % (len(BLD), len(XN), len(signals), sum(SIG_OK)))
if REND and REND.get("measureError"):
    P("!! 実測が途中で落ちた: %s" % REND["measureError"])
if REND:
    P("実測倍率: %.4f px/m (デフォルト) / 歩きズーム %.1f px/m を別測" % (REND["pxPerMeter"], WALK_PX_PER_M))
else:
    P("!! ブラウザ実測なし → N3/N4 の画面判定はスキップ (合格にはしない)")
P("")

fails = {k: [] for k in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10",
                         "N11", "N12", "N13", "N14", "N15", "N16", "N17", "N18", "N19",
                         "N20", "N21", "N22", "N23", "N24", "N25", "N26", "N27",
                         "N28", "N29", "N30", "N31", "N32", "N33", "N34", "N35", "N36", "N37", "N38", "N39",
                         "N40", "N41", "N42", "N43", "N44",
                         "N45", "N46", "N47", "N48", "N49", "N50", "N51", "N52", "N53", "N54",
                         "N55", "N56", "N57", "N58", "N59", "N60", "N61",
                         "N62", "N63", "N64", "N65", "N66", "N67", "N68", "N69", "N70")}
band = [s for s in shops if abs(TX(s) - spine_x(TY(s))) < 60]

# 同一住所グループ。ジオコーディング結果が同一なので、見分けるための分離を人工的に
# 入れている。よって真座標との差はその分離量を許容する。
# ハードコードだと取りこぼす (中山5-19-10 は3店・2026-07-30に実際に取りこぼした) ので
# 住所から導出する。真座標が40m以内に固まっているものだけを「同一地点」とみなす。
_by_addr = {}
for _s in shops:
    if _s.get("addr"):
        _by_addr.setdefault(_s["addr"], []).append(_s)
SAME_ADDR_GROUPS = []
for _a, _v in _by_addr.items():
    if len(_v) < 2:
        continue
    _cx = sum(TX(t) for t in _v) / len(_v)
    _cy = sum(TY(t) for t in _v) / len(_v)
    if max(math.hypot(TX(t) - _cx, TY(t) - _cy) for t in _v) <= 40:
        SAME_ADDR_GROUPS.append((_a, [t["name"] for t in _v]))
PAIRED = {n for _a, g in SAME_ADDR_GROUPS for n in g}
P("同一住所グループ (通り沿いの移動制限を免除): %d組" % len(SAME_ADDR_GROUPS))
for _a, _g in SAME_ADDR_GROUPS:
    P("   %s : %s" % (_a, " / ".join(_g)))
P("")
# 移動の上限は「距離」ではなく「向き」で決める。2026-07-30 敵対レビュー2周目の実測より:
#   住所ジオコーディング(gsi_addr)の点は街区の"道路に面した接点"にあるので、
#   建物の奥へ入れる動き = 通りに直交する動き = 正しいセットバック補正。
#   位置関係を壊すのは 通りに沿う動き (どの店の隣か・信号の上下が変わる)。
#   実測: 花祭壇 15.9m のうち沿い0.9m・直交15.8m / ウエルシア 14.4m のうち沿い0.2m・直交14.4m
MAX_ALONG = {"osm:exact": 4.0, "osm:partial": 4.0, "gsi_addr": 8.0, "approx": 8.0}
MAX_CROSS = {"osm:exact": 20.0, "osm:partial": 20.0, "gsi_addr": 20.0, "approx": 25.0}
# 同一住所グループは1点を共有しているので、判別のために街区の奥 (通りに直交) へ
# 広げる必要がある。この許容は「グループの構成員か」で決める。src の値で決めると
# src を書き換えるだけで上限が緩むため (2026-07-30 に実際に10店で発生した)。
MAX_CROSS_PAIRED = 25.0
MAX_WARP_ALONG = 6.0      # 隣接ペアの「通り沿いの間隔」の変化の上限 (m)

for s in shops:
    nm, x, y = s["name"], s["x"], s["y"]

    # N1 建物の中にいる (公園は自分のポリゴン内)
    if nm not in OPEN_SITES:
        if BLD and not in_building(x, y):
            fails["N1"].append(nm)
    else:
        pk = next((p for p in parks if p["name"] == nm), None)
        if pk and not poly_inside(pk["pts"], x, y):
            fails["N1"].append(nm + "(公園ポリゴン外)")

    # N2 道路の帯の内側にいない
    for r in roads:
        if road_d(x, y, r) < road_w(r) / 2.0 + SETBACK:
            fails["N2"].append("%s ← %s (%.1fm)" % (nm, r.get("name") or "(無名 " + r["cls"] + ")", road_d(x, y, r)))
            break

    # N3 歩きズームで★の絵が道路の帯にかからない / 見える大きさである
    w = walkby.get(nm)
    if w:
        rad = w["starMapM"] / 2.0
        hit = next((r for r in roads if road_d(x, y, r) < road_w(r) / 2.0 + rad), None)
        if hit:
            fails["N3"].append("%s ★%.1fm が %s にかかる" % (nm, w["starMapM"], hit.get("name") or hit["cls"]))
        if w["starPxNow"] < MIN_STAR_PX:
            fails["N3"].append("%s ★が%.1fpx (最小%.0f)" % (nm, w["starPxNow"], MIN_STAR_PX))

    # N4 ラベルが自分の★に一意に結びつく
    b = byname.get(nm)
    # 引き出し線で結ばれたラベルは、近さでなく線で対応が分かる (N37 が線を見る)。
    # N14 にだけ除外を入れて N4 に入れ忘れ、8件の誤検出を出した (2026-07-31)。
    if b and b.get("labelShown") and b.get("lx") is not None and not b.get("leader"):
        dself = math.hypot(b["lx"] - x, b["ly"] - y)
        dother = min((math.hypot(b["lx"] - o["x"], b["ly"] - o["y"]) for o in shops if o is not s), default=1e9)
        if dother <= dself:
            fails["N4"].append("%s (自分%.0fm / 他人%.0fm)" % (nm, dself, dother))

    # N5 バス通り沿い: 東西が実座標と一致 + 向かいの店が反対側にいる
    if s in band:
        if side(x, y) != side(TX(s), TY(s)):
            fails["N5"].append("%s 東西が反転" % nm)
        opp = [o for o in band if side(o["x"], o["y"]) != side(x, y) and abs(o["y"] - y) < 40]
        opp_true = [o for o in band if side(TX(o), TY(o)) != side(TX(s), TY(s)) and abs(TY(o) - TY(s)) < 40]
        if opp_true and not opp:
            fails["N5"].append("%s 真では向かいに店があるのに表示では無い" % nm)

    # N6 最寄り信号との南北関係 + その信号が交差点にある
    if s in band and signals:
        k = min(range(len(signals)), key=lambda i: math.hypot(signals[i][0] - TX(s), signals[i][1] - TY(s)))
        sx, sy = signals[k]
        if abs(TY(s) - sy) >= 15 and (TY(s) - sy) * (y - sy) < 0:
            fails["N6"].append("%s 信号との上下が逆" % nm)
        if not SIG_OK[k]:
            d = min((math.hypot(sx - q[0], sy - q[1]) for q in XN), default=1e9)
            fails["N6"].append("%s の目印になる信号(%.0f,%.0f)が交差点にない(%.0fm)" % (nm, sx, sy, d))

# ---- 通りの方向で移動を分解する ----
def street_axis(y):
    h = 2.0
    ax, ay = spine_x(y + h) - spine_x(y - h), 2 * h
    L = math.hypot(ax, ay) or 1.0
    return ax / L, ay / L          # 通りに沿う単位ベクトル


def decompose(s):
    """真座標からの移動を (通りに沿う, 通りに直交) に分ける"""
    tx, ty = TX(s), TY(s)
    dx, dy = s["x"] - tx, s["y"] - ty
    ax, ay = street_axis(ty)
    return abs(dx * ax + dy * ay), abs(dx * ay - dy * ax)


def along_coord(s, use_true=False):
    """通り沿いの位置 (南北の順序を表す1次元座標)"""
    x, y = (TX(s), TY(s)) if use_true else (s["x"], s["y"])
    ax, ay = street_axis(TY(s))
    return x * ax + y * ay


# ---- N7 移動が「通りに沿う」方向に偏っていない (位置関係を壊していない) ----
for s in shops:
    al, cr = decompose(s)
    src = s.get("src", "approx")
    lim_a = MAX_ALONG.get(src, 8.0)
    # 直交の上限は「同一住所グループの構成員か」で決める (src では決めない)
    lim_c = MAX_CROSS_PAIRED if s["name"] in PAIRED else MAX_CROSS.get(src, 25.0)
    if s["name"] not in PAIRED and al > lim_a:
        fails["N7"].append("%s が通りに沿って%.1fm動いた (上限%.0fm / %s)" % (s["name"], al, lim_a, src))
    if cr > lim_c:
        fails["N7"].append("%s が通りに直交して%.1fm動いた (上限%.0fm / %s)" % (s["name"], cr, lim_c, src))

# ---- N8 ★同士が重ならない (歩きズームでの★直径より離れている) ----
star_m = max((r["starMapM"] for r in (REND.get("walk", {}).get("rows", []) if REND else [])), default=4.0)
MIN_SEP = max(3.0, star_m * 1.2)
for i in range(len(shops)):
    for j in range(i + 1, len(shops)):
        a, b = shops[i], shops[j]
        d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        if d < MIN_SEP:
            fails["N8"].append("%s ⇔ %s が%.1fm (★直径%.1fm・最低%.1fm)"
                               % (a["name"], b["name"], d, star_m, MIN_SEP))

# ---- N9 公園ポリゴンとの内外が真座標と一致 ----
for pk in parks:
    for s in shops:
        if poly_inside(pk["pts"], TX(s), TY(s)) != poly_inside(pk["pts"], s["x"], s["y"]):
            fails["N9"].append("%s と %s の内外が真座標と違う" % (s["name"], pk["name"]))

# ---- N10 「通り沿いの間隔」が歪んでいない ----
# 直線距離ではなく通り沿いの1次元間隔で見る。向かい合う店の間隔(通りを横切る距離)は
# セットバックで正しく変わるが、通り沿いの間隔が変わると「どの店の隣か」が壊れる。
bs = sorted(band, key=lambda s: TY(s))
for a, b in zip(bs, bs[1:]):
    if a["name"] in PAIRED and b["name"] in PAIRED:
        continue
    gt = abs(along_coord(a, True) - along_coord(b, True))
    gd = abs(along_coord(a) - along_coord(b))
    if abs(gd - gt) > MAX_WARP_ALONG:
        fails["N10"].append("%s ⇔ %s 通り沿いの間隔 真%.1fm → 表示%.1fm (%+.1fm)"
                            % (a["name"], b["name"], gt, gd, gd - gt))

# ---- N11-N14 概観ズーム (最初に見える倍率) の見やすさ ----
# 歩きズームは N3/N4/N8 が見ている。ここは「開いた瞬間の画面」を見る。
def _rect_d(rc, sx, sy):
    """ラベル矩形の縁から★中心までの最短距離。中心で測ると長い店名が不利になる。"""
    l, t, r, b = rc
    return math.hypot(max(l - sx, 0.0, sx - r), max(t - sy, 0.0, sy - b))


def _seg_rect_hit(x1, y1, x2, y2, rc):
    """線分が矩形と交わるか。引き出し線が他店のラベルを横切るかの判定に使う。"""
    l, t, r, b = rc
    if max(x1, x2) < l or min(x1, x2) > r or max(y1, y2) < t or min(y1, y2) > b:
        return False
    if l <= x1 <= r and t <= y1 <= b:
        return True
    if l <= x2 <= r and t <= y2 <= b:
        return True
    for ax, ay, bx, by in ((l, t, r, t), (r, t, r, b), (r, b, l, b), (l, b, l, t)):
        d1 = (x2-x1)*(ay-y1) - (y2-y1)*(ax-x1)
        d2 = (x2-x1)*(by-y1) - (y2-y1)*(bx-x1)
        d3 = (bx-ax)*(y1-ay) - (by-ay)*(x1-ax)
        d4 = (bx-ax)*(y2-ay) - (by-ay)*(x2-ax)
        if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
            return True
    return False


def _zoom_checks(D, zname, is_default):
    if not D:
        return
    rows = D.get("rows") or []
    rp = D.get("roadPx") or {}
    main = rp.get("main", 0.0)
    s0 = D.get("pxPerMeter") or 1.0
    if is_default:
        if main and main < ROAD_FLOOR_PX:
            fails["N11"].append("%s でバス通りが%.1fpx (通りとして読める床%.0fpx)"
                                % (zname, main, ROAD_FLOOR_PX))
        for r in rows:
            # 主: 指で押す対象として見える大きさか (2026-08-01 これが本題になった)
            if r["starPxNow"] < STAR_MIN_VISIBLE_PX:
                fails["N12"].append("%s ★が%.1fpx しかない (最低%.0f・店名は14-18pxなのに"
                                    "主役の店の印がそれより小さい)"
                                    % (r["name"], r["starPxNow"], STAR_MIN_VISIBLE_PX))
            # 従: 大きくしすぎて地図が印だらけになっていないか
            elif main and r["starPxNow"] / main > STAR_ROAD_MAX:
                fails["N12"].append("%s ★%.1fpx が通り%.1fpx の%.2f倍 (上限%.2f)"
                                    % (r["name"], r["starPxNow"], main,
                                       r["starPxNow"] / main, STAR_ROAD_MAX))
    # N15 その倍率で実際に描かれている帯に★が「乗って」いないか。
    # 帯の幅は「描画px ÷ 倍率」で地図単位に戻す (画面px床が効いている場合を含める)。
    #
    # 判定は2段。「絵が一切触れない」を要求すると物理的に達成できないため
    # (2026-07-30 実測):
    #   既定0.92px/m・★7.2px(地図7.83m/半径3.91m)・バス通り半幅6.5m
    #   → 一切触れないには中心線から 10.41m 必要
    #   実際: 藤倉設備工業 9.21m / BAKERY&BAKE EndRoll 9.41m ← 現実がそれより近い
    #   ★を可読の下限6px(MIN_STAR_PX)まで縮めても必要9.76mで この2店は解消しない
    # ボスの訴えは「道路の上に店舗がある」なので、乗っているか(=中心が帯の内側か)を
    # 不合格とし、先端のかすりは量に上限を置いて歯止めにする。
    DRAWN = {}
    for c in ("main", "major", "mid", "minor"):
        if c in rp:
            DRAWN["road-" + c] = rp[c] / s0
    byn = {r["name"]: r for r in rows}
    for s in shops:
        r = byn.get(s["name"])
        if not r:
            continue
        rad = r["starMapM"] / 2.0
        for rd in roads:
            key = "road-main" if rd.get("guide_spine") else CLSMAP.get(rd["cls"], "road-mid")
            half = DRAWN.get(key, road_w(rd)) / 2.0
            d = road_d(s["x"], s["y"], rd)
            nm2 = rd.get("name") or rd["cls"]
            if d < half:      # ★の中心が帯の内側 = 道路の上に乗っている
                fails["N15"].append("%s の★が %s の帯の上に乗っている (中心線から%.1fm / 帯の半幅%.1fm) (%s)"
                                    % (s["name"], nm2, d, half, zname))
                break
            bite = half + rad - d
            if bite > MAX_STAR_ROAD_BITE:
                fails["N15"].append("%s ★%.1fm が %s に%.1fm食い込む (上限%.1fm) (%s)"
                                    % (s["name"], r["starMapM"], nm2, bite,
                                       MAX_STAR_ROAD_BITE, zname))
                break
    stars = [r for r in rows if r.get("starCx") is not None]
    for r in rows:
        rc = r.get("labelRect")
        if not rc:
            continue
        inside = [o["name"] for o in stars
                  if o["i"] != r["i"] and rc[0] <= o["starCx"] <= rc[2]
                  and rc[1] <= o["starCy"] <= rc[3]]
        if inside:
            fails["N13"].append("%s のラベルが %s の★を内包 (%s)"
                                % (r["name"], "/".join(inside[:2]), zname))
        if r.get("starCx") is None:
            continue
        own = _rect_d(rc, r["starCx"], r["starCy"])
        oth = sorted((_rect_d(rc, o["starCx"], o["starCy"]), o["name"])
                     for o in stars if o["i"] != r["i"])
        # 引き出し線で自分の★と結ばれているラベルは、近さでなく線で対応が分かる。
        # 近さの判定から外すかわりに、線そのものの分かりやすさを N37 で見る。
        if r.get("leader"):
            continue
        if oth and (own > LABEL_MARGIN_MAX * oth[0][0] if oth[0][0] > 0 else own > 0):
            fails["N14"].append("%s のラベル 自分%.0fpx / %s %.0fpx (%s)"
                                % (r["name"], own, oth[0][1], oth[0][0], zname))

    # ---- N37 引き出し線がどの★のものか紛れないか ----
    # 引き出し線は「近さ」の代わりに対応を示すので、線そのものが紛れてはいけない。
    #   ・他店の★のそば (6px以内) を通らない  ・他店のラベルを横切らない
    for r in rows:
        if not r.get("leader"):
            continue
        if r.get("leaderDrawn") is False:
            fails["N37"].append("%s は引き出し線あつかいなのに線が描かれていない "
                                "(ラベルが★から離れたまま、どの★のものか分からない) (%s)"
                                % (r["name"], zname))
        if not r.get("labelRect") or r.get("starCx") is None:
            continue
        rc = r["labelRect"]
        ex, ey = (rc[0] + rc[2]) / 2.0, (rc[1] + rc[3]) / 2.0
        sx, sy = r["starCx"], r["starCy"]
        for o in stars:
            if o["i"] == r["i"]:
                continue
            if seg_d(o["starCx"], o["starCy"], sx, sy, ex, ey) < 6.0:
                fails["N37"].append("%s の引き出し線が %s の★のそばを通る (%s)"
                                    % (r["name"], o["name"], zname))
        for o in rows:
            if o["i"] == r["i"] or not o.get("labelRect"):
                continue
            if _seg_rect_hit(sx, sy, ex, ey, o["labelRect"]):
                fails["N37"].append("%s の引き出し線が %s のラベルを横切る (%s)"
                                    % (r["name"], o["name"], zname))
        # N38 長さ
        _lim = LEADER_MAX_PX_VOICE if r.get("voice") else LEADER_MAX_PX
        _len = math.hypot(ex - sx, ey - sy)
        if _len > _lim:
            fails["N38"].append("%s の引き出し線が %.0fpx (上限%.0f%s) — 地図を横切る配線になる (%s)"
                                % (r["name"], _len, _lim,
                                   "・こどもの声" if r.get("voice") else "", zname))

    # ---- N39 引き出し線で外へ運んだ結果、名前が縁で切れていないか ----
    # 画面の縁で名前が切れること自体は、地図を動かせる以上ふつうのこと。
    # 問題なのは「置き場が無いので外へ運んだら画面の外だった」場合で、
    # それは配置の失敗。線を引かない普通のラベルは対象にしない。
    for r in rows:
        if not r.get("leader"):
            continue
        if not r.get("starInView") or not r.get("labelRect"):
            continue
        cut = r.get("labelCutPx") or 0
        if cut > 1:
            w = r["labelRect"][2] - r["labelRect"][0]
            fails["N39"].append("%s は引き出し線で運んだ名前の %dpx / %dpx が画面の外に出ている (%s)"
                                % (r["name"], cut, round(w), zname))


if REND:
    _zoom_checks(REND, "既定ズーム", True)
    _zoom_checks(REND.get("walk"), "歩きズーム", False)
    # N17 固定UI (お店一覧ボタン / ズーム操作) が店名を覆っていないか。
    # 2026-07-30: 西原歯科医院 のラベルが「お店一覧」に36%覆われていた。
    # 表示域の端で切れるぶんは正常なので除いてある (パンで届く)。
    for c in (REND.get("uiCovered") or []):
        if c["pct"] >= 10:
            fails["N17"].append("%s のラベルが固定UIに%d%%覆われている (既定ズーム)"
                                % (c["name"], c["pct"]))

    # N18 こどもの声バッジが自分の★に一意に結びつくか。
    # 2026-07-30: 11個中4個が他店の★のほうが近く、声の持ち主を取り違える。
    # バッジは★から約17.5m (地図単位固定) の位置に出るが、隣の店は8.4mまで近づける。
    # N19 信号アイコンと★/ラベルが重なっていないか。
    # 描画順は gRoads(信号) → gShops(★/ラベル) なので、隠れるのは信号のほう。
    # 店は読めるが、N6 で「歩く時の目印」として使う信号が読めなくなる。
    # 信号は22m (道路13mの1.68倍) の地図単位固定で、カットショップ NOBU と重なっていた。
    for zk, zn in (("", "既定ズーム"), ("walk", "歩きズーム")):
        D = REND if not zk else REND.get(zk)
        if not D:
            continue
        for b in (D.get("badges") or []):
            if b.get("own") and b.get("nearest") and b["nearest"] != b["own"]:
                fails["N18"].append("%s の声バッジが %s の★のほうに近い (自分%.0fpx / 相手%.0fpx) (%s)"
                                    % (b["own"], b["nearest"], b["ownPx"], b["nearestPx"], zn))
        for h in (D.get("sigHit") or []):
            fails["N19"].append("信号アイコンが %s の%sと重なり、信号が読めない (%s)"
                                % (h["n"], h["kind"], zn))

    # ---- N20-N24 UI/UX。画面幅を変えて操作部だけ見る ----
    _tap_bad, _txt_bad = {}, {}
    for u in (REND.get("ui") or []):
        vw = u["vw"]
        dev = "%dx%d" % (vw, u.get("vh", 0))
        # N20/N21 は画面の状態ごとの総なめ。直す場所はセレクタ単位なので、
        # 端末・状態をまたいで1件にまとめる (同じ1箇所を136件に数えても読めないだけ)。
        for t in (u.get("sweep") or {}).get("taps", []):
            e = _tap_bad.setdefault(t["sel"], {"txt": t["txt"], "w": t["w"], "h": t["h"], "where": []})
            e["w"] = min(e["w"], t["w"]); e["h"] = min(e["h"], t["h"])
            e["where"].append("%s %s" % (dev, t["state"]))
        for t in (u.get("sweep") or {}).get("texts", []):
            e = _txt_bad.setdefault(t["sel"], {"txt": t["txt"], "fs": t["fs"],
                                               "attrib": t["attrib"], "where": []})
            e["fs"] = min(e["fs"], t["fs"])
            e["where"].append("%s %s" % (dev, t["state"]))
        if u.get("fontPx", 16) != 16:
            # 文字サイズ行はここだけ通す = 主の内容の高さ。
            # 地図の割合や押し位置は 16px 前提の床なので当てない。
            if u.get("portrait", True):
                # 330px という床は既定16pxで実測して決めた数字で、文字を2倍にした人に
                # 同じ絶対値を要求するのは筋が通らない (文字が大きいぶん1件が高い)。
                # 見たいのは「入口で店がいくつ目に入るか」なので件数で見る。
                if u.get("shopsInView", 99) < 3:
                    fails["N23"].append("入口で見えている店が%d件しかない (最低3件) [%dx%d 文字%dpx]"
                                        % (u.get("shopsInView", 0), vw, u.get("vh", 0), u["fontPx"]))
            continue
        # 文字を大きくして測った行は、ここから下の寸法の検査には渡さない。
        # 床 (主の内容が画面の何%か等) は 16px 前提で実測して決めたもので、
        # 200% の文字に同じ床を当てると達成不能な要求になる。
        # 文字サイズで見たいのは「切れていないか」であって「何%占めるか」ではない。
        if u.get("fontPx", 16) != 16:
            continue
        for o in u["offscreen"]:
            fails["N22"].append("%s (%s) が画面の外にある [幅%d]" % (o["nm"], o["txt"], vw))
        for c in (u.get("credits") or []):
            fails["N25"].append("「%s」が固定UIに%d%%覆われている [幅%d]"
                                % (c["txt"], c["pct"], vw))
        # N23 / N26 は縦向きだけ。横向きは「地図が主」でなく「一覧が主」の使い方になり、
        # 同じ床を当てると達成不能な要求になる (縦向きの床は実測で導出したもの)。
        if u.get("portrait", True):
            # 既定の画面 = 二列表示。主の内容がこれだけの高さを持つこと
            if u.get("mainRatio", 0) < MAP_MIN_RATIO:
                fails["N23"].append("主の内容 (通り沿いの二列) が画面の%.0f%%しかない (床%.0f%%) [%dx%d]"
                                    % (u.get("mainRatio", 0) * 100, MAP_MIN_RATIO * 100,
                                       vw, u.get("vh", 0)))
            if u.get("mainPx", 0) < MAP_MIN_PX:
                fails["N23"].append("主の内容の高さが%dpxしかない (床%.0fpx) [%dx%d]"
                                    % (u.get("mainPx", 0), MAP_MIN_PX, vw, u.get("vh", 0)))
            # 地図を開いた時は地図がこれだけの高さを持つこと
            if u["mapRatio"] < MAP_MIN_RATIO:
                fails["N23"].append("地図を開いた時に地図が画面の%.0f%%しかない (床%.0f%%) [%dx%d]"
                                    % (u["mapRatio"] * 100, MAP_MIN_RATIO * 100, vw, u.get("vh", 0)))
            if u.get("mapH", 0) < MAP_MIN_PX:
                fails["N23"].append("地図を開いた時の高さが%dpxしかない (床%.0fpx) [%dx%d]"
                                    % (u["mapH"], MAP_MIN_PX, vw, u.get("vh", 0)))
            for n in (u.get("voiceHidden") or []):
                fails["N26"].append("%s のこどもの声ラベルが出ていない [%dx%d]"
                                    % (n, vw, u.get("vh", 0)))
        else:
            if u.get("mapH", 0) < LAND_MAP_MIN_PX or u["mapRatio"] < LAND_MAP_MIN_RATIO:
                fails["N23"].append("横向きで地図が%dpx (画面の%.0f%%) しかない "
                                    "(床%.0fpx / %.0f%%) [%dx%d]"
                                    % (u.get("mapH", 0), u["mapRatio"] * 100,
                                       LAND_MAP_MIN_PX, LAND_MAP_MIN_RATIO * 100,
                                       vw, u.get("vh", 0)))
        lay = u.get("layout") or {}
        if not lay.get("calls"):
            fails["N27"].append("ラベル配置の時間を測れなかった (呼び出し%s回/ズームボタン%s個) [%dx%d]"
                                % (lay.get("calls"), lay.get("buttons"), vw, u.get("vh", 0)))
        elif lay.get("worst", 0) > MAX_LAYOUT_MS:
            fails["N27"].append("ズーム1回のラベル配置に%.0fms かかる (上限%.0fms) [%dx%d]"
                                % (lay["worst"], MAX_LAYOUT_MS, vw, u.get("vh", 0)))
    # ---- N30 / N31 / N34 セレクタ単位でまとめる ----
    _c, _g, _e = {}, {}, {}
    for u in (REND.get("ui") or []):
        _dev = "%dx%d" % (u["vw"], u.get("vh", 0))
        sw = u.get("sweep") or {}
        for it in sw.get("contrast", []):
            k = it["sel"]
            e = _c.setdefault(k, {**it, "where": []})
            e["ratio"] = min(e["ratio"], it["ratio"])
            e["where"].append("%s %s" % (_dev, it["state"]))
        for it in sw.get("gaps", []):
            k = (it["a"], it["b"])
            e = _g.setdefault(k, {**it, "where": []})
            e["gap"] = min(e["gap"], it["gap"])
            e["where"].append("%s %s" % (_dev, it["state"]))
        for it in sw.get("emoji", []):
            k = (it["sel"], it["ch"])
            e = _e.setdefault(k, {**it, "where": []})
            e["where"].append("%s %s" % (_dev, it["state"]))
    def _w(rows):
        u = sorted(set(rows))
        return "どの端末でも" if len(u) >= 12 else u[0] + ("" if len(u) == 1 else " ほか%d" % (len(u)-1))
    for k, e in sorted(_c.items(), key=lambda kv: kv[1]["ratio"]):
        fails["N30"].append("%s (%s) が %.2f:1 (必要%.1f / %.1fpx) [%s]"
                            % (k, e["txt"], e["ratio"], e["need"], e["px"], _w(e["where"])))
    for k, e in sorted(_g.items(), key=lambda kv: kv[1]["gap"]):
        if e["gap"] < 0:
            fails["N44"].append("「%s」と「%s」が 横%dpx 縦%dpx 重なっている [%s]"
                                % (e["a"], e["b"], e.get("ox", 0), e.get("oy", 0),
                                   _w(e["where"])))
        else:
            # どこにあった2つなのかを出す。位置が無いと原因を追えない (2026-08-04)
            fails["N31"].append("「%s」%s と「%s」%s が %.1fpx しか離れていない (最小%.0f) [%s]"
                                % (e["a"], e.get("ra") or "", e["b"], e.get("rb") or "",
                                   e["gap"], TAP_GAP_MIN_PX, _w(e["where"])))
    for k, e in sorted(_e.items()):
        fails["N34"].append("%s (%s) がアイコンに絵文字 %s を使っている [%s]"
                            % (e["sel"], e["txt"], e["ch"], _w(e["where"])))
    # ---- N35 地図の店名の大きさ ----
    _mt = REND.get("mapText") or {}
    for px, n in sorted((_mt.get("small") or {}).items(), key=lambda kv: float(kv[0])):
        fails["N35"].append("地図の店名 %d件が %spx (床%.0fpx)。UIの文字は14px以上なのに "
                            "地図だけ小さい" % (n, px, MAP_LABEL_MIN_PX))
    # ---- N36 指で地図を拡大できるか ----
    _zg = REND.get("zoomGestures")
    if _zg is not None:
        for g in ZOOM_GESTURES:
            if not _zg.get(g):
                fails["N36"].append("%s で地図が拡大しない (地図なのに指で寄せられない)" % g)
    # ---- N32 動きを減らす設定 ----
    for m in (REND.get("motion") or []):
        fails["N32"].append("動きを減らす設定でも %s が %.2f秒 動く" % (m["sel"], m["sec"]))
    # ---- N33 地図を飛ばす手段 / タブ順 ----
    for u in (REND.get("ui") or []):
        bp = (u.get("sweep") or {}).get("bypass")
        if not bp:
            continue
        _dev = "%dx%d" % (u["vw"], u.get("vh", 0))
        if bp["inMap"] > 10 and not bp["skip"]:
            fails["N33"].append("地図の★が%d件Tabの通り道にあり、飛ばすリンクが無い "
                                "(操作要素%d件) [%s]" % (bp["inMap"], bp["total"], _dev))
        for r in bp["reordered"]:
            fails["N33"].append("%s (%s) は CSS order:%s で見た目の順を変えているため "
                                "Tab の順と食い違う [%s]"
                                % (r["sel"], r["nm"], r["order"], _dev))
        break                      # 端末ごとに同じ話なので1台分だけ出す
    kpar = REND.get("keyboardParity") or {}
    _unreach = [n for n in (kpar.get("liveOutside") or [])
                if n not in set(kpar.get("reachedByTab") or [])]
    if _unreach:
        fails["N33"].append("お店一覧を開くと %s が指では押せる (一覧に効く) のに "
                            "Tab では届かない — キーボードだけの人がその機能を使えない"
                            % "／".join(_unreach[:5]))

    # N57 一覧の店名が語の途中で折り返されていないか (2026-08-09 ボスの実機写真)
    _lone = {}
    for u in (REND.get("ui") or []):
        for it in (u.get("sweep") or {}).get("lone", []):
            _lone.setdefault((it["txt"], it["line"]), []).append(
                "%dx%d %s" % (u["vw"], u.get("vh", 0), it["state"]))
    for (txt, line), where in sorted(_lone.items()):
        fails["N57"].append("一覧の「%s」が語の途中「%s」で行が分かれる [%s]"
                            % (txt, line, sorted(set(where))[0]))

    # N58 ボタンの文字に「1文字だけの行」ができていないか (2026-08-10・同型3回目)
    _orph = {}
    for u in (REND.get("ui") or []):
        for it in (u.get("sweep") or {}).get("orphan", []):
            _orph.setdefault((it["sel"], it["txt"], it["ch"]), []).append(
                "%dx%d %s" % (u["vw"], u.get("vh", 0), it["state"]))
    for (sel_, txt, ch), where in sorted(_orph.items()):
        _w = sorted(set(where))
        fails["N58"].append("%s の「%s」が折り返され、「%s」だけが1行に取り残される [%s]"
                            % (sel_, txt, ch, _w[0] + ("" if len(_w) == 1 else " ほか%d" % (len(_w)-1))))

    # N59 箱が中身の文字を切っていないか (2026-08-10・あみさん「拡大すると文字が大変」)
    # 高さを px で決め打ちした箱に、端末の文字設定で伸びる文字を入れると起きる。
    # どの端末・どの文字サイズで出たかを添える (16px でも出るなら常時の欠陥)。
    _cut = {}
    for u in (REND.get("ui") or []):
        for it in (u.get("sweep") or {}).get("cutbox", []):
            _cut.setdefault((it["sel"], it["txt"]), []).append(
                ("%dx%d %s" % (u["vw"], u.get("vh", 0), it["state"]), it["dw"], it["dh"]))
    for (sel_, txt), rows in sorted(_cut.items()):
        _w = sorted(set(r[0] for r in rows))
        _dw, _dh = max(r[1] for r in rows), max(r[2] for r in rows)
        _lack = " / ".join(x for x in ("横%dpx" % _dw if _dw else "", "縦%dpx" % _dh if _dh else "") if x)
        fails["N59"].append("%s が中の「%s」を切っている (%s 足りない) [%s]"
                            % (sel_, txt, _lack,
                               _w[0] + ("" if len(_w) == 1 else " ほか%d" % (len(_w)-1))))

    # N60 同じ行で店名が住所より小さくなっていないか (2026-08-10)
    _rank = {}
    for u in (REND.get("ui") or []):
        for it in (u.get("sweep") or {}).get("rank", []):
            _rank.setdefault((it["sel"], it["name"], it["addr"]), []).append(
                "%dx%d %s" % (u["vw"], u.get("vh", 0), it["state"]))
    for (sel_, nm, ad), where in sorted(_rank.items()):
        _w = sorted(set(where))
        fails["N60"].append("%s の店名が%.1fpx・住所が%.1fpx で、住所の方が大きい [%s]"
                            % (sel_, nm, ad,
                               _w[0] + ("" if len(_w) == 1 else " ほか%d" % (len(_w)-1))))

    # N61 方位記号の針が北を向いているか (2026-08-10・あみさん指摘)
    # 2026-08-10: 測定キーが欠けたら黙って0件になっていた (N57/N58 と同型)。
    # 「測っていない」を「違反なし」と読ませない。地図を開ける画面の数だけ
    # 測定が揃っていることを先に要求する。
    _cmp = {}
    _want_cmp = [u for u in (REND.get("ui") or []) if u.get("mapFrame") is not None]
    # --devices で絞った時は地図を開く行が入らないことがある。絞った実行は
    # そもそも合格を名乗れないので、ここで「測れていない」とは言わない。
    if (not A.devices and (REND.get("ui") or [])
            and not any(u.get("compass") for u in (REND.get("ui") or []))):
        fails["N61"].append("方位記号を一度も測れていない (地図が開かなかった)")
    _have_cmp = [u for u in _want_cmp if u.get("compass")]
    if _want_cmp and len(_have_cmp) != len(_want_cmp):
        fails["N61"].append("方位記号を測れていない画面が %d/%d ある (測定漏れを合格にしない)"
                            % (len(_want_cmp) - len(_have_cmp), len(_want_cmp)))
    for u in (REND.get("ui") or []):
        c = u.get("compass")
        if not c:
            continue
        if not c.get("ok"):
            _cmp.setdefault(("測れない", c.get("why", "?"), 0), []).append("%dx%d" % (u["vw"], u.get("vh", 0)))
        elif c.get("off", 0) > 3:
            _cmp.setdefault(("ずれ", c["actual"], c["want"]), []).append("%dx%d" % (u["vw"], u.get("vh", 0)))
    for (kind, a, b), where in sorted(_cmp.items(), key=lambda kv: str(kv[0])):
        _w = sorted(set(where))
        if kind == "測れない":
            fails["N61"].append("方位記号を測れない (%s) [%s]" % (a, _w[0]))
        else:
            fails["N61"].append("針が真上から%.1f度を指しているが、北は%.1f度の向き (%.1f度ずれ) [%s]"
                                % (a, b, abs(((a - b) + 180) % 360 - 180),
                                   _w[0] + ("" if len(_w) == 1 else " ほか%d" % (len(_w)-1))))

    for _k, _n, _fmt in (("wrap", "N28", "%s (%s) が「%s」で改行される [%s]"),
                         ("clip", "N29", "%s (%s) が入れ物に収まらない 必要%dpx / 幅%dpx [%s]")):
        _seen = {}
        for u in (REND.get("ui") or []):
            for it in (u.get("sweep") or {}).get(_k, []):
                _seen.setdefault(it["sel"], []).append((it, "%dx%d %s" % (u["vw"], u.get("vh", 0), it["state"])))
        for sel_, rows in sorted(_seen.items()):
            it = rows[0][0]
            where = sorted(set(r[1] for r in rows))
            wtxt = "どの端末でも" if len(where) >= 12 else where[0] + ("" if len(where) == 1 else " ほか%d" % (len(where)-1))
            if _n == "N28":
                fails[_n].append(_fmt % (sel_, it["txt"], it["at"], wtxt))
            else:
                fails[_n].append(_fmt % (sel_, it["txt"], it["need"], it["has"], wtxt))

    # ---- N40-N43 通り沿いの二列表示 ----
    # 位置の正しさ (西/東・順番・向かい合わせ) は地図で検証済みの資産。
    # 見せ方が変わってもそれが保たれているかを、画面の実測で確かめる。
    # 2026-07-31 改訂。48px は「実測の最大が37.1pxだったから」で置いた数字だったが、
    # カードの高さが45pxなので 48px ずれると上下の重なりがゼロになり、
    # 人の目には「向かい合っている」と読めない。しかも最適化がこの上限まで
    # 押し込むので、閾値がそのまま設計になってしまった (柏屋と河村内科外科クリニックは
    # 実際1m差なのに47.0pxで通った)。
    #
    # 正しい問いは「画面のズレが小さいか」ではなく「画面のズレが実際のズレを表しているか」。
    # 実際の南北差 Δy を画面に写すと Δy × 縦縮尺 px になる。そこからの誤差で見る。
    # 誤差24px = カード45pxの約半分。ここまでなら2枚は上下に重なって残るので
    # 「向かい合っている」と読める。
    FACING_ERR_MAX_PX = 24.0
    # ただし片側に3枚が密集している所などは、カード45px+隙間8pxの積み上げが
    # 実際の間隔より広くなり、どう並べても誤差を消せない (花祭壇の向かいは3枚で
    # 最低106px要るが、全部を近くに置ける幅は足りない)。
    # そういう組は「隠す」のでなく「ずらしてあることを見せる」= 引き出し線を出す。
    # 線が出ていれば実際の位置が読めるので合格とするが、線があっても離れすぎては
    # 読めないので、幾何が強いる最大 (花祭壇の3枚で53px) までに限る。
    FACING_ERR_LEADER_MAX = 56.0
    _true_side, _true_y = {}, {}
    for _s in shops:
        _true_side[_s["name"]] = 1 if TX(_s) >= spine_x(TY(_s)) else -1
        _true_y[_s["name"]] = TY(_s)
    _byidx = {i: sh for i, sh in enumerate(shops)}
    _strip_done = False
    for u in (REND.get("ui") or []):
        st = u.get("strip")
        if not st or _strip_done:
            continue
        _strip_done = True
        dev = "%dx%d" % (u["vw"], u.get("vh", 0))
        rows = st.get("rows") or []
        if not rows:
            fails["N40"].append("二列表示の行が1つも見つからない (.strip-row) [%s]" % dev)
            continue
        # N40 東西
        for r in rows:
            sh = _byidx.get(r["i"])
            if not sh:
                fails["N40"].append("行の data-i=%s が店に対応しない [%s]" % (r["i"], dev))
                continue
            want = "east" if _true_side[sh["name"]] > 0 else "west"
            if r["side"] != want:
                fails["N40"].append("%s が %s 側に出ている (真は %s 側) [%s]"
                                    % (sh["name"], "東" if r["side"] == "east" else "西",
                                       "東" if want == "east" else "西", dev))
        # 2026-08-15: 二列から外す指示の店 (strip_hide) は行数に数えない (N70 が別で見る)
        _strip_expected = len([s2 for s2 in shops if not s2.get("strip_hide")])
        if len(rows) != _strip_expected:
            fails["N40"].append("二列表示の行が%d件 (出るはずは%d件・店は%d件) [%s]"
                                % (len(rows), _strip_expected, len(shops), dev))
        # N41 並び順 (通り沿いの節だけ。離れた節は別の並びでよい)
        near = [r for r in rows if not r.get("far") and _byidx.get(r["i"])]
        for side in ("west", "east"):
            col = [r for r in near if r["side"] == side]
            by_screen = sorted(col, key=lambda r: r["top"])
            by_true = sorted(col, key=lambda r: _true_y[_byidx[r["i"]]["name"]])
            for a, b in zip(by_screen, by_true):
                if a["i"] != b["i"]:
                    fails["N41"].append("%s 側の並び順が真の順番と違う (%s の位置に %s) [%s]"
                                        % ("東" if side == "east" else "西",
                                           _byidx[b["i"]]["name"], _byidx[a["i"]]["name"], dev))
                    break
        # N42 向かい合わせ
        pos = {r["i"]: r for r in near}
        # 同じ側ごとに「最良の詰め方」を組み直す (幾何が強いるズレを知るため)
        _best = {}
        for _side in ("west", "east"):
            _col = sorted([r for r in near if r["side"] == _side],
                          key=lambda r: _true_y[_byidx[r["i"]]["name"]])
            _k = st.get("pxPerM") or 0
            _items = [{"ideal": _true_y[_byidx[r["i"]]["name"]] * _k, "h": r["h"]} for r in _col]
            for _r, _c in zip(_col, _best_centers(_items, STRIP_GAP)):
                _best[_r["i"]] = _c
        for i, a in enumerate(shops):
            for b in shops[i+1:]:
                if abs(TY(a) - TY(b)) > 20:
                    continue
                if _true_side[a["name"]] == _true_side[b["name"]]:
                    continue
                ia = next((k for k, v in _byidx.items() if v is a), None)
                ib = next((k for k, v in _byidx.items() if v is b), None)
                ra, rb = pos.get(ia), pos.get(ib)
                if not ra or not rb:
                    continue
                # 画面のズレが、実際の南北差を写したものになっているか
                k = st.get("pxPerM")
                if not k:
                    fails["N42"].append("二列の縦縮尺が読めない (STRIP_PX_PER_M) [%s]" % dev)
                    break
                ca = ra["top"] + ra["h"]/2
                cb = rb["top"] + rb["h"]/2
                # 北 (yが小さい) が上に来るので、真のズレは符号つきで比べる
                want = (TY(b) - TY(a)) * k
                err = abs((cb - ca) - want)
                if err > FACING_ERR_MAX_PX:
                    # ずらしてあることを引き出し線で見せているなら実位置は読めるが、
                    # 線があっても離れすぎては読めない。上限は幾何が強いる分まで:
                    # 花祭壇の向かいの3枚は 2×(45+8)=106px 必要で、中央に置いても
                    # 端は53pxずれる。これが「どうやっても消えないズレ」の最大値。
                    # 2026-08-10: 引き出し線を消した (ボス指示) ので、「線があるから
                    # 実位置が読める」という免除の根拠が消えた。表示を消したのに
                    # 検査だけ免除を残すと、最大56px=約43mのズレを黙って通す。
                    # 免除は削除した。代わりに「幾何が強いる分」と比べる。
                    # 1枚のカードが向かいの複数店と同時に高さを合わせることはできない。
                    # 花祭壇は向かいに3店あり、それぞれが要求する置き場が71px散らばる。
                    # どこに置いても、少なくとも散らばりの半分は必ず誰かとの誤差になる。
                    # (最初この事情を入れずに書き、通るはずのない床を要求していた)
                    def _spread(idx, other_side):
                        want_pos = []
                        for _o in shops:
                            if _o is _byidx.get(idx):
                                continue
                            _oi = next((kk for kk, vv in _byidx.items() if vv is _o), None)
                            if _oi is None or _oi not in _best:
                                continue
                            if pos.get(_oi, {}).get("side") != other_side:
                                continue
                            if abs(TY(_o) - TY(_byidx[idx])) > 20:
                                continue
                            want_pos.append(_best[_oi] - (TY(_o) - TY(_byidx[idx])) * k)
                        return (max(want_pos) - min(want_pos)) / 2.0 if len(want_pos) > 1 else 0.0
                    forced = max(_spread(ia, rb["side"]), _spread(ib, ra["side"]))
                    # 余裕6px の内訳: 幾何の床は「いちばん悪い相手との誤差を最小にする置き方」
                    # (両端の中点) で出しているが、アプリは相手全員の平均に置く。
                    # どちらも妥当な方針で、最悪値は数px 変わる。加えて高さの実測は0.1px刻み。
                    # ここを詰めるほどの利得は無いが、6px を超えたら置き方の問題として落とす。
                    _limit = max(FACING_ERR_MAX_PX, forced + 6.0)
                    if err <= _limit:
                        continue
                    fails["N42"].append("%s と %s は南北差%.0fm (画面なら%.0fpx) の向かい合わせ"
                                        "なのに 画面では%.0fpx ずれていて 誤差%.0fpx "
                                        "(許容%.0f = 幾何が強いる最良%.0f + 3) [%s]"
                                        % (a["name"], b["name"], abs(TY(a)-TY(b)), abs(want),
                                           abs(cb - ca), err, _limit, forced, dev))
        # N43 押すものが親指の届く範囲 (画面の下半分)
        for c in (st.get("ctl") or []):
            if c["cy"] < st["h"] * 0.5:
                fails["N43"].append("「%s」が画面の上から%d/%dpx の位置にある "
                                    "(片手だと親指が届かない) [%s]"
                                    % (c["nm"], c["cy"], st["h"], dev))

    # ---- N45-N50 (2026-07-31) 絵を見て分かることを数字にしたもの ----
    _seen_gap, _seen_filter, _seen_word = set(), set(), set()
    _seen_decor = set()
    for u in (REND.get("ui") or []):
        dev = "%dx%d" % (u["vw"], u.get("vh", 0))
        port = u.get("portrait")

        # N45 地図の上に何も乗っていない / N46 見出しと戻る手段 / N47 縁で切れない
        mf = u.get("mapFrame")
        if mf and mf.get("vp"):
            for o in sorted(mf.get("occ") or [], key=lambda x: -x["area"]):
                fails["N45"].append("地図の上に %s が %s (%dpx²) 乗っている %s [%s]"
                                    % (o["sel"], o.get("why", ""), o["area"],
                                       o["rect"], dev))
            if port and mf.get("openRatio", 0) < MAP_OPEN_MIN_RATIO:
                fails["N45"].append("地図を開いても地図は画面の%.0f%%しかない (最低%.0f%%) [%s]"
                                    % (mf["openRatio"] * 100, MAP_OPEN_MIN_RATIO * 100, dev))
            band = mf.get("band") or [0, 0]
            if not (mf.get("heading") or []):
                fails["N46"].append("地図の画面に見出しが1つも無い (今どこにいるか分からない) [%s]" % dev)
            back = mf.get("back") or []
            top_back = [b for b in back if b["cy"] < band[0] + 8 or b["cy"] > band[1] - 8]
            if not back:
                fails["N46"].append("地図から戻る手段が画面に無い [%s]" % dev)
            elif not top_back:
                fails["N46"].append("地図から戻る手段が地図の中に埋もれている "
                                    "(帯の外に置く) [%s]" % dev)
            # N52 地図が枠を埋めているか (縦向きのみ。横向きは前提が違う)
            if port and mf.get("fillRatio") is not None:
                if mf["fillRatio"] < MAP_FILL_MIN_RATIO:
                    fails["N52"].append("地図が枠の高さ%dpx に対して%dpx しかなく、"
                                        "下に%dpx の空白がある (枠の%.0f%%・最低%.0f%%) [%s]"
                                        % (mf.get("frameH", 0), mf.get("svgH", 0),
                                           mf.get("deadPx", 0), mf["fillRatio"] * 100,
                                           MAP_FILL_MIN_RATIO * 100, dev))
            for c in (mf.get("cut") or []):
                fails["N47"].append("地図の「%s」が%s %s [%s]"
                                    % (c["t"], c["why"], c["rect"], dev))

        # N48 カード同士の隙間
        sg = u.get("stripGaps")
        if sg and sg.get("pairs") and dev not in _seen_gap:
            _seen_gap.add(dev)
            for t in (sg.get("tight") or [])[:12]:
                fails["N48"].append("「%s」と「%s」の隙間が%.1fpx (最低%.0f・境目が見えない) [%s]"
                                    % (t["a"], t["b"], t["gap"], STRIP_GAP_MIN_PX, dev))
            if len(sg.get("tight") or []) > 12:
                fails["N48"].append("ほか%d組も隙間が%.0fpx未満 [%s]"
                                    % (len(sg["tight"]) - 12, STRIP_GAP_MIN_PX, dev))

        # N49 絞り込んだとき1画面に何件見えるか
        for f in (u.get("filterView") or []):
            key = dev + f["how"]
            if key in _seen_filter:
                continue
            _seen_filter.add(key)
            # 2026-08-15: 床6件は縦持ちの基準。横向き (二列の高さ196px) では
            # タップ領域44pxの床と両立できず、物理的に置ける行数が6未満になる。
            # 以前はカーブスが西列に居て左右2列で数を稼げていたが、クライアント指示で
            # 二列から外した結果、医療の絞り込みが縦1列になり「6件」が不可能になった。
            # 床は「物理的に置ける行数」で丸める (縦持ちでは今までどおり6)。
            _dbg = f.get("dbg") or {}
            _step = (_dbg.get("rowH") or 45) + 8
            _room = (_dbg.get("svH") or 0) - max(0, (_dbg.get("firstTop") or 0) - (_dbg.get("svTop") or 0))
            _phys = max(1, _room // _step + 1) if _room > 0 else FILTER_VISIBLE_MIN
            want = min(f["total"], FILTER_VISIBLE_MIN, _phys)
            if f["total"] and f["visible"] < want:
                fails["N49"].append("%s で%d件のはずが、画面には%d件しか見えない "
                                    "(最低%d件) [%s] %s"
                                    % (f["how"], f["total"], f["visible"], want, dev,
                                       json.dumps(f.get("dbg") or {}, ensure_ascii=False)))

        # N51 通りの帯の中で 道路名・信号 どうしが重なっていないか
        for sc in (u.get("stripDecor") or []):
            key51 = dev + sc["how"]
            if key51 in _seen_decor:
                continue
            _seen_decor.add(key51)
            for b in (sc.get("bad") or [])[:6]:
                fails["N51"].append("%s で %s と %s が 横%dpx 縦%dpx 重なっている "
                                    "(読めない字の塊になる) [%s]"
                                    % (sc["how"], b["a"], b["b"], b["ox"], b["oy"], dev))
            if len(sc.get("bad") or []) > 6:
                fails["N51"].append("%s で ほか%d組も重なっている [%s]"
                                    % (sc["how"], len(sc["bad"]) - 6, dev))

        # N50 探しそうな言葉が、当たるべき店に当たるか
        _anchor = dict(SEARCH_WORDS)
        for s in (u.get("searchWords") or []):
            if s["w"] in _seen_word:
                continue
            want = _anchor.get(s["w"], "")
            names = s.get("names") or []
            if s["hits"] == 0:
                _seen_word.add(s["w"])
                fails["N50"].append("「%s」で検索しても0件 (店名にその字が無いだけで、"
                                    "その店はある: %s) [%s]" % (s["w"], want, dev))
            elif want and not any(want in n for n in names):
                _seen_word.add(s["w"])
                fails["N50"].append("「%s」で%d件出るが「%s」が入っていない (出たのは %s) [%s]"
                                    % (s["w"], s["hits"], want,
                                       "、".join(names[:4]) or "なし", dev))
            elif s["hits"] > SEARCH_HITS_MAX:
                _seen_word.add(s["w"])
                fails["N50"].append("「%s」で%d件も出る (%d件まで・絞れていない) [%s]"
                                    % (s["w"], s["hits"], SEARCH_HITS_MAX, dev))

    def _where(w):
        # 全端末・全状態に出るなら「どこでも」。そうでなければ最初の1つを示す。
        u = sorted(set(w))
        return "どの端末でも" if len(u) >= 12 else u[0] + ("" if len(u) == 1 else " ほか%d" % (len(u) - 1))

    for sel_, e in sorted(_tap_bad.items(), key=lambda kv: min(kv[1]["w"], kv[1]["h"])):
        fails["N20"].append("%s (%s) が %.0fx%.0fpx (最小%.0f) [%s]"
                            % (sel_, e["txt"], e["w"], e["h"], TAP_MIN_PX, _where(e["where"])))
    for sel_, e in sorted(_txt_bad.items(), key=lambda kv: kv[1]["fs"]):
        lim = ATTRIB_MIN_PX if e["attrib"] else TEXT_MIN_PX
        fails["N21"].append("%s (%s) が %.1fpx (床%.0f) [%s]"
                            % (sel_, e["txt"], e["fs"], lim, _where(e["where"])))

    # N24 印を押したらその店が開く (2026-08-08 ボス指示「選択窓より、ちゃんと見やすく
    # 押しやすく独立してあるボタンがある方がいい」)。旧版は nearby() の件数を数えて
    # いたが、その関数は 2026-08-08 に廃止された。gate は呼び続けて例外を握り潰し、
    # 対象0件のまま PASS していた。押した所の実判定で測り直す。
    for _zn, _z in (("既定ズーム", REND), ("歩きズーム", REND.get("walk") or {})):
        if not _z:
            continue
        if _z.get("tapErr"):
            fails["N24"].append("%s で押し分けを測れなかった: %s "
                                "(判定の関数を変えたら gate も直すこと)" % (_zn, _z["tapErr"]))
            continue
        _ts = _z.get("tapSelf")
        if _ts is None:
            fails["N24"].append("%s で押し分けの測定そのものが行われていない" % _zn)
        elif _ts:
            fails["N24"].append("%s: 印を押しても その店が開かない %d件 (%s)"
                                % (_zn, len(_ts),
                                   "、".join("%s→%s" % (x["n"], x["got"]) for x in _ts[:4])))

    # N54 店名の置き場が規則どおりか (ボスが毎回指摘している所)
    for _zn, _z in (("既定ズーム", REND), ("歩きズーム", REND.get("walk") or {})):
        if not _z:
            continue
        if _z.get("slotErr"):
            fails["N54"].append("%s で置き場を測れなかった: %s "
                                "(置き場の規則を変えたら gate も直すこと)" % (_zn, _z["slotErr"]))
            continue
        _sb = _z.get("slotBad")
        if _sb is None:
            fails["N54"].append("%s で置き場の測定そのものが行われていない" % _zn)
        elif not _z.get("slotChecked"):
            fails["N54"].append("%s で店名が1件も出ていない (測る対象が無い)" % _zn)
        elif _sb:
            fails["N54"].append("%s: 規則から外れた店名 %d件 (%s)"
                                % (_zn, len(_sb), "、".join(_sb[:4])))

    # N55 引き切った画面でも印が重ならない / 数え落としが無い
    _zo = REND.get("zoomout") or {}
    if not _zo:
        fails["N55"].append("引き切った画面を測れていない")
    else:
        if _zo.get("over"):
            fails["N55"].append("引き切り %.2fpx/m で印どうしが重なる %d組 (%s)"
                                % (_zo.get("scale", 0), len(_zo["over"]),
                                   "、".join(_zo["over"][:4])))
        if _zo.get("covered") != _zo.get("total"):
            fails["N55"].append("引き切りで数えられる店が %d件 (全%d件)。"
                                "まとめの丸に入れ損ねた店がある"
                                % (_zo.get("covered", 0), _zo.get("total", 0)))
        for c in (_zo.get("clusters") or []):
            if c["w"] < TAP_MIN_PX or c["h"] < TAP_MIN_PX:
                fails["N55"].append("まとめの丸が %.0fx%.0fpx (最小%.0f)"
                                    % (c["w"], c["h"], TAP_MIN_PX))
            if not c["label"]:
                fails["N55"].append("まとめの丸に読み上げ名が無い")

    # N56 地図に名前が出ている店の数。2026-08-09 ボス「どのサイズの縮小でも店名を
    # 表示してほしい」「まだ店名出てないところあるけどどういうつもり?」。
    # 置き方の規則 (N54) は見ていたのに「何件出ているか」は誰も見ていなかったため、
    # 斜め配置を廃した時に 地図に名前が出ない店が 2件→9件 に増えたのを素通りした。
    # 床は 2026-08-09 の実測 (既定49 / 歩き54) から少し下げた値。
    # ⚠ 下げる時は理由と実測を必ず書くこと。下げれば退行がそのまま通る。
    LABEL_VISIBLE_FLOOR = {"既定ズーム": 46, "歩きズーム": 50}
    for _zn, _z in (("既定ズーム", REND), ("歩きズーム", REND.get("walk") or {})):
        if not _z:
            fails["N56"].append("%s の画面を作れていない" % _zn)
            continue
        _lv = _z.get("labelsVisible")
        if _lv is None:
            fails["N56"].append("%s で名前の数を測れていない" % _zn)
        elif _lv < LABEL_VISIBLE_FLOOR[_zn]:
            fails["N56"].append("%s で地図に名前が出ている店が %d件しかない (床%d件)。"
                                "置き方を変えた時に数が落ちていないか確かめること"
                                % (_zn, _lv, LABEL_VISIBLE_FLOOR[_zn]))

    # N53 検査が対象を作れていること。状態を作れずに黙って飛ばすと、
    # その画面は総なめから消えたまま PASS になる。
    for u in REND.get("ui") or []:
        _ms = (u.get("sweep") or {}).get("missing") or []
        if _ms:
            fails["N53"].append("%dx%d で作れなかった画面: %s"
                                % (u.get("vw", 0), u.get("vh", 0), "、".join(_ms)))

# ---- N16 座標の出典 (src) が書き換えられていない ----
# src は N7 の上限を決めるキーなので、書き換えれば閾値を緩めたのと同じになる。
# 2026-07-30、同一住所の分離のために10店が gsi_addr → approx に変わり、
# うち1店 (中杜建設) が直交23.8m を approx の25m 上限で通していた。
_sbp = os.path.join(HERE, "src_baseline.json")
if os.path.exists(_sbp):
    _base = json.load(io.open(_sbp, encoding="utf-8"))["src"]
    for s in shops:
        b = _base.get(s["name"])
        if b and s.get("src") != b:
            fails["N16"].append("%s の出典が %s → %s に書き換わっている (src_baseline.json と不一致)"
                                % (s["name"], b, s.get("src")))

# ---- N62〜N65 こどもの声とクライアント訂正 (2026-08-14 あみさん指摘) ----
# 「声が反映されていない場所がある」。台帳69行に対して地図は26件しか出ていなかった。
# 原因は写し漏れではなく、台帳を読む経路が無かったこと = 落ちても誰も気づけない構造。
# ここで「台帳の1行1行が、地図か skip のどちらかに必ず居る」ことを数える。
_vmp = os.path.join(HERE, "voices_master.json")
_ccp = os.path.join(HERE, "client_corrections.json")
if not os.path.exists(_vmp):
    fails["N62"].append("voices_master.json が無い (声の台帳が消えている)")
else:
    _vm = json.load(io.open(_vmp, encoding="utf-8"))
    _by = {s["name"]: s for s in shops}
    _seen_rows = 0
    for _pl in _vm["places"]:
        if _pl.get("skip_reason"):
            _seen_rows += len(_pl["voices"])
            continue
        if not _pl.get("shops"):
            fails["N62"].append("台帳「%s」に行き先も skip の理由も無い" % _pl["master_name"])
            continue
        for _t in _pl["shops"]:
            if _t not in _by:
                fails["N62"].append("台帳「%s」の行き先「%s」が地図に無い (%d行が消える)"
                                    % (_pl["master_name"], _t, len(_pl["voices"])))
                continue
            _seen_rows += len(_pl["voices"])
            # N63 本文が1文字でも変わっていないか (言い換えは中身の改変)
            _want = [v["text"] for v in _pl["voices"]]
            _got = [v.get("text") for v in (_by[_t].get("voices") or [])]
            if _got != _want:
                for _a, _b in zip(_want, _got + [None] * len(_want)):
                    if _a != _b:
                        fails["N63"].append("%s の声が台帳と違う 台帳「%s」/ 地図「%s」"
                                            % (_t, _a, _b))
                if len(_got) != len(_want):
                    fails["N63"].append("%s の声が %d件しかない (台帳は %d行)"
                                        % (_t, len(_got), len(_want)))
    # 台帳の総行数と、地図＋skip で説明できた行数が合うか (黙って消えた行を出す)
    _total_rows = sum(len(p["voices"]) for p in _vm["places"])
    _mapped_rows = sum(len(p["voices"]) for p in _vm["places"] if not p.get("skip_reason"))
    _skip_rows = _total_rows - _mapped_rows
    _in_map = sum(len(s.get("voices") or []) for s in shops)
    _expect_in_map = sum(len(p["voices"]) * len(p.get("shops") or [])
                         for p in _vm["places"] if not p.get("skip_reason"))
    if _in_map != _expect_in_map:
        fails["N62"].append("地図の声が %d件・台帳から入るはずが %d件 (差 %d)"
                            % (_in_map, _expect_in_map, _expect_in_map - _in_map))
    # 台帳が自分で宣言している件数と、実体が合っているか。
    # (2026-08-14 独立レビュー指摘: 台帳から場所ごと消しても、台帳同士の整合だけ見ていると通る)
    _decl = _vm.get("counts") or {}
    if _decl.get("voice_lines") != _total_rows:
        fails["N62"].append("台帳の宣言 %s行 と 実体 %d行 が違う (行が消えたか足された)"
                            % (_decl.get("voice_lines"), _total_rows))
    if _decl.get("places") != len(_vm["places"]):
        fails["N62"].append("台帳の宣言 %s箇所 と 実体 %d箇所 が違う"
                            % (_decl.get("places"), len(_vm["places"])))
    # 🔴 一次ソース (あみさんから受け取った本文そのもの) と突き合わせる。
    # 台帳同士を比べても、台帳ごと書き換われば気づけない。正は _source/ の受領物。
    _srcmd = os.path.join(HERE, "_source", "2026-08-15_あみさん声リスト_LINE.md")
    if not os.path.exists(_srcmd):
        fails["N62"].append("一次ソース (%s) が無い (台帳を検算できない)"
                            % os.path.basename(_srcmd))
    else:
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import make_voices_master as _MVM   # 同じ読み取り規則を使う (二重実装しない)
            _src_rows = [(p["master_name"], p["lines"]) for p in _MVM.parse_source(_srcmd)]
            # 確認待ち (前の台帳から持ち越している分) は一次ソースに無いのが正しい
            _carried = [p for p in _vm["places"] if p.get("pending_confirmation")]
            _fromsrc = [p for p in _vm["places"] if not p.get("pending_confirmation")]
            if len(_src_rows) != len(_fromsrc):
                fails["N62"].append("一次ソースは %d箇所・台帳は %d箇所 (持ち越し %d箇所を除く)"
                                    % (len(_src_rows), len(_fromsrc), len(_carried)))
            for (_nm, _lines), _pl in zip(_src_rows, _fromsrc):
                if _nm != _pl["master_name"]:
                    fails["N62"].append("一次ソースの「%s」が台帳では「%s」になっている"
                                        % (_nm, _pl["master_name"]))
                    continue
                # raw が原文と1文字も違わないこと。text は絵文字を落とした表示用。
                _raw = [v.get("raw", v["text"]) for _pl_v, v in zip(_lines, _pl["voices"])] \
                    if len(_lines) == len(_pl["voices"]) else None
                if _raw is None:
                    fails["N63"].append("一次ソースと台帳の行数が違う (%s): %d行 / %d行"
                                        % (_nm, len(_lines), len(_pl["voices"])))
                elif _raw != _lines:
                    for _a, _b in zip(_lines, _raw):
                        if _a != _b:
                            fails["N63"].append("一次ソースと台帳が違う (%s): 原文「%s」/ 台帳「%s」"
                                                % (_nm, _a, _b))
                # 表示用の文が「原文 → 誤字の直し → 絵文字落とし」の結果と一致するか。
                # 台帳に無い書き換えが混ざっていたらここで落ちる。
                for _v in _pl["voices"]:
                    if _MVM.display_text(_v.get("raw", _v["text"])) != _v["text"]:
                        fails["N63"].append("%s の表示用の文が、原文と誤字の直しから作られていない: 「%s」"
                                            % (_nm, _v["text"]))
            # 確認待ちは「宙に浮かせない」。理由と出どころが必ず要る。
            for _pl in _carried:
                if not _pl.get("carried_from"):
                    fails["N62"].append("持ち越しの「%s」に出どころが書いていない" % _pl["master_name"])
        except Exception as _e:
            fails["N62"].append("一次ソースと突き合わせられない: %s: %s"
                                % (type(_e).__name__, _e))


# 表記統一の規則は build_mapdata.py が正本。二重実装せず、そこから借りる。
def _norm_display(value, field):
    if not value:
        return value
    s = str(value)
    s = re.sub(r'(?<=[0-9])：(?=[0-9])', ':', s)
    s = re.sub(r'(?<=[0-9])\s*[〜~−ー–—-]\s*(?=[0-9])', '～', s)
    if field == "closed":
        s = s.replace("、", "・")
        s = re.sub(r'(?<=[0-9])\.(?=[0-9])', '・', s)
    return re.sub(r'[ 　]{2,}', ' ', s).strip()


if not os.path.exists(_ccp):
    fails["N64"].append("client_corrections.json が無い (訂正の台帳が消えている)")
else:
    _cc = json.load(io.open(_ccp, encoding="utf-8"))
    _by = {s["name"]: s for s in shops}
    for _c in _cc["corrections"]:
        _s = _by.get(_c["shop"])
        if _c.get("applied"):
            if _s is None:
                fails["N64"].append("訂正の宛先「%s」が地図に無い" % _c["shop"])
                continue
            for _k, _v in (_c.get("set") or {}).items():
                # 地図側は表記統一 (記号だけ揃える) を通したあとの値なので、
                # 台帳側にも同じ規則を当ててから比べる。語が変わっていれば落ちる。
                _want = _norm_display(_v, _k) if _k in ("hours", "closed") else _v
                if _s.get(_k) != _want:
                    fails["N64"].append("%s の %s が訂正どおりでない 指示「%s」/ 地図「%s」"
                                        % (_c["shop"], _k, _want, _s.get(_k)))
            # 「あるか」でなく「中身が一致するか」を見る。存在だけ見ていると、
            # 曜日を24時間営業に書き換えても通ってしまう
            # (2026-08-14 独立レビューで故障注入して素通りを確認済み)
            for _k in ("hours_struct", "closed_rules", "open_now"):
                if _k not in _c:
                    continue
                if _s.get(_k) != _c[_k]:
                    fails["N64"].append("%s の %s が台帳と違う 台帳 %s / 地図 %s"
                                        % (_c["shop"], _k,
                                           json.dumps(_c[_k], ensure_ascii=False, sort_keys=True),
                                           json.dumps(_s.get(_k), ensure_ascii=False, sort_keys=True)))
        else:
            # 保留分は「勝手に適用していないこと」を見る。指示が2通りに読めるものなので、
            # 片方を黙って選んで出すのがいちばん危ない。
            # 存在の有無だけでなく、公式サイトの写しと同じ値のままかを見る。
            if _s is None:
                fails["N64"].append("保留中の「%s」が地図から消えている" % _c["shop"])
            else:
                if _s.get("hours_struct") or _s.get("closed_rules") or _s.get("open_now") is not None:
                    fails["N64"].append("保留中の「%s」に訂正が入っている (確認が取れるまで動かさない)"
                                        % _c["shop"])
                _odp = os.path.join(HERE, "official_details.json")
                if os.path.exists(_odp):
                    _od = (json.load(io.open(_odp, encoding="utf-8")).get("shops") or {}).get(_c["shop"])
                    if _od:
                        for _k in ("hours", "closed", "tel"):
                            if _od.get(_k) is not None and _s.get(_k) != _od.get(_k):
                                fails["N64"].append(
                                    "保留中の「%s」の %s が公式の写しから変わっている 公式「%s」/ 地図「%s」"
                                    % (_c["shop"], _k, _od.get(_k), _s.get(_k)))
    for _r in _cc.get("renames", []):
        if _r["from"] in _by:
            fails["N64"].append("改名前の「%s」が地図に残っている (→「%s」)"
                                % (_r["from"], _r["to"]))
        if _r["to"] not in _by:
            fails["N64"].append("改名後の「%s」が地図に無い" % _r["to"])
    for _r in _cc.get("removals", []):
        if _r["shop"] in _by:
            fails["N65"].append("削除を指示された「%s」が地図に残っている" % _r["shop"])
    _txt = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    for _r in _cc.get("removals", []):
        if _r["shop"] in _txt:
            fails["N65"].append("削除を指示された「%s」が index.html の中に残っている" % _r["shop"])

# ---- N66 二列に並べた信号が中山バス通り沿いだけか (2026-08-14 あみさん指摘) ----
# 「通りの地図の位置関係がズレている。信号機の場所とか」。
# 二列は一本の通りの絵なのに、絞り込みが無く別の道路の信号 (最遠622m) まで並べていた。
_ss = (REND or {}).get("stripSignals")
if _ss is None:
    fails["N66"].append("二列の信号を測れていない (測れないものを合格にしない)")
else:
    _bw = sorted((G.get("busway") or []), key=len, reverse=True)
    _main = _bw[0] if _bw else []

    def _n66_street_distance(px, py):
        best = float("inf")
        for _i in range(1, len(_main)):
            _a, _b = _main[_i - 1], _main[_i]
            _dx, _dy = _b[0] - _a[0], _b[1] - _a[1]
            _den = _dx * _dx + _dy * _dy
            _t = max(0.0, min(1.0, ((px - _a[0]) * _dx + (py - _a[1]) * _dy) / _den)) if _den else 0.0
            best = min(best, math.hypot(px - (_a[0] + _t * _dx), py - (_a[1] + _t * _dy)))
        return best

    _shown_y = _ss.get("shown") or []
    if not _main:
        fails["N66"].append("バス通りの線が取れない (判定できない)")
    else:
        # 残し過ぎ: 通り沿いでない信号が並んでいないか
        for _y in _shown_y:
            _cand = [p for p in signals if abs(p[1] - _y) < 0.6]
            if not _cand:
                fails["N66"].append("二列の信号 y=%.1f が GEO のどの信号とも一致しない" % _y)
                continue
            _d = min(_n66_street_distance(p[0], p[1]) for p in _cand)
            if _d > 30.0:
                fails["N66"].append("二列に出ている信号 y=%.1f は中山バス通りから %.1fm 離れた"
                                    "別の道路の信号" % (_y, _d))
        # 落とし過ぎ: 通り沿いの信号が全部出ているか。
        # 「1基も無い時だけ」しか見ていないと、4基中1基だけ残しても通る
        # (2026-08-14 独立レビューで故障注入して素通りを確認済み)
        _on_street = [p for p in signals if _n66_street_distance(p[0], p[1]) <= 30.0]
        if len(_shown_y) != len(_on_street):
            _missing = [p for p in _on_street
                        if not any(abs(p[1] - _y) < 0.6 for _y in _shown_y)]
            fails["N66"].append(
                "二列に出ている信号が %d基・通り沿いには %d基ある%s"
                % (len(_shown_y), len(_on_street),
                   " (出ていない: %s)" % "、".join("y=%.1f" % p[1] for p in _missing)
                   if _missing else ""))

# ---- N68 営業時間・定休日の表記がそろっているか (2026-08-15 ボス指摘) ----
# 掲載元の書き方がばらばらで、波ダッシュが5種類・コロンが2種類混在していた。
# 記号だけ揃える (語は触らない)。揃っていない値が1つでも出たら止める。
for _s in shops:
    for _f in ("hours", "closed"):
        _v = _s.get(_f)
        if not _v:
            continue
        _want = _norm_display(_v, _f)
        if _v != _want:
            fails["N68"].append("%s の %s の表記が揃っていない 「%s」→「%s」"
                                % (_s["name"], _f, _v, _want))
        for _ch, _why in (("〜", "波ダッシュ U+301C"), ("~", "チルダ U+007E"),
                          ("−", "マイナス U+2212"), ("：", "全角コロン")):
            if re.search(r'(?<=[0-9])\s*' + re.escape(_ch), _v):
                fails["N68"].append("%s の %s に %s が残っている: 「%s」"
                                    % (_s["name"], _f, _why, _v))

# ---- N69 詳細シートの値の左端が全店でそろっているか (2026-08-15 ボス指摘) ----
# ラベル列が auto 幅だと、その店に出る項目のうち最長のラベルで幅が決まり、
# 電話だけの店と営業時間もある店で値の左端が動く。全店同じ x から始まること。
_fx = (REND or {}).get("factCols")
if _fx is None:
    fails["N69"].append("詳細シートの値の位置を測れていない (測れないものを合格にしない)")
else:
    _lefts = sorted({round(r["valueLeft"], 1) for r in _fx if r.get("valueLeft") is not None})
    if len(_lefts) > 1:
        _ex = {}
        for r in _fx:
            _ex.setdefault(round(r["valueLeft"], 1), []).append(r["name"])
        fails["N69"].append(
            "値の左端が %d通りある (%s)。例: %s"
            % (len(_lefts), "、".join("%.0fpx" % v for v in _lefts),
               " / ".join("%.0fpx=%s" % (k, v[0]) for k, v in sorted(_ex.items())[:3])))
    if not _fx:
        fails["N69"].append("詳細シートの情報欄を1件も測れていない")

# ---- N70 二列(通り)ビューから外す指示の店が、二列に出ていないか (2026-08-15) ----
# 「通りの方のマップからカーブスを消してほしい」。消すのは二列だけで、
# 地図・一覧・検索からは消さない (店そのものを消す指示ではない)。両方を見る。
_sn = (REND or {}).get("stripNames")
for _ex in (json.load(io.open(_ccp, encoding="utf-8")).get("strip_exclusions", [])
            if os.path.exists(_ccp) else []):
    _nm = _ex["shop"]
    if _sn is None:
        fails["N70"].append("二列の店名を測れていない (測れないものを合格にしない)")
        break
    if any(_nm in t for t in _sn):
        fails["N70"].append("「%s」が二列にまだ出ている (外す指示)" % _nm)
    if _nm not in {s2["name"] for s2 in shops}:
        fails["N70"].append("「%s」が地図データごと消えている (二列から外すだけの指示)" % _nm)

# ---- N67 祝日表が今日から先まで届いているか (2026-08-14) ----
# 表の範囲外は安全側に倒して「いま」を出さない。つまり表が切れると、構造化した
# 全店から「いま」が黙って消える。切れる前に気づくために期限を検査する。
_hdp = os.path.join(HERE, "holidays.json")
_covers = ((G.get("meta") or {}).get("holidays") or {}).get("covers") or {}
if not _covers:
    fails["N67"].append("祝日表が地図に入っていない (「いま」が全店で出せない)")
else:
    import datetime as _dt
    _today = _dt.date.today()
    _need = _today + _dt.timedelta(days=180)
    try:
        _to = _dt.date(*[int(x) for x in _covers["to"].split("-")])
    except Exception:
        _to = None
    if _to is None:
        fails["N67"].append("祝日表の範囲が読めない: %s" % _covers.get("to"))
    elif _to < _need:
        fails["N67"].append("祝日表が %s までしか無い (180日先の %s に届いていない)。"
                            "内閣府CSVを取り直して make_holidays.py を回すこと"
                            % (_to.isoformat(), _need.isoformat()))

LBL = {"N1": "建物の中にいる", "N2": "道路の帯の内側にいない",
       "N3": "歩きズームで★が道路にかからず見える大きさ", "N4": "ラベルが自分の★に一意に結びつく",
       "N5": "通りの東西と向かい合いが成立", "N6": "目印の信号が使える",
       "N7": "移動が通りに沿う方向に偏っていない", "N8": "★同士が重なっていない",
       "N9": "公園との内外が真座標と一致", "N10": "通り沿いの間隔が歪んでいない",
       "N11": "既定ズームで通りが通りとして読める", "N12": "★が指で押す対象として見える大きさ",
       "N13": "ラベルが他店の★を内包しない", "N14": "ラベルの縁から自分の★が明確に最近傍",
       "N15": "★が道路の帯の上に乗っていない",
       "N16": "座標の出典(src)が書き換えられていない",
       "N17": "固定UIが店名を覆っていない",
       "N18": "こどもの声バッジが自分の★に一意に結びつく",
       "N19": "信号アイコンが★やラベルと重なっていない",
       "N20": "操作要素が44x44px以上", "N21": "文字が14px以上 (帰属表示は12px)",
       "N22": "操作要素が画面の外に出ていない", "N23": "地図が画面の62%以上",
       "N24": "印を押したらその店が開く (選択窓なしで独立して押せる)",
       "N25": "固定UIが帰属表示・注記を覆っていない",
       "N26": "こどもの声の店のラベルが端末を問わず出ている",
       "N27": "ズームしても地図の再描画が止まらない",
       "N28": "ボタンの文字が語の途中で改行されない",
       "N29": "文字が入れ物からはみ出していない",
       "N30": "文字と背景の明暗差が足りている",
       "N31": "押せるもの同士が近すぎない",
       "N32": "動きを減らす設定を尊重している",
       "N33": "キーボードで地図を飛ばせる・タブ順が見た目と合う",
       "N34": "絵文字をアイコン代わりに使っていない",
       "N35": "地図の店名が読める大きさ",
       "N36": "指で地図を拡大できる",
       "N37": "引き出し線がどの★のものか紛れない",
       "N38": "引き出し線が長すぎない",
       "N39": "引き出し線で運んだ名前が画面の外に出ていない",
       "N40": "二列の東西が真座標と一致する",
       "N41": "二列の並び順が通り沿いの真の順番と一致する",
       "N42": "向かい合う店が画面上でも同じ高さに来る",
       "N43": "押すものが親指の届く範囲にある",
       "N44": "押せるもの同士が重なっていない",
       "N45": "地図を開いたら地図が覆われていない",
       "N46": "地図の画面に見出しと戻る手段がある",
       "N47": "地図の店名が画面の縁で切れていない",
       "N48": "二列のカード同士に押し分けられる隙間がある",
       "N49": "絞り込んだ結果が1画面で見渡せる",
       "N50": "探しそうな言葉で店が引ける",
       "N51": "通りの中の道路名・信号が重なっていない",
       "N52": "地図が枠を埋めている (下に空白が残らない)",
       "N53": "検査が対象を作れている (状態が黙って抜けていない)",
       "N54": "店名が印に対して決まった置き場に出ている",
       "N55": "引き切っても印が重ならない (まとめの丸で解く)",
       "N56": "地図に名前が出ている店の数が落ちていない",
       "N57": "一覧の店名が語の途中で折り返されていない",
       "N58": "ボタンの文字に1文字だけの行ができていない",
       "N59": "箱が中身の文字を切っていない (端末の文字設定 150%/200%)",
       "N60": "同じ行で店名が住所より小さくない",
       "N61": "方位記号の針が北を向いている",
       "N62": "こどもの声の台帳が1行も行方不明になっていない",
       "N63": "こどもの声の本文が台帳と1文字も違わない",
       "N64": "クライアントの訂正が地図に出ている (保留分は動いていない)",
       "N65": "削除を指示された地点が地図に残っていない",
       "N66": "二列に並べた信号が中山バス通り沿いのものだけ",
       "N67": "祝日表が今日から180日先まで届いている",
       "N68": "営業時間・定休日の表記がそろっている",
       "N69": "詳細シートの値の左端が全店でそろっている",
       "N70": "二列から外す指示の店が二列に出ていない (店ごと消してもいない)"}
for k in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10",
          "N11", "N12", "N13", "N14", "N15", "N16", "N17", "N18", "N19",
          "N20", "N21", "N22", "N23", "N24", "N25", "N26", "N27", "N28", "N29",
              "N30", "N31", "N32", "N33", "N34", "N35", "N36", "N37", "N38", "N39", "N40", "N41", "N42", "N43", "N44",
              "N45", "N46", "N47", "N48", "N49", "N50", "N51", "N52", "N53", "N54",
              "N55", "N56", "N57", "N58", "N59", "N60", "N61",
              "N62", "N63", "N64", "N65", "N66", "N67", "N68", "N69", "N70"):
    v = sorted(set(fails[k]))
    P("【%s】%s — 違反 %d件" % (k, LBL[k], len(v)))
    for t in v[:14]:
        P("      " + t)
    if len(v) > 14:
        P("      ...他 %d件" % (len(v) - 14))

# ---------------- 全体 ----------------
P("")
P("【全体】")
gfail = []
if REND:
    # 2026-08-04: 「60」を直書きしていたが、ボス指示で地点が増えると
    # 正しい状態が不合格になる。件数はデータ(mapdata.json)から取る。
    # 意味は変わらない = 「載っている店・地点が全部★として出ているか」。
    P("  ★表示数: %d / %d" % (len(REND["rows"]), len(shops)))
    if len(REND["rows"]) != len(shops):
        gfail.append("★が%d件でない (データ上は%d件)" % (len(shops), len(shops)))
    wv = REND.get("walk", {}).get("labelsVisible", 0)
    P("  ラベル可視: デフォルト %d / 歩きズーム %d / bbox交差 %d"
      % (REND["labelsVisible"], wv, REND["labelCross"]))
    if REND["labelCross"]:
        gfail.append("ラベルbbox交差 %d件" % REND["labelCross"])
    # N4 は「ラベルを全部隠せば通る」盲点があるので、可視数を全体側で見る。
    #
    # 2026-08-04 基準を作り直した。理由:
    #   ボス指示で引き出し線(点線)を廃止した。点線があった時は、離れた場所に名前を置いて
    #   線で結べたので数が稼げていた (旧: 既定40件 / 歩き 全件)。線が無い今は
    #   「自分の★がいちばん近い」を満たす場所にしか名前を置けない (N4/N14 が要求する)。
    #   隣の★が画面上 8px しかない店では、どこへ置いても隣の方が近い = 幾何的に不可能。
    #   件数の床のままだと「不可能なことを要求する検査」になり、下げれば手抜きを通す。
    #   そこで「名前が無い店は、隣の★が近すぎて置けない店に限る」に置き換える。
    #   置けるのに置いていない店が1件でもあれば不合格 (手抜きは通らない)。
    # 置ける最小間隔の根拠: ★14px の半分(7) + 文字の高さ14px の半分(7) + 余白(3) = 17。
    # 実測では 19px / 22px の店も置けていないので、丸めて 24px を「置けない」の線とする。
    # (この値を上げれば手抜きが通る。上げる時は理由と実測を必ず書くこと)
    NAME_MIN_GAP_PX = 24.0
    # 名前は★と同じ側 (東の店は右・西の店は左) に置く決まりなので、
    # ★が画面の縁に寄っていると、その側に名前を置く幅が無い。
    # これは実装の手抜きではなく画面幅の問題なので、報告はするが不合格にはしない。
    # 幅の根拠: 店名は8〜10文字・文字14px で 110〜130px。名前1つ分が入らない位置は
    # 「置けない」。実測 (2026-08-04): なかやまとびのこ公園 は左縁から125px で、
    # 名前(約110px)＋★との間隔が入らない。
    EDGE_MARGIN_PX = 130.0
    REND_SCREEN_W = 390.0
    edge_notes = []
    for zk, zn, floor_rows in (("", "既定ズーム", REND.get("rows") or []),
                               ("walk", "歩きズーム", (REND.get("walk") or {}).get("rows") or [])):
        pts = [r for r in floor_rows if r.get("starCx") is not None]
        for r in floor_rows:
            if r.get("labelShown"):
                continue
            if r.get("starCx") is None:
                continue
            # 画面の外にいる店の名前が出ないのは当たり前 (N39 と同じ考え方)
            if not r.get("starInView"):
                continue
            near = min((math.hypot(r["starCx"] - o["starCx"], r["starCy"] - o["starCy"])
                        for o in pts if o["i"] != r["i"]), default=1e9)
            if near < NAME_MIN_GAP_PX:
                continue
            # 2026-08-07: 「隣の★までの距離」だけで置けるはずと判定していたが、
            # 名前は長いほど遠くまで伸びるので、隣に24px あっても長い名前は必ず
            # 隣の★をまたいでしまい、どの印の名前か決まらなくなる。
            # 検査側で置き場ルールを作り直すと本体と必ずズレるので、
            # 本体が残している「どの候補をなぜ捨てたか」を読む。
            # blocked (他の名前に押し出された) 以外で全滅していれば、置けない店。
            _src = REND if zk == "" else (REND.get("walk") or {})
            rej = (_src.get("labelReject") or {}).get(r.get("name"))
            if rej and rej.get("tried") and not rej.get("blocked"):
                continue
            if zk != "" and not rej:
                # 歩きズームは本体の記録が残らないので、置き場ルールをなぞって見る。
                # 名前は「いちばん近い★のもの」として読まれるので、自分より近い★が
                # ある位置には置けない (本体と同じ 0.72 の比率で判定)。
                name = r.get("name") or ""
                width = sum(0.62 if ord(ch) < 0x2E80 else 1.0 for ch in name) * 14.0
                gap, step, half, ratio = 9.0, 19.0, 9.0, 0.72
                free = False
                for dy in (0, -step, step, -2 * step, 2 * step, -3 * step, 3 * step):
                    for side in (1, -1):
                        x0 = (r["starCx"] + gap) if side > 0 else (r["starCx"] - gap - width)
                        box = (x0, r["starCy"] + dy - half, x0 + width, r["starCy"] + dy + half)

                        def _d(px, py, _b=box):
                            return math.hypot(max(_b[0] - px, 0, px - _b[2]),
                                              max(_b[1] - py, 0, py - _b[3]))

                        own = _d(r["starCx"], r["starCy"])
                        others = [_d(o["starCx"], o["starCy"]) for o in pts if o["i"] != r["i"]]
                        if others and own > ratio * min(others):
                            continue
                        free = True
                        break
                    if free:
                        break
                if not free:
                    continue
            gfail.append("%s の名前が%sで出ていない (隣の★まで%.0fpx あるので置けるはず)"
                         % (r["name"], zn, near))
    if edge_notes:
        P("  画面の縁で名前を置く幅が無い店: %s" % " / ".join(edge_notes))
    P("  JSエラー: %d" % REND["jsErrors"])
    if REND["jsErrors"]:
        gfail.append("JSエラー %d件" % REND["jsErrors"])
    mn = min((r["starPxNow"] for r in REND["rows"]), default=0)
    P("  ★の画面サイズ (デフォルト): 最小 %.1fpx" % mn)
    if mn < MIN_STAR_PX:
        gfail.append("★が%.1fpx (最小%.0f)" % (mn, MIN_STAR_PX))
    smap = sorted({r["starMapM"] for r in REND["rows"]})
    wmap = sorted({r["starMapM"] for r in REND.get("walk", {}).get("rows", [])})
    P("  ★の地図空間サイズ: デフォルト %s m / 歩きズーム %s m" % (smap[:3], wmap[:3]))
    if wmap and wmap[-1] > 12.0:
        gfail.append("歩きズームで★が%.1fm (実店舗の間口10m超・縮尺の外)" % wmap[-1])
else:
    gfail.append("ブラウザ実測なし")
# 測定が途中で落ちたら、その先の項目は「違反0件」でなく「測れていない」。
# 空回りの合格を出さないため、必ず不合格にする。
if REND and REND.get("measureError"):
    gfail.append("実測が途中で落ちた (%s) — この先の項目は測れていない"
                 % REND["measureError"])
if REND and not (REND.get("ui") or []):
    gfail.append("UI検査が1件も実施されていない (N20-N34 / N40-N43 は未測定)")
P("  信号が交差点に立っている: %d / %d" % (sum(SIG_OK), len(signals)))
if sum(SIG_OK) != len(signals):
    gfail.append("交差点にない信号 %d基" % (len(signals) - sum(SIG_OK)))

# 「歩ける店」= 店ごとの違反が1件も無い店の数。違反文の先頭語を店名とみなすが、
# 店名で始まらない違反文 (端末名・要素名など) まで店として数えていた。
# 2026-08-08 実測: N53 の「360x640 で…」6件が幽霊の6店になり 60→54 と出た。
# 実在する店名だけを数える。
_shop_names = {s["name"] for s in shops}
nav_fail = set()
for k in fails:
    for t in fails[k]:
        nm = t.split(" ")[0].split("(")[0].split("←")[0].strip()
        if nm in _shop_names:
            nav_fail.add(nm)
P("")
P("=" * 78)
P("歩ける店 (N1..N44 全通過): %d / %d" % (len(shops) - len(nav_fail), len(shops)))
P("全体の不合格項目: %d件 %s" % (len(gfail), gfail if gfail else ""))
total = sum(len(set(v)) for v in fails.values()) + len(gfail)
P("判定: %s (違反 %d件)%s" % ("PASS" if total == 0 else "FAIL", total,
     "" if not A.devices else "  ※ --devices で絞って測った結果。合格ではない"))
P("=" * 78)

if A.json:
    io.open(A.json, "w", encoding="utf-8").write(json.dumps(
        {"fails": {k: sorted(set(v)) for k, v in fails.items()}, "global": gfail,
         "navigable": len(shops) - len(nav_fail), "shops": len(shops),
         "verdict": "PASS" if total == 0 else "FAIL"}, ensure_ascii=False, indent=1))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
print("\n".join(OUT))
sys.exit(0 if total == 0 else 1)
