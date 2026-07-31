# Task AS 実装結果

対象 Issue: LightAim-hub/nakayama-guidemap#36

対象の手編集: tools/v2-build/template.html

## 結果

- AS-1: compact 状態の帯高から道路名の本数と位置を再計算するようにした。信号は compact 中に display:none まで保証し、390x844・こどもの声絞り込みでは道路名3本、信号0本、装飾重なり0組。
- AS-2: Intl.Segmenter('ja', {granularity:'word'}) で店名を語単位 span にし、「丁目」「支店」「薬局」「センター」「クリニック」は直前語と結合した。カード名は2行上限。360x640 / 390x844 / 768x1024 の全60店で3行、語 span の途中折れ、2行枠外への隠れはいずれも0件。
- AS-3: 地図下帯の文言を「通りへ」に変更。390x844で帰属・お店一覧・通りへ・ズームはすべて高さ44px、隣接間隔は左から8px / 8px / 8px。
- AS-4: .strip-guide を通常フローへ戻し、行が sticky 帯の背面へ入る構造をなくした。390x844の9スクロール位置で半端に隠れる行0件、遠方節見出しの部分隠れ0件。
- 横向き compact では東西見出しだけ畳み、640x360でも N49 の最低6件を確保した。

## 検証

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| テンプレート変更と生成HTML再生成 | python tools/v2-build/build_mapdata.py / exit 0 / C:/Users/paipa/nakayama-guidemap/index.html / v2.html | Layer 2 | なし |
| 生成HTMLのJavaScript構文 | index.html JS parse OK / v2.html JS parse OK / exit 0 | Layer 3 | なし |
| AS-1〜AS-4の実Chromium測定 | Playwright Chromium 148 / 360x640・375x667・390x844・428x926・640x360・844x390 / 各測定 exit 0 | Layer 3 | 指定 Python gate の起動制約は下記 |
| N26 | 6端末すべて voiceHidden=[] | Layer 3 | なし |
| N42 / N48 / N49 / N51 | 6端末すべて faceBad=0 / gapMin=8px, gapBad=0 / 各絞り込み visible>=6 / decor.bad=0 | Layer 3 | なし |
| N1〜N19 と座標不変 | python tools/v2-build/gate.py --no-browser では N1〜N19 各0件（総合合否根拠には未使用）。生成HTMLの GEO SHA-256 は HEAD と同一 3447daf4a45cd66df785e5f01096323e6de160b642a46ac562d387fb19cc9c74 | Layer 3 | なし |
| 禁止ファイル | git diff --exit-code -- preview.html tools/v2-build/preview.template.html tools/v2-build/mapdata.json / exit 0。tools/v2-build/gate.py は着手前からある N51 追加差分を保持し、Codexは未編集 | Layer 3 | なし |
| 指定ブラウザ gate | python tools/v2-build/gate.py / exit 1。Playwright の子プロセス用 named pipe が PermissionError: [WinError 5]、続いて gate の例外処理が TypeError: 'NoneType' object does not support item assignment | Layer 2 | サンドボックス外の通常端末で同じコマンドを1回実行し、N1〜N51全0件・exit 0を取得する |

## 指定 gate の扱い

--no-browser の表示を合格根拠にはしていない。Python版 Playwrightだけがこの managed seat の子プロセス用パイプ作成を拒否される一方、同梱 Playwright の Chromium は Node 経路で起動でき、上記の実画面測定は通った。

したがって成果物はローカル実装・実ブラウザ回帰までの Layer 3 相当だが、依頼の Done Definition である python tools/v2-build/gate.py exit 0 は未取得。無印の完了・総合 PASS は主張しない。

## 変更していないもの

- tools/v2-build/gate.py
- preview.html
- tools/v2-build/preview.template.html
- tools/v2-build/mapdata.json
- 店・道路・信号の座標
- git push / deploy / 本番公開
