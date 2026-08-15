#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""情報の整合性を全数で突き合わせる (2026-08-15 ボス指示「抜け漏れなくチェック」)。

gate.py は「規則に違反していないか」を見る。ここは違う仕事をする:
**同じことを言っているはずの2つの出どころが、食い違っていないか**を全店ぶん並べる。

見るもの:
  C1 表示している営業時間の文 と 判定に使う曜日別データ (hours_struct) が矛盾していないか
     → いちばん危ない。画面には「水 8:30～12:30」と出ているのに、判定は終日営業…が起きうる
  C2 定休日の文 と hours_struct / closed_rules が矛盾していないか
     → 「日曜定休」と書いてあるのに日曜の時間が入っている、など
  C3 公式サイトの写し (official_details.json) と地図の食い違い (訂正で意図的に変えた分を除く)
  C4 こどもの声: 一次ソース ↔ 台帳 ↔ 地図
  C5 写真ファイルが実在するか
  C6 電話番号・URL の形と重複
  C7 時点表示 (voices_as_of / details_as_of) が実際の更新日と合っているか
  C8 座標の出どころ (src) の内訳と、弱い出どころの店

exit 0 = 食い違いなし。exit 1 = 1件以上。数字は必ず出す。

usage: python audit_consistency.py [--json out.json]
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WD = "日月火水木金土"          # 0=日 … 6=土 (JS の getDay と同じ)
findings = []
notes = []


def bad(code, shop, msg):
    findings.append({"code": code, "shop": shop, "msg": msg})


def load(name, root=HERE):
    p = os.path.join(root, name)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))


GEO = load("mapdata.json")
if GEO is None:
    raise SystemExit("mapdata.json が無い。先に build_mapdata.py を回すこと")
SHOPS = {s["name"]: s for s in GEO["shops"]}
OFFICIAL = (load("official_details.json") or {}).get("shops") or {}
CC = load("client_corrections.json") or {}
VM = load("voices_master.json") or {}

# 訂正で意図的に公式と変えた店。C3 でここを食い違いとして数えない。
INTENDED = {}
for c in CC.get("corrections", []):
    if c.get("applied"):
        INTENDED[c["shop"]] = set((c.get("set") or {}).keys())
RENAMED = {r["from"]: r["to"] for r in CC.get("renames", [])}

# ---------------- C1 営業時間の文 と 曜日別データ ----------------
TIME = re.compile(r'(\d{1,2})\s*[:：時]\s*(\d{0,2})')


def minutes_in_text(text):
    """文中の時刻をすべて分に直して返す。"""
    out = []
    for m in TIME.finditer(text):
        out.append(int(m.group(1)) * 60 + int(m.group(2) or 0))
    return out


for name, s in SHOPS.items():
    hs = s.get("hours_struct")
    if not hs:
        continue
    text = s.get("hours") or ""
    if not text:
        bad("C1", name, "曜日別データを持っているのに、画面に出す営業時間の文が無い")
        continue
    shown = set(minutes_in_text(text))
    used = set()
    for k, ranges in hs.items():
        for a, b in ranges:
            used.add(a)
            used.add(b % 1440 if b >= 1440 else b)
    missing = sorted(used - shown)
    if missing:
        bad("C1", name,
            "判定に使う時刻が営業時間の文に出てこない: %s / 文=「%s」"
            % ("、".join("%d:%02d" % (m // 60, m % 60) for m in missing), text))
    # 文に曜日が書いてあるなら、その曜日が空でないこと
    for i, ch in enumerate(WD):
        if re.search(r'(?<![０-９0-9])' + ch + r'(?:曜)?', text) and str(i) in hs:
            if not hs[str(i)]:
                bad("C1", name, "文には %s曜 が書いてあるのに、判定では %s曜 が終日休み" % (ch, ch))

# ---------------- C2 定休日の文 と 曜日別データ / 休みの規則 ----------------
for name, s in SHOPS.items():
    hs = s.get("hours_struct")
    closed_text = s.get("closed") or ""
    if not hs:
        continue
    # 「毎月1日」「第1・2・3水曜日」「10～3月」のような日付・回数の表現は、
    # 中に「日」「月」の字を含むが曜日ではない。先に外してから曜日を探す。
    # (2026-08-15 実測: これを外さないと Double Egg の「毎月1日」を日曜・月曜定休と誤読した)
    scan = re.sub(r'毎月\s*[0-9０-９]+\s*日', '', closed_text)
    scan = re.sub(r'第[0-9０-９・.,、]+', '', scan)
    scan = re.sub(r'[0-9０-９]+\s*～\s*[0-9０-９]+\s*月', '', scan)
    for i, ch in enumerate(WD):
        # 「日・祝」「日曜」「日曜日」いずれの書き方も拾う。「木曜午後」は半日なので除く
        m = re.search(ch + r'曜?日?(午前|午後)?', scan)
        if not m:
            continue
        half = m.group(1)
        has = bool(hs.get(str(i)))
        if not half and has:
            bad("C2", name, "定休日に「%s」とあるのに、判定では %s曜に営業時間が入っている: 「%s」"
                % (m.group(0), ch, closed_text))
        if half and not has:
            bad("C2", name, "定休日は「%s」(半日) なのに、判定では %s曜が終日休み" % (m.group(0), ch))
    if "祝" in closed_text and not (s.get("closed_rules") or {}).get("holidays"):
        bad("C2", name, "定休日に「祝」とあるのに、休みの規則に祝日が入っていない: 「%s」" % closed_text)
    if re.search(r'毎月\s*([0-9０-９]+)\s*日', closed_text):
        if not (s.get("closed_rules") or {}).get("dates"):
            bad("C2", name, "定休日に「毎月◯日」とあるのに、休みの規則に日付が入っていない: 「%s」" % closed_text)

# ---------------- C3 公式サイトの写し と 地図 ----------------
c3 = 0
for off_name, off in OFFICIAL.items():
    name = RENAMED.get(off_name, off_name)
    s = SHOPS.get(name)
    if s is None:
        notes.append("公式の写しにあるが地図に無い: %s (閉業・削除の可能性)" % off_name)
        continue
    for k in ("tel", "hours", "closed", "addr"):
        want, got = off.get(k), s.get(k)
        if want is None or got is None:
            continue
        if k in INTENDED.get(name, set()):
            continue                       # 訂正で意図的に変えた分
        if k == "addr":
            norm = lambda v: re.sub(r'[\s　]', '',
                                    v.replace("丁目", "-").replace("−", "-")
                                     .replace("―", "-").replace("宮城県", ""))
            if norm(want) != norm(got):
                notes.append("住所が公式と違う: %s 地図=%s / 公式=%s" % (name, got, want))
            continue
        if k in ("hours", "closed"):
            # 記号は build_mapdata.py が意図して揃えている (見せ方の統一)。
            # 揃えた分を「公式と食い違う」と数えないよう、両側に同じ規則を当てる。
            def n(v):
                v = re.sub(r'(?<=[0-9])：(?=[0-9])', ':', str(v))
                v = re.sub(r'(?<=[0-9])\s*[〜~−ー–—-]\s*(?=[0-9])', '～', v)
                v = v.replace("、", "・")
                v = re.sub(r'(?<=[0-9])\.(?=[0-9])', '・', v)
                return re.sub(r'[\s　]', '', v)
            if n(want) != n(got):
                bad("C3", name, "%s が公式の写しと違う (訂正の記録も無い) 地図=「%s」/ 公式=「%s」"
                    % (k, got, want))
                c3 += 1
        elif want != got:
            bad("C3", name, "%s が公式の写しと違う 地図=「%s」/ 公式=「%s」" % (k, got, want))
            c3 += 1

# ---------------- C4 こどもの声 ----------------
if VM:
    total_master = 0
    for pl in VM.get("places", []):
        want = [v["text"] for v in pl["voices"]]
        total_master += len(want) * len(pl.get("shops") or [])
        for target in pl.get("shops") or []:
            s = SHOPS.get(target)
            if s is None:
                bad("C4", target, "台帳「%s」の行き先が地図に無い" % pl["master_name"])
                continue
            got = [v.get("text") for v in (s.get("voices") or [])]
            if got != want:
                bad("C4", target, "声が台帳と違う 台帳%d行 / 地図%d件" % (len(want), len(got)))
    in_map = sum(len(s.get("voices") or []) for s in SHOPS.values())
    if in_map != total_master:
        bad("C4", "-", "地図の声 %d件 / 台帳から入るはず %d件" % (in_map, total_master))
    # 台帳に無いのに地図に声がある店 (取り残し)
    listed = set()
    for pl in VM.get("places", []):
        listed.update(pl.get("shops") or [])
    for name, s in SHOPS.items():
        if (s.get("voices") or []) and name not in listed:
            bad("C4", name, "台帳に無いのに地図に声が %d件ある (前の版の残り)" % len(s["voices"]))

# ---------------- C5 写真ファイル ----------------
for name, s in SHOPS.items():
    for ph in s.get("photos") or []:
        src = ph.get("src") or ""
        found = [e for e in (".webp", ".jpg", ".jpeg", ".png", ".avif")
                 if os.path.exists(os.path.join(ROOT, src + e))]
        if not found and not os.path.exists(os.path.join(ROOT, src)):
            bad("C5", name, "写真のファイルが無い: %s" % src)
        if not (ph.get("alt") or "").strip():
            bad("C5", name, "写真に説明 (alt) が無い: %s" % src)

# ---------------- C6 電話番号・URL ----------------
tel_owner = {}
for name, s in SHOPS.items():
    tel = s.get("tel")
    if tel:
        if not re.fullmatch(r'0\d{1,4}-\d{1,4}-\d{4}', tel):
            bad("C6", name, "電話番号の形が他と違う: %s" % tel)
        tel_owner.setdefault(tel, []).append(name)
    url = s.get("url")
    if url and url != "#" and not url.startswith("http"):
        bad("C6", name, "リンク先が URL になっていない: %s" % url)
for tel, owners in tel_owner.items():
    if len(owners) > 1:
        notes.append("同じ電話番号の店: %s → %s" % (tel, "、".join(owners)))

# ---------------- C7 時点表示 ----------------
meta = GEO["meta"]
if not meta.get("voices_as_of"):
    bad("C7", "-", "こどもの声の時点が入っていない")
if not meta.get("details_as_of"):
    bad("C7", "-", "店舗情報の時点が入っていない")
# 「こどもの声（◯月◯日時点）」は**声を集めた日**を出す欄。受け取った日ではない。
# 台帳に collected があればそれと突き合わせる。無ければ「分からない」として止める
# (受領日で埋めてしまうと、集めた日を偽ることになる)。
_col = VM.get("source", {}).get("collected")
if not _col:
    bad("C7", "-", "台帳に声を集めた日 (collected) が無い。画面には「%s」と出ている"
        % (meta.get("voices_as_of") or "(空)"))
elif (meta.get("voices_as_of") or "") != _col:
    bad("C7", "-", "こどもの声の時点が台帳と違う 画面=「%s」/ 台帳=「%s」"
        % (meta.get("voices_as_of"), _col))
if CC.get("received"):
    y, m, d = CC["received"].split("-")
    want = "%s年%d月%d日" % (y, int(m), int(d))
    got = meta.get("details_as_of") or ""
    if got != want:
        bad("C7", "-", "店舗情報の時点が訂正の受領日と違う 画面=「%s」/ 訂正台帳=「%s」" % (got, want))

# ---------------- C8 座標の出どころ ----------------
src_count = {}
for name, s in SHOPS.items():
    src_count[s.get("src", "?")] = src_count.get(s.get("src", "?"), 0) + 1
weak = [n for n, s in SHOPS.items() if s.get("src") in ("approx", "gsi_dem")]

# ---------------- 出力 ----------------
P = print
P("=" * 78)
P("情報の整合性 全数チェック   店 %d / 声 %d件"
  % (len(SHOPS), sum(len(s.get("voices") or []) for s in SHOPS.values())))
P("=" * 78)
by_code = {}
for f in findings:
    by_code.setdefault(f["code"], []).append(f)
LABEL = {
    "C1": "営業時間の文 と 判定に使う曜日別データ",
    "C2": "定休日の文 と 曜日別データ・休みの規則",
    "C3": "公式サイトの写し と 地図 (訂正の記録がないもの)",
    "C4": "こどもの声 (一次台帳 ↔ 地図)",
    "C5": "写真ファイルと説明",
    "C6": "電話番号・リンク先の形",
    "C7": "「◯月◯日時点」の表示",
}
for code in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
    rows = by_code.get(code, [])
    P("")
    P("【%s】%s — 食い違い %d件" % (code, LABEL[code], len(rows)))
    for r in rows:
        P("      %s: %s" % (r["shop"], r["msg"]))
P("")
P("【C8】座標の出どころ")
for k, v in sorted(src_count.items(), key=lambda kv: -kv[1]):
    P("      %-14s %d店" % (k, v))
if weak:
    P("      ※ 出どころが弱い店 (approx / 標高由来): %s" % "、".join(weak))
if notes:
    P("")
    P("【参考】食い違いとして数えないが目に入れておくもの (%d件)" % len(notes))
    for n in notes:
        P("      " + n)
P("")
P("=" * 78)
P("食い違い 合計 %d件" % len(findings))
P("=" * 78)

if "--json" in sys.argv:
    out = sys.argv[sys.argv.index("--json") + 1]
    io.open(out, "w", encoding="utf-8").write(
        json.dumps({"findings": findings, "notes": notes, "src": src_count},
                   ensure_ascii=False, indent=1))

sys.exit(1 if findings else 0)
