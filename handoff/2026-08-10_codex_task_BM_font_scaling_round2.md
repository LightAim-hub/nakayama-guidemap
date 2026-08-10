# BM: BL の直しで作った副作用を取る（文字サイズ対応・2周目）

BL は gate を通したが、**上限のつけ方に3つ問題がある**。実測で確認済み。
`gate.py` に **N60「同じ行で店名が住所より小さくない」**を足したので、いまは **FAIL 2件**。

## 触ってよい / いけない

- 触る: `tools/v2-build/template.html`
- **触らない: `tools/v2-build/gate.py` / `index.html` / `v2.html` / `mapdata.json` / `official_details.json`**

## 直すもの

### 1. 既定の文字設定で見出しが小さくなった（いちばん重い）

`header h1{ font-size:clamp(17px,1.2rem,18px) }` にしたため、**普通の端末で 19.2px → 18px に縮んだ**。
崩れを直すために、何もしていない人の見た目を劣化させてはいけない。

実測 (390x844・端末16px):

| | 前 | BLの後 |
|---|---|---|
| `header h1` | 19.2px | **18px（縮んだ）** |

**上限の下限側は、いまの見た目の値を下回らないこと。** `header` は `height:auto` に変えて
伸びられるようになったので、見出しはもっと上まで伸ばしてよい（目安 24px 程度まで）。
他の文字（`.shop-total-summary` `.chip .lbl` `.searchbar input` `#searchstatus`
`.strip-shop-name` `.lrow .lname` `.lrow .laddr` `.detail-nav button` `header p`）は
16px 端末で前と同じだったので、そのままでよい。

### 2. 文字を大きくすると 住所が店名より大きくなる（N60・FAIL 2件）

`.lrow .lname` に上限18pxを付けた一方、`.lrow .laddr` は上限が無く伸び続ける。

| 端末の文字 | 店名 | 住所 |
|---|---|---|
| 150% (24px) | 18.0px | 21.0px |
| 200% (32px) | 18.0px | **28.0px** |

一覧の主役は店名なので、これは主従が逆。**本文の上限は個別に決めず、
一括で「ここまで」を決めて 店名・住所・詳細に同じ考え方で当てること。**
店名の上限を上げるのでも、住所を同じ上限で止めるのでもよいが、
**どの文字サイズでも 店名 ≧ 住所** になること（N60 がこれを見る）。

### 3. `.chip .lbl` の折り返し規則を、理由の説明なしに裏返した

```diff
- .chip .lbl{ word-break:keep-all; overflow-wrap:break-word; }
+ .chip .lbl{ word-break:keep-all; overflow-wrap:normal; }
```

すぐ上のコメントは「`anywhere` は最小幅を1文字まで潰し、キーボード表示時にチップ同士を
重ねたため `break-word` にする」と、**あみさんの指摘への対応理由**を書いている。
コメントと実装が食い違っている状態にしないこと。
**`break-word` に戻して直せるなら戻す。** どうしても `normal` が要るなら、
コメントを「なぜ変えたか・前の問題が再発しない理由」に書き換えること。

## 合格条件

1. `python tools/v2-build/build_mapdata.py` が通る
2. `python tools/v2-build/gate.py --target index.html` が **PASS（違反0件・N1〜N60）**
3. 端末16px（390x844）で `header h1` が **19.2px 以上**、他の文字が BL 前と同じ
4. 歩ける店 60/60 / JSエラー 0

`result.txt` に、変えた宣言とその前後の実測値（16px と 32px の両方）を表で貼ること。
