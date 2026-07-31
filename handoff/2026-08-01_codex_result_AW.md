# Task AW — N14「中山不動産」帰属修正結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

手編集したプロダクトソース: `tools/v2-build/template.html`

## 結論

歩きズーム 2.0px/m の「中山不動産」は、通常候補の近さが曖昧な場合に既存の引き出し線候補へ進むようになった。
実Chromiumでは N14 は0件。引き出し線は360x640 / 390x844とも42.55pxで、90px上限内、他店の★・ラベルとの交差0、画面外切れ0だった。

既定ズームの候補順は変えず、ラベル可視は既定59件・歩き62件、bbox交差0件を維持した。

## 原因

AVの変更で候補選択が変わった結果か、という見立ては当たっていた。ただし、AVの「全ラベルを現在倍率で再配置する」修正自体は必要で、戻してはいけない。

実ブラウザでAV前の条件をresponse差替えだけで再現して比較した。

| 条件 | 歩きズームの再配置対象 | 中山不動産 |
|---|---:|---|
| AV後の現行 | 60件 | 通常候補 `side=+1 / gap=7.5px / dy=4px` |
| AV前を再現 | 17件 | 既定ズーム時の引き出し線配置を保持 |

AV後に選ばれた通常候補には、候補評価と実描画で原点が揃っていない問題が潜んでいた。

- 候補キャッシュは、描画された★の `getBoundingClientRect()` 中心を原点にしていた。
- `setLabelPosition()` は、店の地図座標 `s.x / s.y` を原点にしていた。
- ★の描画bbox中心と店の地図座標の画面位置には、縦方向に0.495pxの差があった。

そのため、同じ候補が評価時と描画後で次のように変化した。

| 測定 | 自分の★ | 最近傍の中杜建設 | 帰属比 |
|---|---:|---:|---:|
| 候補キャッシュ | 7.50px | 9.50px | 0.7895 — 実装上限0.79内 |
| 実DOM | 7.50px | 9.01px | 0.8329 — gate上限0.80超過 |

キャッシュ矩形の上端は8.005px、実DOMは8.500pxで、差は0.495pxだった。AVで全60件を歩きズームごとに再配置するようになり、この通常候補が初めて選ばれてN14が表面化した。

## 修正

`tools/v2-build/template.html:1034-1046, 1108-1143, 1152-1165, 1206-1220` を変更した。

- 拡大域 (`scale >= 1.5`) では、店の地図座標を画面へ変換した `screenOrigins` を作る。
- 通常候補の帰属判定と引き出し線判定だけ、実描画と同じ原点へ0.495px分平行移動した矩形で評価する。
- 衝突格子、候補列、文字幅キャッシュ、優先度探索の順序は変えない。
- 既定ズームでは従来の★bbox中心を使い、可視59件と候補順を保持する。

これにより曖昧な通常候補を採用せず、既存のAQ経路で引き出し線候補へ進む。特定店名のハードコード、座標変更、優先度ラベルの退避は使っていない。

## 実ブラウザ検証

Python版 `gate.py` は、このmanaged seatでPlaywright子プロセス用named pipeの作成が `PermissionError: [WinError 5]` になり、ブラウザ採点へ到達しなかった。続く既存例外処理も `REND=None` へ代入して `TypeError` になり exit 1だった。`gate.py` は変更していない。

`--no-browser` の表示は総合合否根拠に使わず、同じ生成HTMLをNode Playwrightから同梱Chromium 148で開き、gateと同じDOM幾何・丸め・閾値を測った。

### N1〜N19

| 項目 | 違反 |
|---|---:|
| N1 / N2 / N3 / N4 / N5 / N6 / N7 / N8 / N9 / N10 | 各0件 |
| N11 / N12 / N13 / N14 / N15 / N16 / N17 / N18 / N19 | 各0件 |

- N4: 既定・歩きとも、線なしラベルで自分以外の★が同距離以下になるもの0件。
- N11: 既定ズームのバス通り12.000px（床12px）。
- N12: 最大 `★ / バス通り = 0.599999`（上限0.60）。
- N13: 他店の★を内包するラベル0件。
- N14: 既定・歩きとも0件。中山不動産は歩きズームで引き出し線あり。
- N17: 固定UIが10%以上覆うラベル0件。
- N18: こどもの声バッジの最近傍取り違え0件。
- N19: 信号と★・ラベルの重なり0件。
- N1/N2/N5〜N10/N15/N16の静的入力である `mapdata.json` / `src_baseline.json` は作業前後同一SHA-256。道路幅・★サイズも実ブラウザで再測した。

### 必須回帰

| 条件 | 実測 |
|---|---|
| N26 | こどもの声11店のラベル欠け0 |
| N27 | 360x640、5試行の最悪47.6ms（上限200ms） |
| N37 | 引き出し線→他★/他ラベルの交差0 |
| N38 | 中山不動産42.55px、90px超過0 |
| N39 | 線付きラベルの画面外切れ0 |
| N41 | 60行、東西とも順序違反0 |
| N42 | 向かい合わせ誤差違反0 |
| N48 | 最小間隔8px、8px未満0 |
| N49 | 声8件 / 先頭カテゴリ8件 / 「中山」検索12件を1画面表示（各最低6） |
| N51 | 通常・声絞込・ケーキ検索で道路名/信号の装飾重なり0 |

### 可視数・基礎要素

| ビューポート | 既定ラベル | 歩きラベル | 歩き店名 | bbox交差 | ★ | 信号 |
|---|---:|---:|---:|---:|---:|---:|
| 360x640 | 59 | 62 | 60 | 0 | 60 | 13 |
| 390x844 | 59 | 62 | 60 | 0 | 60 | 13 |

JS errorは両幅・歩きズームで0件だった。

## ビルド・ファイル境界

- `python tools/v2-build/build_mapdata.py`: exit 0、shops=60 / roads=66 / signals=13。
- 生成HTMLのinline JavaScript parse: `index.html` / `v2.html` とも exit 0。
- `git diff --check`: exit 0。
- `index.html` と `v2.html` は同一SHA-256 `B0C7B1FF4476158BD14CDA8CDE8EB96C678CAE45E8977CCBDA16FE188405A143`。

| 保護対象 | 作業前後SHA-256 |
|---|---|
| `tools/v2-build/gate.py` | `BAA07409F5799C3CCEAB812E841A9F556C9571DBF4A3C793C346F2F2D6A3A1F4` |
| `preview.html` | `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` |
| `tools/v2-build/preview.template.html` | `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` |
| `tools/v2-build/mapdata.json` | `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` |
| `tools/v2-build/src_baseline.json` | `61A27D0CFF317B8CB3A25237BE362245C6C477B72069921F23994A3C56051EAA` |

店・道路・信号の座標は変更していない。手編集したプロダクトソースは `template.html` のみで、`index.html` / `v2.html` は指定ビルドによる生成物。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| AV後の候補変更と0.495px原点差を特定し、歩きズームの帰属判定を実描画原点へ合わせた | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html:1034` | Layer 2 | 独立reviewerの差分確認 |
| 実ChromiumでN1〜N19・必須回帰・可視数・速度を再採点 | `C:\Users\paipa\nakayama-guidemap\handoff\2026-08-01_codex_result_AW.md` / 最悪47.6ms / ブラウザJS error 0 | Layer 3 | Python版gateはseatのWinError 5で未到達。別session reviewerが通常端末でも確認 |
| 保護ファイル・座標・生成物を検査 | `build_mapdata.py` exit 0 / 上記SHA-256 / `git diff --check` exit 0 | Layer 3 | push・deployは未実施 |

返却先: `ai:claude-code`（独立reviewer）。
