# Codex タスク BJ — 320px で地図の見出しが「なかやま商店街マッ」と切れる

前段: BG / BH / BI の差分が作業ツリーにある。`python tools/v2-build/gate.py` は **PASS（違反0件）**。
**これを崩さずに直す。**

## 現象（実測・320×568 の地図画面）

見出しが `なかやま商店街マッ` で切れている。**省略記号が無く、語の途中でぶつ切り**なので壊れて見える。

原因は自分たちで作った。BG-4 で `絞り込み` ボタンを見出し帯に足したため、
`body.map-open header` の3列が `minmax(112px,1fr) / minmax(72px,112px) / 90px` になり、
320px 幅では見出しに 80px 程度しか残らない。`header` は `overflow:hidden` で、
`body.map-open header h1` には `text-overflow` の指定が無い。

360px では切れていない（`なかやま商店街マップ` が全部出る）。**320px だけの問題。**

## 直すこと

地図画面の見出しが**切れる時は省略記号（…）で終わる**ようにする。
`body.map-open header h1` に `overflow:hidden; text-overflow:ellipsis;` を足すのがいちばん小さい。

- 見出しを消さない（N46 = 地図の画面に見出しと戻る手段がある）
- 帯を高くしない（`--map-head-h:44px` のまま）
- 360px / 390px で今の見え方を変えない
- `✕ 通り / へもどる` の2行はこのままでよい（1文字だけの行が無ければ合格＝N58）

## 制約

- `tools/v2-build/gate.py` は変更禁止（N58 を含め Claude Code の管轄）
- 触らない: `preview.html` / `preview.template.html` / 道路データ / 店の座標
- BG / BH / BI の実装に触らない
- `index.html` は手で編集しない / push はしない

## DOD

1. `python tools/v2-build/build_mapdata.py` が exit 0
2. `python tools/v2-build/gate.py` が exit 0（サンドボックスで回らなければその旨を書く）
3. 320×568 の地図画面で、見出しが切れる場合は末尾が `…` になっている
