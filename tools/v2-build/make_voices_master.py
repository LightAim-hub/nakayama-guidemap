#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""こどもの声の一次台帳を voices_master.json へ変換する。

なぜ要るか:
  2026-08-14 に「声が反映されていない場所がある」と指摘を受けた。突き合わせたら
  台帳 69行 / 23箇所 に対し、地図に出ていたのは 26件 / 11店だった。原因は
  **台帳を読む経路がそもそも無かった**こと。写し漏れても誰も気づけなかった。
  ここを台帳駆動にして、対応先の無い行は SKIP に理由つきで残す。

正本の移り変わり:
  2026-08-14  xlsx (`2026-08-14_中山商店街_こどもの声台帳.xlsx`) 69行/23箇所
  2026-08-15  LINE (`2026-08-15_あみさん声リスト_LINE.md`) 33行/12箇所 ← **いまの正本**
              あみさんが選び直し・書き直した版。件数が減り、本文も変わっている。
              xlsx は履歴として _source に残す (消さない)。

本文は1文字も変えない:
  こどもの声は本人の言葉。どれを載せるかはこちらの領分でも、書き換えるのはクライアントの領分。

絵文字だけは表示側で落とす:
  地図のフォントは使う字だけを部分集合にして積んでいるので、絵文字は豆腐 (□) になる。
  gate にも絵文字を弾く検査がある。落とした事実は raw に原文を残して追えるようにする。

usage: python make_voices_master.py
"""
import io
import json
import os
import re
import sys

# ⚠ stdout の差し替えは main() の中でやる。モジュールの読み込みだけで差し替えると、
# gate.py がこの中の関数を使うために import した時に gate 側の出力が壊れる
# (2026-08-14 実測: gate が最後の print で I/O operation on closed file で落ちた)。

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_source", "2026-08-15_あみさん声リスト_LINE.md")
SRC_XLSX = os.path.join(HERE, "_source", "2026-08-14_中山商店街_こどもの声台帳.xlsx")
OUT = os.path.join(HERE, "voices_master.json")

# 台帳の書き方 → 地図の店名。1つの声を2店に出すものは list で持つ。
# (だぶるえっぐは台帳が本店/4丁目を区別していない。今の本番も同じ声を両方に出しているので、
#  その挙動を保つ。分けたくなったらあみさんに聞いてからにする。)
NAME_MAP = {
    "フラワー中山": "フラワー中山",
    "とらの子": "中華レストラン とらの子",
    "BAKERY&BAKE End Roll": "BAKERY&BAKE EndRoll",
    "中山山の神公園": "中山山の神公園",
    "cake nao": "Cake NAO",
    "柏屋": "柏屋",
    "KAYA": "レストラン KAYA",
    "中山とびのこ公園": "なかやまとびのこ公園",
    "だぶるえっぐ": ["Double Egg", "Double Egg4丁目"],
    "たきみち公園": "たきみち公園",
    "中山市民センター": "中山市民センター",
    "中山坂の上": "中山の坂の上",
}

# 2026-08-15 の新しいリストには無いが、前の台帳 (xlsx) には有り、いま地図に出ているもの。
# **消す指示か書き漏れかが分からないので、確認が取れるまで残す。**
# 消すのは戻せないが、残すのは戻せる。確認が取れたら NAME_MAP へ移すか、この辞書ごと消す。
PENDING_CONFIRMATION = {
    "ウエルシア": {
        "shops": ["ウエルシア仙台中山店"],
        "voices": ["商品が安い", "飲み物やお菓子をたくさん買う"],
        "reason": "2026-08-15 の新リストに無い。xlsx には2行あり、いま地図にも出ている。"
                  "消す指示か書き漏れかをあみさんへ確認中",
        "from": "2026-08-14_中山商店街_こどもの声台帳.xlsx",
    },
}

# 絵文字・異体字セレクタ・結合文字。地図のフォントに字形が無いので表示からは落とす。
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿️‍⃣]+")


def strip_emoji(text):
    """絵文字を落として前後の空白を整える。語は変えない。"""
    return EMOJI_RE.sub("", text).strip()


def parse_source(path):
    """`## 店名` と `- 声` だけを読む。前書き・後書きは無視する。"""
    places, cur = [], None
    body = False
    for raw in io.open(path, encoding="utf-8").read().splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            title = line[3:].strip()
            if title.startswith("原文からの整形"):
                cur = None
                body = False
                continue
            cur = {"master_name": title, "lines": []}
            places.append(cur)
            body = True
            continue
        if body and cur is not None and line.startswith("- "):
            cur["lines"].append(line[2:].strip())
    return places


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    parsed = parse_source(SRC)
    if not parsed:
        raise SystemExit("一次台帳から1箇所も読めなかった: %s" % SRC)

    places, total, dropped_emoji = [], 0, []
    for p in parsed:
        name = p["master_name"]
        voices = []
        for raw in p["lines"]:
            shown = strip_emoji(raw)
            if not shown:
                raise SystemExit("絵文字を落としたら空になる行がある (%s): %r" % (name, raw))
            if shown != raw:
                dropped_emoji.append((name, raw))
            voices.append({"text": shown, "raw": raw})
        total += len(voices)
        entry = {"master_name": name, "voices": voices}
        if name in NAME_MAP:
            t = NAME_MAP[name]
            entry["shops"] = t if isinstance(t, list) else [t]
        else:
            raise SystemExit(
                "台帳の「%s」が NAME_MAP に無い。載せる先を決めてから回すこと "
                "(黙って落とさないための停止)。" % name)
        places.append(entry)

    # 確認待ちの分を、出どころと理由つきで足す
    for name, info in PENDING_CONFIRMATION.items():
        places.append({
            "master_name": name,
            "voices": [{"text": t, "raw": t} for t in info["voices"]],
            "shops": info["shops"],
            "pending_confirmation": info["reason"],
            "carried_from": info["from"],
        })
        total += len(info["voices"])

    doc = {
        "_readme": "こどもの声の一次台帳。本文は1文字も変えない (絵文字だけ表示から落とし、raw に原文を残す)。"
                   "地図の声はここから生成する (build_mapdata.py)。",
        "source": {
            "file": "tools/v2-build/_source/2026-08-15_あみさん声リスト_LINE.md",
            "provided_by": "あみさん (宮城大学 事業構想学群 宮﨑ゼミ / 中山商店街振興組合)",
            "received": "2026-08-15",
            "channel": "LINE",
            # 画面の「こどもの声（◯月◯日時点）」に出るのはこちら (受け取った日ではない)。
            # 差し替え版に新しい声 (KAYA のハンバーグなど) が入っているので、集め直したのか
            # 元の声から選び直したのかは未確認。あみさんに確認するまで原本の収集日を出す。
            "collected": "2026年6月12日",
            "collected_note": "原本 (xlsx) の収集日。2026-08-15 の差し替え版の収集日は未確認",
            "supersedes": "tools/v2-build/_source/2026-08-14_中山商店街_こどもの声台帳.xlsx "
                          "(69行/23箇所・履歴として保存)",
        },
        "counts": {
            "places": len(places),
            "voice_lines": total,
            "mapped_places": sum(1 for p in places if p.get("shops")),
            "pending_places": sum(1 for p in places if p.get("pending_confirmation")),
            "emoji_dropped": len(dropped_emoji),
        },
        "places": places,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print("wrote %s" % OUT)
    print("箇所 %d / 声 %d行 (確認待ち %d箇所)"
          % (doc["counts"]["places"], doc["counts"]["voice_lines"],
             doc["counts"]["pending_places"]))
    if dropped_emoji:
        print("絵文字を落とした行 %d件 (raw に原文あり):" % len(dropped_emoji))
        for name, raw in dropped_emoji:
            print("   %-18s %s" % (name, raw))


if __name__ == "__main__":
    main()
