# Task BD 実装結果（Layer 2 / ブラウザゲート未判定）

- 済んだこと: ボス直接FBを起点とする BD-1〜BD-8 を、指定された2ソースへ全件反映し、通常ビルドで本番生成物を更新した。
- 現在地: `python tools/v2-build/build_mapdata.py` は exit 0。`gate.py` は Playwright の起動が環境に拒否され、N1〜N52 の合否判定は未実行。
- 次の一手: Claude Code が実ブラウザで `gate.py` / `eyes.py` / ラベルと道路の重なり / パン / 写真 / 絞り込みを確認する。

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| BD-1〜BD-8 の実装と通常生成 | `tools/v2-build/template.html` / `tools/v2-build/build_mapdata.py` / `index.html` / `v2.html` / `tools/v2-build/mapdata.json`; build exit 0 | Layer 2 | `gate.py` と実ブラウザ確認。ボール=`ai:claude-code` |
| データ不変条件・構文の自己検査 | 本ファイルの「実測できた数字」および各生成物 | Layer 2 | 見た目・操作の意味検証は未実施 |
| 正本ゲート起動 | `python tools/v2-build/gate.py` → exit 1 (`PermissionError: [WinError 5]`) | Layer 2 | Playwright 起動前停止のため違反件数は未計測 |

## 変更点

### BD-1 信号統合

- `SIGNAL_MERGE_DISTANCE_M = 30.0` を追加した。
- `signals_raw.json` 由来の13ノードは削除せず、30m未満の組をビルド時にグループ化し、各グループの座標平均（2点では中点）を表示信号として出力するようにした。
- 統合後の件数・統合数・30m未満の残存対をビルド内ガードで検査するようにした。地図と二列表示は同じ `GEO.signals` を使う。

### BD-2 店名配置

- `labelCandidates()` を店舗の所属側だけに限定し、同じ側で横方向の余白と上下位置を段階的に探索するようにした。
- 実際に描画する道路幅（縁取りを含む）と参道を画面座標の線分グリッドへ入れ、店名矩形が道路線幅＋3pxの余白へ交差する候補を除外するようにした。
- 既存の店名・星・信号等の地図記号・固定UIとの衝突除外を維持し、候補が無い時だけ非表示にする。

### BD-3 坂の上と写真データ

- `PREVIEW_PHOTOS` を本番共通の `SPOT_PHOTOS` に昇格した。
- `中山の坂の上` を `cat=place`, `lat=38.294850`, `lng=140.836401`, `src=gsi_dem`、preview と同じ紹介文・写真1枚で本番へ追加した。
- 坂の地点は屋外地点として扱い、実座標 `lat/lng/tx/ty` は固定したまま、表示用 `x/y` だけを既存の同側・道路安全配置へ通した。
- 3公園各2枚＋坂の上1枚を本番 `mapdata.json` に出力するようにした。`--preview` 側の既存固定座標・写真経路は残した。

### BD-4 本番写真UI

- `preview.template.html` の `setPhotoPicture` / `createPhotoPicture` / `buildPhotoGallery` / ライトボックス4関数を本番へ移植した。
- 写真を住所の下、ステータス類の上へ挿入した。`s.photos` が無い場合はDOMを追加しない。
- `<picture>` の webp→jpg フォールバック、`loading='lazy'`, `decoding='async'`, `aspect-ratio`、サムネの `aria-pressed`、切替の `aria-live`、ライトボックスのfocus復帰を追加した。
- Esc はライトボックスを先に閉じ、その次の Esc で詳細シートを閉じる。

### BD-5 地図パン

- `#viewport` に1本指ドラッグとマウスポインタのドラッグを追加した。
- client px を現在の viewBox 比率で地図座標へ換算し、既存 `clampViewBox()` を通して範囲を制限する。
- 10px超で `singleTouch.moved` / mouseの `moved` を立て、店クリックを抑止する。2本指時は `pinchGesture` を優先する。

### BD-6 道路名

- 地図側の `text.roadname` 生成処理を削除した。公園名・河川名は維持した。
- 二列表示の `.strip-road-label` は維持した。

### BD-7 引き出し線

- 地図側の `.label-leader` / `.faraway` と `labelLeaderPaths` の生成・更新処理を削除した。
- 実在する参道 `.sando` と debug/edit 用表示は維持した。

### BD-8 絞り込み

- 絞り込み状態を `body.map-filtering` で示し、非該当 `.hit.dim` の `.shoplabel` だけを非表示にした。
- 非該当の星は従来どおり opacity 0.25 で残す。

## 実測できた数字

- 通常ビルド: exit 0。`shops=61`, `roads=66`, `signals=11`。生成 `mapdata.json` は32,239文字・36,239 UTF-8 bytes（ビルダー内の非圧縮診断値は35,914文字）。
- 統合後の61店・11信号をbaselineにした通常ビルドを2回連続実行: 2回とも exit 0。`index.html` / `v2.html` / `mapdata.json` は再実行前後で全てSHA-256一致。
- 信号: 生ノード13、表示11、統合グループ2、統合ノード2。既知の2組の出力中点は `[580.5,1263.3]` と `[278.7,856.7]`。
- 出力信号同士の30m未満の対: 0組。最短距離: 142.587m。
- 追加後の既存60地点について、HEAD版との `lat/lng/tx/ty` 差分: 0件。
- 坂の上: `lat=38.29485`, `lng=140.836401`, `tx=427.8`, `ty=270`, 表示位置 `x=440`, `y=271`, `src=gsi_dem`。
- 道路: 66本。HEAD版 `mapdata.json` の `roads` 配列との完全一致: true。
- 写真: 4地点・7レコード（2+2+2+1）。対応する webp/jpg 14ファイルの欠落: 0。
- 写真ヘルパー群: production と preview の関数ブロック完全一致: true（5698 bytes）。
- 地図道路名・店名引き出し線の実行時生成パターン: 0件。`.strip-road-label` と `.sando` は残存。
- `tools/v2-build/template.html`, `index.html`, `v2.html` のインラインJavaScript構文検査: 3ファイルとも成功。
- `index.html` と `v2.html`: SHA-256一致 (`430C9C1BAD223DAA7DB39EA37838D0161735BF6E4DC1B30D80AF455AD8714F12`)。
- `git diff --check`: exit 0。
- 禁止3ファイル (`tools/v2-build/gate.py`, `preview.html`, `tools/v2-build/preview.template.html`) の `git diff --exit-code`: exit 0。

## 測れなかったもの

- `gate.py` の N1〜N52 違反件数とPASS/FAIL。コマンドは起動を試みたが、`sync_playwright()` が子プロセスを作る段階で `PermissionError: [WinError 5] アクセスが拒否されました` となり exit 1。その後、例外処理でも `REND` が `None` のため `TypeError` が発生した。違反判定へ到達していないので、**gate 合否判定は未実行**とする。`gate.py` 自体は無変更。
- 既定ズーム・歩きズームにおける「表示店名矩形と道路線」の重なり件数。
- 拡大3回後の100pxドラッグによる viewBox 実移動量、およびドラッグ後に詳細シートが開かないこと。
- 写真の実表示、サムネ切替、ライトボックス、Esc順序、focus復帰、写真なし詳細のピクセル差。
- 絞り込み中に実際に見えている非該当店名の件数。
- `--preview` 生成物の実ブラウザ差分（preview用コード経路は保持したが、禁止されたpreview生成物を更新しないため通常ビルドのみ実行）。
- `eyes.py` と目視品質。

commit / push は実施していない。
