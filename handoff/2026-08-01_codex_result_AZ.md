# Task AZ 実装・検証結果

## 現在地

Task AZ の3塊は `tools/v2-build/template.html` に実装し、最終生成物を実 Chromium で再計測した範囲では対象違反を0件にしました。ただし正本ゲート未取得のため、handoff上限は Layer 2（実装物を再読込可能）です。

ただし正本の `python tools/v2-build/gate.py` は、評価開始前の Python Playwright 起動時に Windows sandbox が名前付きパイプを拒否し、`PermissionError: [WinError 5]` で終了しました。このため、N1〜N52の公式な全0件判定は未取得です。`--no-browser` の結果は合否根拠にしていません。

次の一手は、sandbox外の通常端末で正本コマンドをそのまま1回実行し、独立 reviewer が結果を確認することです。ボールは `ai:claude-code` です。

## 実装内容

### 塊A — 操作ボタンと地図面積

- 現在地・全体・拡大・縮小を地図右下の44px丸ボタンへ移し、8px間隔で配置した。
- 縦が短い横画面だけは、下半分に収めるため同じ4ボタンを2列×2段にした。
- 下帯は `© OSM ⓘ / お店一覧 / 通りへ` の3要素だけにし、56pxへ縮めた。
- 位置情報ステータスは地図上端の小型pillとし、ラベル配置のkeep-out対象に加えた。

実 Chromium 計測:

| viewport | 地図高/画面高 | 地図充填 | ボタン最小 | 最小間隔 | 下半分違反 |
|---|---:|---:|---:|---:|---:|
| 360×640 | 540/640 = 84.4% | 100% | 44px | 8px | 0 |
| 375×667 | 567/667 = 85.0% | 100% | 44px | 8px | 0 |
| 390×844 | 744/844 = 88.2% | 100% | 44px | 8px | 0 |
| 428×926 | 826/926 = 89.2% | 100% | 44px | 8px | 0 |

### 塊B — 星・信号・ラベル帰属

- 既定ズームと全体表示の星は14pxを維持した。
- 歩きズームでは道路との実交差を避けるため、星の地図上直径を最大5.45mに制限した。2px/m時の画面表示は10.9px。N12の判定対象である既定ズームは14pxのまま。
- この制限が必要な幾何上限は、EndRollが5.8718m、藤倉設備工業が5.5037m。店・道路座標は変更していない。
- ラベル帰属の最近傍比率を厳しくし、Dogsalon Blancheとフラワー中山を含む曖昧な配置を退けた。
- 信号は座標データを変えず、星と重なる時だけ表示を最大10pxずらす候補選択を追加した。既定ズームでは13信号中2件が±10px、歩きズームでは全件0pxだった。

### 塊C — 引き出し線

- 引き出し線と他ラベルの判定に3pxの安全余白を加えた。
- 線の始点を星の内側2pxに固定し、浅い曲線にして「ラベルが離れているのに線なし」の中間状態をなくした。
- おたからや、ん daccha とこやを含め、線の欠落・ラベル横切り・過長・途中切れを実 Chromium 計測で各0件にした。

## 最終検証

| 検証 | 結果 | 物理証拠 |
|---|---|---|
| 生成 | exit 0、shops=60 / roads=66 / signals=13 | `python tools/v2-build/build_mapdata.py` |
| HTML JavaScript構文 | exit 0、index/v2各inline script 1本をcompile | `index.html`, `v2.html` |
| diff構文 | exit 0 | `git diff --check` |
| 実 Chromium・既定ズーム | 360/390とも N14候補0、信号×星0、線横切り0、線欠落0、bbox交差0、星60、信号13 | 最終生成 `index.html` に対する2026-08-01再計測 |
| 実 Chromium・歩きズーム | 360/390とも N3候補0、N14候補0、信号×星0、線横切り0、線欠落0、bbox交差0、星60、信号13 | 最終生成 `index.html` に対する2026-08-01再計測 |
| 可視ラベル | 縦画面55〜60件、歩きズーム62件、bbox交差0 | 同上 |
| こどもの声 | 対象の縦画面・既定/歩きズームで欠落0 | 同上 |
| 配置速度 | 5系列のworst 38.8〜55.0ms（要求200ms以下） | 同上 |
| 現在地 | 押下前0回、押下後1回、外部request 0、local/session storage 0、範囲外/拒否時view不変 | 同上 |
| 正本ブラウザゲート | **未判定**。exit 1（評価開始前） | `python tools/v2-build/gate.py` → `PermissionError: [WinError 5]`、続いて既存例外処理の `TypeError: REND is None` |

注: 静的診断目的で実行した `--no-browser` は、ユーザー指定どおりPASS証拠から除外した。

## ファイル境界・保護対象

手編集は `tools/v2-build/template.html` と本結果文書のみ。`index.html` と `v2.html` は指定のビルドスクリプトによる生成物。本セッション開始時点ですでにdirtyだった `tools/v2-build/gate.py` は触っていない。

| ファイル | SHA-256 |
|---|---|
| `tools/v2-build/template.html` | `1A1AB39660A9375672EB0514CD715F4AE939165979F7D58680D527BB021BC7CD` |
| `tools/v2-build/mapdata.json` | `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` |
| `index.html` / `v2.html` | `7E09075470E93C6008C60210395E9F8933557F2A7148FC65DEE438DA569AA22F` |
| `tools/v2-build/gate.py`（既存dirty・本セッション不編集） | `92832D510ADBFF8ED2AC135E110D6B85024CB2F329DA05A3B0C14FD17985FBA6` |
| `preview.html` | `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` |
| `tools/v2-build/preview.template.html` | `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` |

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| Task AZ 3塊の実装、再生成、実 Chromium再計測 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html` / build exit 0 / 本文の計測値 | Layer 2 | sandbox外で公式 `python tools/v2-build/gate.py` を実行し、独立reviewer確認。ボール=`ai:claude-code` |
