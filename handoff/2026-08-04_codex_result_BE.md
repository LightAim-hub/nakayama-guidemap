# Task BE 実装結果（Layer 2 / 正本ブラウザゲート未実行）

- 済んだこと: tools/v2-build/template.html だけを手編集して BE-1〜BE-4 を反映し、通常ビルドで index.html / v2.html / tools/v2-build/mapdata.json を更新した。
- 現在地: build_mapdata.py は exit 0。gate.py は Playwright 起動前の PermissionError: [WinError 5] で exit 1となり、N1〜N52のブラウザ判定は未実行。
- 次の一手: Claude Code が実ブラウザで正本 gate.py を実行し、店名可視数・N26・N31・道路との重なり0件・絞り込み中の全該当店名を確認する。

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| BE-1〜BE-4の実装と通常生成 | tools/v2-build/template.html / index.html / v2.html / tools/v2-build/mapdata.json; build exit 0 | Layer 2 | 正本ブラウザgate。ボール=ai:claude-code |
| 構文・データ・禁止対象・BD回帰の静的検査 | 本ファイルの「実測できたこと」 | Layer 2 | 見た目とブラウザ実測は未判定 |
| 正本gateの起動 | python tools/v2-build/gate.py → exit 1 (PermissionError: [WinError 5]) | Layer 2 | Playwright起動前停止のため合格扱いにしない |

## 実装内容

### BE-1 店名の可視数を戻す

- 道路との余白を、handoffで許可された 3px → 2px にした。
- 同じ側だけを使う条件は維持し、横方向を17段階、上下方向を2px刻み中心の37段階まで増やした。
- 配置優先度を「こどもの声あり → 有効な公式URLまたは地点/公園 → その他」にした。
- 同じ優先度では、現在置ける候補が少ない店から先に置く制約優先の配置へ変えた。
- 候補は道路・他店名・他店の★・信号・固定UI・自店への帰属条件をすべて満たすものだけ採用する。

### BE-2 こどもの声の店

- こどもの声あり11地点は最上位のまま、拡張した候補集合を既存の優先配置探索へ渡す。
- 通常店より先に確定し、低優先ラベルだけを退避できる既存の優先度分離を維持した。

### BE-3 絞り込み中の再配置

- フィルタ状態では matchesFilter() が真の店だけをラベル配置対象とする。
- 非該当の店名と声バッジを配置計算から外し、フィルタ変更ごとに scheduleMapScaleStyles() で再配置する。
- 非該当の★は従来どおり薄い状態で残す。

### BE-4 お店一覧の間隔

- #listrows の上余白を 8px → 10px にし、先頭の店ボタンと「閉じる」の間隔を2px増やした。

## 実測できたこと

- python tools/v2-build/build_mapdata.py: exit 0。shops=61, roads=66, signals=11。
- 同じ通常ビルドを連続実行し、3生成物は再実行前後でSHA-256一致。
  - index.html / v2.html: AA1BD0E9D9E8E62D197249873B37CA8BD4AAE0B23B20914E97FC60F668A47B97
  - tools/v2-build/mapdata.json: 593A1A6279E24C8609222FEC7852EBF4EB66CFF1D67B9E14E0477F31DF8D7D67
- tools/v2-build/template.html, index.html, v2.html のインラインJavaScript構文検査: 3ファイルとも成功。
- python tools/v2-build/gate.py --no-browser: exit 1。静的データ経路ではN1〜N52の列挙上は違反0件・歩ける店61/61だったが、全体は「ブラウザ実測なし」1件でFAIL。この結果をN26/N31の合格証拠には使っていない。
- 店61件の lat/lng/tx/ty は着手前後でSHA-256一致: 162463bf5c4936ab58f8816397c7fd7140f9e07a30a73d0da1b3291571760720。
- 禁止対象と生成元の着手前後SHA-256一致:
  - tools/v2-build/gate.py: D24AD6D68319A295178955A7F6753C48C8A7D7AD07153342AC31C6DE7B846058
  - preview.html: 87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44
  - tools/v2-build/preview.template.html: ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC
  - tools/v2-build/build_mapdata.py: 94EFA65C9E87C627231A0821CB15A8B2663859D514AD82E4E8750CB498130A8F
- BD回帰の静的検査:
  - 信号11点、30m未満0組、最短142.587m。
  - 写真4地点・7レコード、対応webp/jpgの欠落0。
  - 中山の坂の上は生成データに存在。
  - パン処理 panViewBoxByClientDelta と写真UI buildPhotoGallery は生成HTMLに存在。
  - 地図道路名と店名引き出し線の実行時生成パターンは0件。参道 .sando は維持。
- git diff --check: exit 0。

## 測れなかったこと

- python tools/v2-build/gate.py のN1〜N52と全体判定。sync_playwright() が子プロセス用pipeを作る段階で PermissionError: [WinError 5] となり、その後gate側の例外処理も REND is None により TypeError で停止した。違反判定へ到達していないため、正本gateは未実行とする。
- 既定ズーム40件以上・歩きズーム61件という店名可視数。
- N26=0、N31=0、店名と道路の重なり0件。
- 声で絞り込んだ際、画面内の該当11地点すべての店名が表示されること。
- 写真・パン・坂の上を含むBD合格項目の実ブラウザ回帰。

commit / push は実施していない。
