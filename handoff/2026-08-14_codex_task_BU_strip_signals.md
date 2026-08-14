# BU: 二列ビューに「中山バス通りにない信号」を7基描いている

Issue: <https://github.com/LightAim-hub/nakayama-guidemap/issues/53>
owner_label: `ai:codex` / codex_mode: implement
**BT (`2026-08-14_codex_task_BT_voices_master_and_corrections.md`) を先に終わらせてから着手すること。**

## 起点

あみさん（2026-08-14）:

> 通りの地図の位置関係がズレている。信号機の場所とか

`diag_geometry.py` は G3=0基（全信号が交差点上）/ G4 取りこぼし0（OSMと1対1）と言っていた。
だが**あの検査は地図の上でOSMとの整合しか見ていない**。二列ビューは誰も測っていなかった。

`tools/v2-build/diag_strip_order.py`（新規・私が作った）で測った実測値:

```
【S5】二列に出している 11基 のうち、通り沿いでない 7基 (最遠 622.3m)
  信号0  (x1143,y655)  通りまで 584.5m  🔴 別の道路
  信号1  (x197,y80)    通りまで 294.4m  🔴 別の道路
  信号2  (x228,y316)   通りまで 204.9m  🔴 別の道路
  信号3  (x262,y630)   通りまで 261.7m  🔴 別の道路
  信号4  (x-15,y1587)  通りまで 590.6m  🔴 別の道路
  信号9  (x279,y857)   通りまで 292.2m  🔴 別の道路
  信号10 (x1232,y544)  通りまで 622.3m  🔴 別の道路
  → 通り沿いは 信号5 / 6 / 7 / 8 の4基だけ (いずれも 0.0m)
```

原因は `tools/v2-build/template.html` の `buildStrip()`:

```js
(GEO.signals||[]).forEach(p => {
  const signal=stripChild('div','strip-signal');
  signal.style.top=(STRIP_TOP_PAD+(p[1]-stripYMin)*STRIP_PX_PER_M)+'px';
  ...
});
```

**絞り込みが無い。** 二列は「中山バス通り」一本の絵なのに、GEO の信号を全基そこへ置き、
位置は `y`（南北）だけで決めている。**別の道路の信号が、バス通りの信号として並ぶ。**
最大 622m 離れた信号が通りの上に乗っているので、地元の人が見れば「信号の場所が違う」と分かる。

（地図ビューは真の座標に描いているので正しい。**壊れているのは二列だけ**。）

なお、S1（通りのy単調性）/ S2（歩く順と表示順）/ S3（信号と店の前後関係）/ S4（東西判定）は
それぞれ 反転0 / 入替3組（うち2組は 1.2m・5.8m の誤差）/ 食い違い0 / 食い違い0 だった。
**つまり原因はこの絞り込み漏れ1点**で、並び順そのものは壊れていない。

## やること

### 1. `template.html` — 二列の信号を通り沿いだけにする

`buildStrip()` の信号ループで、**通りまでの距離が 30m 以内の信号だけ**を置く。
距離の計算には**既にある `streetDistance(px, py)` をそのまま使う**（同じファイルの上の方で定義済み。
2026-08-10 に「通りからの最短距離」を出すために作ったもの。新しく書かない）。

```js
(GEO.signals||[]).filter(p => streetDistance(p[0], p[1]) <= STRIP_SIGNAL_MAX_M).forEach(p => { ... });
```

- 閾値は名前つき定数 `STRIP_SIGNAL_MAX_M = 30` にして、他の STRIP_* 定数の並びに置く
- **地図ビューの信号は絞らない**（あちらは真の座標に描いていて正しい）
- 絞った結果 4基になる。`layoutStripSignals()` のまとめ処理はそのままでよい

### 2. `gate.py` — N66 として焼く

| 項目 | 中身 |
|---|---|
| N66 | 二列ビューに出ている信号がすべて中山バス通り沿い（`streetDistance` ≤ 30m）である。1基でも外れたら FAIL |

実ブラウザで `.strip-signal` を数え、`data-y` と GEO から距離を出して判定する。
**直す前の版に当てて「違反7件で FAIL」することを必ず確認してから**、直した版の PASS を出す
（N57・N58 で2度、検査を足したのに何も捕まえていなかった事故がある）。

## DOD

```bash
python tools/v2-build/build_mapdata.py     # exit 0
python tools/v2-build/gate.py              # exit 0 / N1〜N66 違反0
python tools/v2-build/diag_strip_order.py  # S5 の「通り沿いでない信号」が 0基
```

- 二列の `.strip-signal` = **4基**（直す前は11基）
- 地図ビューの信号 = **11基のまま**（減っていないこと）
- 直す前の版で N66 が違反7件で FAIL することの実測
- `git diff --stat` と `index.html` のバイト数を報告

コミットは Issue #53 参照。push してよい。submit gate まで到達したら終わってよい。
