#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""内閣府の「国民の祝日」CSV から holidays.json を作る。

なぜ要るか:
  「いま営業中」を出す店の多く (歯科・接骨院・クリニック) が祝日休み。
  祝日が分からないと、祝日に「いま営業中」と出してしまう。
  間違って営業中と出す方が、出さないより害が大きい (2026-08-09 ボス判断)。

  表の範囲外の日は判定しない = 安全側に倒す。だから covers を JSON に持たせ、
  gate が「今日から180日先まで表が届いているか」を見る。

出どころ: https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv
  (_source/ に取得日つきで控えてある。取り直す時は _source を更新してからここを回す)

usage: python make_holidays.py
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_source", "2026-08-14_naikakufu_syukujitsu.csv")
OUT = os.path.join(HERE, "holidays.json")
FROM_YEAR = 2026


def main():
    raw = open(SRC, "rb").read()
    text = raw.decode("cp932", errors="strict")   # 内閣府CSVは Shift_JIS

    dates, names = [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        ymd, name = line.split(",", 1)
        parts = ymd.split("/")
        if len(parts) != 3 or not parts[0].isdigit():
            continue                              # ヘッダ行
        y, m, d = (int(p) for p in parts)
        if y < FROM_YEAR:
            continue
        key = "%04d-%02d-%02d" % (y, m, d)
        dates.append(key)
        names[key] = name.strip()

    dates.sort()
    doc = {
        "_readme": "国民の祝日。ここに無い日は祝日でないと断定できる範囲 (covers) の中でだけ判定に使う。",
        "source": {
            "url": "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv",
            "file": "tools/v2-build/_source/2026-08-14_naikakufu_syukujitsu.csv",
            "fetched": "2026-08-14",
        },
        "covers": {"from": dates[0], "to": dates[-1]},
        "count": len(dates),
        "dates": dates,
        "names": names,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print("wrote %s" % OUT)
    print("%d日分 / %s 〜 %s" % (doc["count"], doc["covers"]["from"], doc["covers"]["to"]))


if __name__ == "__main__":
    main()
