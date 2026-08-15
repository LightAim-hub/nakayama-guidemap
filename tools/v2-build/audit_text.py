#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""画面に出る日本語の誤字・表記の乱れを機械で当てる (2026-08-15 ボス指示)。

方針:
  - **こどもの声は直さない。** 本人の言葉なので、誤字があっても原文のまま出す。
    ただし「気づいていない」のと「気づいて残している」のは違うので、別枠で必ず出す。
  - 直すのは**こちらが書いた文**: 店舗情報 (営業時間・定休日・住所・説明) と、
    画面の固定文言 (template.html の中の日本語)。

見るもの:
  T1 括弧の対応 (（）「」() 【】) が取れているか
  T2 句読点・記号の重複 (。。 、、 ・・ ！！ ～～)
  T3 全角と半角の混ざり (英数字が全角 / カタカナが半角)
  T4 余計な空白 (行頭行末・連続)
  T5 同じ文字の不自然な連続 (ののの など)
  T6 店名の表記ゆれ (よく似た名前が2つある)
  T7 画面の固定文言のうち、よくある打ち間違いの形
  T8 こどもの声の中の気になる表記 (直さない・報告だけ)

exit 0 = 直すべきものが無い。exit 1 = 1件以上。

usage: python audit_text.py
"""
import io
import json
import os
import re
import sys
import unicodedata

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
GEO = json.load(io.open(os.path.join(HERE, "mapdata.json"), encoding="utf-8"))
TPL = io.open(os.path.join(HERE, "template.html"), encoding="utf-8").read()

findings, voice_notes, notes = [], [], []


def bad(code, who, msg):
    findings.append((code, who, msg))


PAIRS = [("（", "）"), ("(", ")"), ("「", "」"), ("【", "】"), ("〈", "〉"), ("［", "］")]
HANKAKU_KANA = re.compile(r'[｡-ﾟ]')
ZEN_ALNUM = re.compile(r'[Ａ-Ｚａ-ｚ０-９]')


def check_text(where, who, text, into, fragment=False):
    """fragment=True: JS の中で他の値と連結される断片。
    断片は単体では括弧が閉じず、末尾の空白も意図的なので、その2つは見ない
    (2026-08-15: 見てしまって偽陽性7件を出した)。"""
    if not text:
        return
    if not fragment:
        for op, cl in PAIRS:
            if text.count(op) != text.count(cl):
                into.append((where, who, "括弧の数が合わない %s%s: 「%s」" % (op, cl, text)))
        if text != text.strip() or re.search(r'[ 　]{2,}', text):
            into.append((where, who, "余分な空白がある: 「%s」" % text))
    else:
        if re.search(r'[ 　]{2,}', text):
            into.append((where, who, "空白が2つ以上続く: 「%s」" % text))
    m = re.search(r'(。。|、、|・・|！！|？？|～～|,,|\.\.)', text)
    if m:
        into.append((where, who, "記号が重なっている「%s」: 「%s」" % (m.group(1), text)))
    if HANKAKU_KANA.search(text):
        into.append((where, who, "半角カタカナが混ざっている: 「%s」" % text))
    if ZEN_ALNUM.search(text):
        into.append((where, who, "全角の英数字が混ざっている: 「%s」" % text))
    m = re.search(r'([ぁ-んァ-ヶ])\1\1', text)
    if m:
        into.append((where, who, "同じ文字が3つ続く「%s」: 「%s」" % (m.group(0), text)))


# ---------------- T1-T5 こちらが書いた文 ----------------
own = []
for s in GEO["shops"]:
    for field in ("name", "addr", "hours", "closed", "note"):
        check_text(field, s["name"], s.get(field), own)
    for ph in s.get("photos") or []:
        check_text("photo.alt", s["name"], ph.get("alt"), own)
for w, who, msg in own:
    bad("T1-5", "%s (%s)" % (who, w), msg)

# ---------------- T6 店名の表記ゆれ ----------------
names = [s["name"] for s in GEO["shops"]]


def key(n):
    n = unicodedata.normalize("NFKC", n)
    n = re.sub(r'[\s　・]', '', n).lower()
    return n


seen = {}
for n in names:
    seen.setdefault(key(n), []).append(n)
for k, group in seen.items():
    if len(group) > 1:
        bad("T6", "／".join(group), "実質同じ名前が %d件ある" % len(group))
# よく似た名前 (1文字違い) も出す
for i, a in enumerate(names):
    for b in names[i + 1:]:
        ka, kb = key(a), key(b)
        if ka == kb or abs(len(ka) - len(kb)) > 1 or len(ka) < 4:
            continue
        diff = sum(1 for x, y in zip(ka, kb) if x != y) + abs(len(ka) - len(kb))
        if diff <= 1:
            notes.append("よく似た店名: 「%s」と「%s」" % (a, b))

# ---------------- T7 画面の固定文言 ----------------
# template.html の中の、タグの外に出ている日本語 (実際に読まれる文) を拾う
body = re.sub(r'<script.*?</script>', '', TPL, flags=re.S)
body = re.sub(r'<style.*?</style>', '', body, flags=re.S)
body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
html_texts, js_texts = [], []
for m in re.finditer(r'>([^<>]{2,}?)<', body):
    t = m.group(1).strip()
    if t and re.search(r'[ぁ-んァ-ヶ一-鿿]', t):
        html_texts.append(t)
# JS の中の日本語リテラルも読まれる文。ただし他の値と連結される断片が多いので、
# 括弧の対応と末尾の空白は見ない (見ると「…より（」を毎回誤って拾う)
for m in re.finditer(r"'([^'\\\n]{2,}?)'", TPL):
    t = m.group(1)
    if re.search(r'[ぁ-んァ-ヶ]', t) and len(t) >= 4:
        js_texts.append(t)
ui_texts = html_texts + js_texts
ui_bad = []
for t in set(html_texts):
    check_text("画面の文言", "-", t, ui_bad)
for t in set(js_texts):
    check_text("画面の文言(組み立て)", "-", t, ui_bad, fragment=True)
# 「〜せれる」「〜れれる」など、よくある打ち間違いの形
TYPO_SHAPES = [
    (r'をを|でで|がが|ををを', "助詞が重なっている"),
    (r'いたしまし[すた]ます', "文末が重なっている"),
    (r'([ぁ-ん])\1{2,}', "同じかなが3つ続く"),
]
for t in set(ui_texts):
    for pat, why in TYPO_SHAPES:
        if re.search(pat, t):
            ui_bad.append(("画面の文言", "-", "%s: 「%s」" % (why, t)))
for w, who, msg in ui_bad:
    bad("T7", w, msg)

# ---------------- T8 こどもの声 (直さない・報告だけ) ----------------
vm_path = os.path.join(HERE, "voices_master.json")
if os.path.exists(vm_path):
    VM = json.load(io.open(vm_path, encoding="utf-8"))
    for pl in VM.get("places", []):
        for v in pl["voices"]:
            t = v["text"]
            tmp = []
            check_text("声", pl["master_name"], t, tmp)
            for _, who, msg in tmp:
                voice_notes.append("%s: %s" % (who, msg))

# ---------------- 出力 ----------------
P = print
P("=" * 78)
P("画面に出る日本語のチェック   店 %d / 画面の文言 %d種" % (len(GEO["shops"]), len(set(ui_texts))))
P("=" * 78)
LBL = {"T1-5": "店舗情報の文 (括弧・記号の重なり・全半角・空白)",
       "T6": "店名の表記ゆれ",
       "T7": "画面の固定文言"}
for code in ("T1-5", "T6", "T7"):
    rows = [f for f in findings if f[0] == code]
    P("")
    P("【%s】%s — %d件" % (code, LBL[code], len(rows)))
    for _, who, msg in rows:
        P("      %s: %s" % (who, msg))
P("")
P("【T8】こどもの声の中の気になる表記 — %d件" % len(voice_notes))
P("      ※ 本人の言葉なので**直さない**。気づいたうえで原文のまま出している、という記録。")
for n in voice_notes:
    P("      " + n)
if notes:
    P("")
    P("【参考】%d件" % len(notes))
    for n in notes:
        P("      " + n)
P("")
P("=" * 78)
P("直すべきもの 合計 %d件" % len(findings))
P("=" * 78)
sys.exit(1 if findings else 0)
