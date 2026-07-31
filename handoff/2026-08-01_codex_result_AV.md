# Task AV — Task AU 引き出し線回帰の修復結果

## 結論

Task AU の高速化後に歩きズームだけで出た N37 / N38 と可視数低下を修復した。
修正は `tools/v2-build/template.html` のラベル配置対象1箇所だけで、文字幅キャッシュと格子探索は維持した。

Chromium 実ブラウザの 360x640・歩きズーム 2.0000px/m では、ラベル可視62件、店名60件、bbox交差0、★60、信号13、こどもの声11店の欠け0、N37/N38/N39相当0、JSエラー0だった。
`layoutLabels` は5試行の最悪値が 39.3〜48.3ms で、指定上限200msを下回った。

## 原因確認

提示された見立ては「ズームで変わる画面pxを、地図単位のまま再利用した」という方向では当たっていた。ただし、90px / 130px の比較式そのものは画面pxで正しかった。

- `cachedCandidateRects()` は `getBoundingClientRect()` 由来の★中心へ `gapPx` / `dyPx` を足し、候補矩形を画面座標で作る。
- `labelLeaderSegment()` と `Math.hypot(...)` も画面座標同士を比較していた。
- 真因は Task AU で追加された `labelLayoutInitialized ? inViewEntries : entries`。初回後は viewBox 内の店だけ再配置し、viewBox 外の店は前ズームの `s.lx/s.ly` を保持していた。
- `s.lx/s.ly` は画面pxのオフセットを `scale` で割って地図単位へ戻した値なので、既定ズーム時の値を歩きズームで使うと、旧オフセットが倍率比だけ画面上で拡大する。0.9198→2.0 の約2.17倍という観測と一致する。
- 同じ除外により、viewBox 外のラベルは現在の `placementGrid` にも入らず、引き出し線とラベルの交差相手として探索されなかった。N37の2件も同じ原因だった。
- 前セッションの停止直前ログでも、歩きズーム時の `visibleEntries` が12〜17件しかなく、残りのラベルが旧配置のまま残っていた物証がある。

## 修正

`tools/v2-build/template.html:1014-1018` で、ズームごとの配置対象を全 `entries` に戻した。

```js
// s.lx/s.ly stores a screen-pixel label offset converted back into map units.
// Every zoom must therefore re-layout every label ...
const visibleEntries=entries;
```

これにより、全ラベルの画面pxオフセットと引き出し線を現在倍率で再計算し、全ラベルを同じ衝突格子へ登録する。Task AU の文字幅キャッシュ、100px格子、候補矩形キャッシュ、優先度探索は残している。

## 格子探索の半径確認

探索に固定の100px半径は使っていない。`LABEL_GRID_PX=100` はセル幅だけである。

- `LabelSpatialGrid.keys(rect)` は矩形の左上セルから右下セルまで全セルを列挙する (`template.html:868-873`)。
- `placementBounds(rect, segment)` は、ラベル矩形 + collision pad と引き出し線の外接矩形の union を返す (`template.html:907-912`)。
- 登録時も検索時もこの union を使う (`template.html:1072`, `1079-1081`)。

したがって、引き出し線130px + ラベル幅が100pxを超えても複数セルへ展開され、探索範囲は切れない。回帰時の問題は半径不足ではなく、viewBox 外ラベルが格子へ登録されていなかったことだった。修正後の実ブラウザでは線と他ラベル/他★の交差が0件になった。

## 実ブラウザ検証

`node C:\tmp\AV_measure.js`、ローカルHTTP、Chromium `chrome.exe` で測定した。Python版 `gate.py` は Playwright IPC 作成が Windows サンドボックスに拒否され (`WinError 5`)、ブラウザ採点へ到達しなかったため、`--no-browser` は使わず、採点式と同じ DOM 幾何を Node/Chromium で測った。

### 地図

| 項目 | 360x640 既定 | 360x640 歩き | 390x844 既定 | 390x844 歩き |
|---|---:|---:|---:|---:|
| 実倍率 px/m | 0.8490 | 2.0000 | 0.9198 | 2.0000 |
| 可視 `text.shoplabel` | 59 | 62 | 59 | 62 |
| こどもの声ラベル欠け | 0 | 0 | 0 | 0 |
| bbox交差 | 0 | 0 | 0 | 0 |
| ★ | 60 | 60 | 60 | 60 |
| 信号 | 13 | 13 | 13 | 13 |
| N37相当: 線→他★/他ラベル | 0 | 0 | 0 | 0 |
| N38相当: 90/130px超過 | 0 | 0 | 0 | 0 |
| N39相当: 線付きラベル切れ | 0 | 0 | 0 | 0 |
| JSエラー | 0 | 0 | 0 | 0 |

歩きズームでは全60店名が表示され、距離表示2件を含む `text.shoplabel` が62件に戻った。

### N27

360x640で採点表同様に `layoutLabels` を包み、拡大3回・縮小3回を5試行した。MutationObserver由来の追加呼出しを含め各7回を記録した。

| 試行 | 最悪値 |
|---:|---:|
| 1 | 42.3ms |
| 2 | 48.3ms |
| 3 | 48.0ms |
| 4 | 42.4ms |
| 5 | 39.3ms |

5試行の最大48.3ms。指定上限200ms、gate上限400msの双方を下回る。

### N41 / N42 / N48 / N49 / N51

`node C:\tmp\AV_strip.js`、Chromium 360x640で再採点した。

| 項目 | 実測 | 判定 |
|---|---|---|
| N41 並び順 | 60行、東西とも順序違反0 | 0件 |
| N42 向かい合わせ | 誤差違反0 | 0件 |
| N48 カード間隔 | 最小8.0px、8px未満0 | 0件 |
| N49 声絞込 | 11件中8件可視（最低6） | 0件 |
| N49 先頭カテゴリ | 13件中8件可視（最低6） | 0件 |
| N49 「中山」検索 | 54件中12件可視（最低6） | 0件 |
| N51 装飾重なり | 全件0 / 声絞込0 / ケーキ検索0 | 0件 |

## ファイル境界と座標

| 検査 | 前 | 後 | 結果 |
|---|---|---|---|
| `tools/v2-build/gate.py` SHA-256 | `BAA07409F5799C3CCEAB812E841A9F556C9571DBF4A3C793C346F2F2D6A3A1F4` | 同左 | 不変 |
| `preview.html` SHA-256 | `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` | 同左 | 不変 |
| `tools/v2-build/preview.template.html` SHA-256 | `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` | 同左 | 不変 |
| `tools/v2-build/mapdata.json` SHA-256 | `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` | 同左 | 店・道路・信号座標不変 |
| `tools/v2-build/src_baseline.json` SHA-256 | `61A27D0CFF317B8CB3A25237BE362245C6C477B72069921F23994A3C56051EAA` | 同左 | 出典不変 |

- `python tools/v2-build/build_mapdata.py`: exit 0、shops=60 / roads=66 / signals=13。
- 生成物 `index.html` と `v2.html`: SHA-256一致 `5526CFA502FB3CF7EBF40F6C1DFE4311801580355DE1CF2520A5598378A3B04C`。
- `git diff --check`: exit 0。
- セッション開始時点で `gate.py`、`index.html`、`template.html`、`v2.html` は既にdirtyだった。本作業で手編集したプロダクトソースは `template.html` のみ。`index.html` / `v2.html` は指定ビルドによる再生成。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| 歩きズームの引き出し線・可視数回帰を修復 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html:1014` | Layer 2 | 独立 reviewer に差分確認を返す |
| 実ブラウザで地図回帰と速度を検証 | `C:\tmp\AV_measure.js` / Chromium / 最大48.3ms / N37・N38・N39相当0 | Layer 3 | reviewer の別セッション確認待ち |
| 通り表示回帰を実ブラウザ再採点 | `C:\tmp\AV_strip.js` / N41・N42・N48・N49・N51各0 | Layer 3 | reviewer の別セッション確認待ち |
| ビルド・保護ファイル・座標を確認 | `build_mapdata.py` exit 0 / 上記SHA-256 / `git diff --check` exit 0 | Layer 3 | push・deployは未実施 |

返却先: `ai:claude-code`（独立 reviewer）。
