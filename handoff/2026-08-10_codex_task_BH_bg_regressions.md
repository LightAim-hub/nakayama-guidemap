# Codex タスク BH — BG で入った退行2件を直す

前段: `handoff/2026-08-10_codex_task_BG_review_backlog.md`（BG-1〜BG-7 は実装済み・作業ツリーに残っている）
土台: `83c260a` + BG の未コミット差分

BG-1/2/3/6/7 は問題なし。**BG-4 と BG-5 が gate を落としている。**
`python tools/v2-build/gate.py` → **FAIL（違反4件）**。3回連続で同じ結果（まぐれではない）。

## BH-1 — BG-4 が N31 を落とした

```
【N31】押せるもの同士が近すぎない — 違反 2件
  「こどもの声 11件。押すと条」[147,0,259,44] と「通りへもどる」[264,0,354,44] が
   5.0px しか離れていない (最小8) [360x640 地図で絞り込み中 ほか5]
  「絞り込み。押すと条件を変更で」[147,0,259,44] と「通りへもどる」[264,0,354,44] が
   5.0px しか離れていない (最小8) [360x640 地図 ほか5]
```

**原因**: `body.map-open header` の `gap:5px`（`template.html` 666-667行）。
`#mapFilterBadge` を押せるボタンにしたので、これまで表示専用だった隙間が
「押せるもの同士の隙間」として N31 の対象になった。

**直す**: 地図の見出し帯で、押せるもの同士が **8px 以上**あくようにする。
360px 幅で3列（見出し / 絞り込み / 通りへもどる）が収まり続けること。
**見出しの帯を高くしない**（`--map-head-h:44px` は変えない）。

## BH-2 — BG-5 が N49 を落とした

```
【N49】絞り込んだ結果が1画面で見渡せる — 違反 2件
  「健康・美容・医療」で絞り込み で13件のはずが、画面には5件しか見えない (最低6件) [640x360]
   {"t":13,"v":5,"scrollTop":0,"svTop":38,"svH":200,"firstTop":90,"rowH":45,"helpH":0}
  こどもの声で絞り込み で11件のはずが、画面には5件しか見えない (最低6件) [640x360]
```

**原因**: `.shop-total-summary`（`<p id="shopTotalSummary">`）を `<main id="stripview">` の
**中**に置いたため、横向きの低い画面（640×360）で一覧の見える行が 6 → 5 に減った。
`#stripview` の高さは 200px しかなく、1行 45px なので 27px の追加が1行ぶん効く。

**直す**: **全店数は入口の画面に出したまま**、`#stripview` の行数を削らないようにする。
やり方は任せる。参考になる事実:

- `header p` は `@media(max-width:759px)`（131行）で消えている＝スマホでは使えない
- `header h1 small` は `@media(max-width:480px)`（142行）で消えている＝390px幅では使えない
- 横向きの低い画面は `@media(orientation:landscape) and (max-height:480px)`（781行）
- `.strip-guide` は `body.strip-compact` で消える（793行）

**合格**:
1. `gate.py` の N49 が違反0
2. 下の4通りすべてで、開いた瞬間の画面に全店数（`GEO.shops.length` 由来）が読める文字で出ている
   - 390×844（縦）/ 320×568（せまい縦）/ 640×360（横）/ 1280×800（PC）
3. 320px 幅・`html{font-size:24px}` で枠外に出ない（N28/N29）

## 制約（BG と同じ）

- **`tools/v2-build/gate.py` は変更禁止。** 検査を通りやすくする変更は不正
- 触らない: `preview.html` / `preview.template.html` / 道路データ / 店の座標
- 直すのは `tools/v2-build/template.html`（必要なら `build_mapdata.py`）のみ
- `index.html` は手で編集しない（`build_mapdata.py` の生成物）
- BG-1/2/3/6/7 の実装には触らない
- commit までしてよい。**push はしない**

## DOD

1. `python tools/v2-build/build_mapdata.py` が exit 0
2. `python tools/v2-build/gate.py` が **exit 0（PASS・違反0件）**
   ※ サンドボックスで Playwright が起動できない場合はそう書いてよい。こちらで回す
3. `git diff --stat` に `gate.py` / `preview*` / 座標データ が出てこない

## 返すもの

BH-1 / BH-2 それぞれ「何行目をどう変えたか」を1〜2行。gate の exit code。`git diff --stat`。
