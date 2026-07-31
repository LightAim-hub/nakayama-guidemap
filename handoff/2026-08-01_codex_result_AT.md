# Task AT 実装結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

対象の手編集: `tools/v2-build/template.html`

## 実装

- 二列模式図の信号を、カード配置後の画面上の中心座標で南北順に並べ、隣接距離が `24px + 4px` 未満の連続群を1印へ集約した。
- 代表印は群の先頭・末尾の画面座標の中点へ置いた。
- 単独印の `aria-label` は「信号」、集約印は「信号2基をまとめた印」「信号3基をまとめた印」のように基数を明示した。
- 中点へ移した代表印と道路名が重ならないよう、通常表示の道路名だけを基準位置の近傍で最短退避した。信号との隙間は4px、道路名同士の隙間も4pxを床にした。
- `GEO.signals`、`mapdata.json`、地図側の信号描画は変更していない。二列DOMは元の13要素を保持し、通常時は集約後の9印だけを表示する。

## 検証台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| 指定ビルド | `python tools/v2-build/build_mapdata.py` / exit 0 / `index.html`, `v2.html` 再生成 / 出力 `signals=13` | Layer 3 | なし |
| 生成HTMLのJavaScript構文 | Node `new Function` で `index.html`, `v2.html` の各inline scriptをparse / exit 0 | Layer 3 | なし |
| N51相当の実Chromium測定 | Chromium 148、360x640 / 375x667 / 390x844 / 428x926 / 640x360 / 844x390、各端末で「絞り込みなし」「こどもの声」「ケーキ検索」の `bad=[]` / exit 0 | Layer 3 | なし |
| 二列信号の集約条件 | 全6端末で二列DOM 13、表示9、表示印の最小中心間隔29.92px。集約ラベルは3基×1印、2基×2印 | Layer 3 | なし |
| 地図側信号 | 全6端末で `#map .signal-icon` 13。`--no-browser` の全体表示も「信号が交差点に立っている: 13 / 13」 | Layer 3 | なし |
| N26 / N37 / N38 | 現行 `gate.py` の地図測定JSと同じ歩行縮尺2px/mで `voiceHidden=[]`、leader問題0、最大42.5px（上限90px）、超過0 / exit 0 | Layer 3 | なし |
| N42 | 画面実測と現行判定式で向かい合い13組を検査し違反0 / exit 0 | Layer 3 | なし |
| N48 / N49 | 現行 `gate.py` の `STRIP_GAP_JS` / `FILTER_VIEW_JS` を実Chromiumで実行。全6端末で gap min=8px、tight=[]。各絞り込みの画面内件数は全端末6件以上 / exit 0 | Layer 3 | なし |
| N1〜N19と座標不変 | `python tools/v2-build/gate.py --no-browser` の N1〜N19 は各0件、`mapdata.json` SHA-256=`3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` | Layer 3 | `--no-browser` は総合合否根拠には使用しない |
| 保護ファイル | 作業前後SHA-256一致: `gate.py`=`BAA07409F5799C3CCEAB812E841A9F556C9571DBF4A3C793C346F2F2D6A3A1F4`、`preview.html`=`87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44`、`preview.template.html`=`ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` | Layer 3 | なし |
| 指定ブラウザ gate | `python tools/v2-build/gate.py` / exit 1。Python Playwright の子プロセス用 named pipe 作成が `PermissionError: [WinError 5]`、その例外処理が `TypeError: 'NoneType' object does not support item assignment` | Layer 2 | sandbox外で同じコマンドを実行し、N1〜N51全0件・exit 0を取得する |

## 指定 gate の扱い

`python tools/v2-build/gate.py --no-browser` は N1〜N51を0件と表示するが、出力自身が「ブラウザ実測なし」を不合格1件として exit 1にするため、総合合格の根拠にはしていない。

Python Playwrightだけがこの managed seat で子プロセス用 named pipe を作れない。sandbox外実行も実行基盤のapproval policyに拒否された。一方、同じローカル生成HTMLを同じChromiumで開き、現行 `gate.py` から抽出した重点判定JSをNode Playwright経路で実行した結果は上表の通りすべて違反0だった。

したがって、成果物はローカル実装と実ブラウザ重点回帰までの Layer 3。依頼の最終条件である `python tools/v2-build/gate.py` exit 0 は未取得なので、総合PASSや無印の完了は主張しない。

## 変更していないもの

- `tools/v2-build/gate.py`（着手前からある差分を保持）
- `preview.html`
- `tools/v2-build/preview.template.html`
- `tools/v2-build/mapdata.json`
- 店・道路・信号の座標
- git push / deploy / 本番公開
