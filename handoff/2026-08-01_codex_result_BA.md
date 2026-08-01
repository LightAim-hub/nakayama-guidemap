# Task BA 実装・検証結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

手編集したプロダクトソース: `tools/v2-build/template.html`

## 現在地

BA-1 / BA-2 は `template.html` に反映し、生成HTMLを実 Chromium で再計測した範囲では、N21相当4件とN47相当の端切れは6端末すべて0件になった。ラベル数・交差・★・信号・配置時間・位置情報の礼儀も回帰していない。

ただし正本の `python tools/v2-build/gate.py` は、評価開始前の Python Playwright 接続で Windows sandbox が named pipe を拒否し、`PermissionError: [WinError 5]`、続く既存例外経路で `TypeError: REND is None` となった。したがって公式の N1〜N52 全0件・exit 0 は未取得であり、`codex-handoff-gate layer` の算出どおり本 handoff の上限は Layer 2（実装物を再読込可能）とする。`--no-browser` は合否根拠に使っていない。

## BA-1 浮きボタン

- `#locatebtn` の文字を削除し、円・十字・中心点からなる24pxの照準SVGへ変更した。
- `aria-label="現在地"`、`title="現在地を表示"`、`aria-describedby="locationStatus"` を持たせた。絵文字は使っていない。
- `#wholebtn` は表示文字14px、`aria-label/title="商店街の全体を見る"`。
- `#zin` / `#zout` は18px。4ボタンは44x44px、右8px、間隔8pxの既存配置を維持した。

実 Chromium で 360x640 / 375x667 / 390x844 / 428x926 / 640x360 / 844x390 を測定し、N21相当・N20相当・N34相当は各端末0件。計算済みfont-sizeは `locate=14 / whole=14 / zin=18 / zout=18px`。

## BA-2 可視帯の端

AM-1 の `labelInsideViewport()` は viewport の四辺6pxを見ていた。ただし候補矩形は★の painted bbox中心を基準に作り、実ラベルは店舗座標を基準に描くため、実描画補正が可視帯判定へ渡っていなかった。また候補計測の `getBBox()` はアウトラインを含む実描画より数px小さく、帯の外に完全に出たと判定した候補が実際には帯へ戻っていた。

次を修正した。

1. 店舗座標と★bbox中心の差分を、所有権判定だけでなく可視帯・keep-out・地図記号・ラベル衝突の候補矩形へ一貫して反映。
2. 可視帯判定だけは候補矩形へ4pxの計測安全余白を足し、実描画が6px境界へ触れないようにした。

正本 `MAP_FRAME_JS` をそのまま実 Chromium で評価した結果、6端末すべて `cut=[]`。指摘された「スクールIE 仙台中山校」「尚絅教会」「西原歯科医院」に加え、375x667で一時的に端へ移った `Dogsalon Blanche` も最終計測では端切れ0件。

## 実ブラウザ回帰

| viewport | N21相当 | N47相当 | 可視ラベル | bbox交差 | ★ | 信号 | 地図充足率 | 配置最悪 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 360x640 | 0 | 0 | 55 | 0 | 60 / 14px | 13 | 100% | 38.2ms |
| 375x667 | 0 | 0 | 55 | 0 | 60 / 14px | 13 | 100% | 33.0ms |
| 390x844 | 0 | 0 | 57 | 0 | 60 / 14px | 13 | 100% | 31.5ms |
| 428x926 | 0 | 0 | 60 | 0 | 60 / 14px | 13 | 100% | 35.7ms |
| 640x360 | 0 | 0 | 42 | 0 | 60 / 14px | 13 | 100% | 40.2ms |
| 844x390 | 0 | 0 | 43 | 0 | 60 / 14px | 13 | 100% | 39.0ms |

正本ゲート内の既定/歩きズーム計測JSもそのまま評価した。既定はラベル59件・交差0・★60（14px）・信号13、歩きズームはラベル62件・交差0・信号13。N4/N13/N14/N17/N18/N19/N37/N38/N39相当の候補は両倍率とも0件。歩きズームの★は既存仕様どおり10.9pxで、N12の対象である既定ズームは14pxを維持している。

位置情報の決定的スタブでは、地図を開く前・現在地押下前の取得0回、押下後1回、押下後の外部request 0件、localStorage/sessionStorage各0件。拒否時は「位置情報は許可されませんでした」と表示し、JS errorは全端末0件。

## 生成・ファイル境界

- `python tools/v2-build/build_mapdata.py`: exit 0、shops=60 / roads=66 / signals=13、`index.html` / `v2.html` 再生成。
- `index.html` / `v2.html`: inline script各1本、`new Function` parse成功。
- `git diff --check`: exit 0。
- `tools/v2-build/gate.py` は着手前からdirtyだったが、本作業では不編集。着手前後SHA-256は同一。
- `preview.html` / `tools/v2-build/preview.template.html` / `mapdata.json` / `src_baseline.json` は着手前後SHA-256同一。店・道路・信号座標は変更していない。

| ファイル | SHA-256 |
|---|---|
| `tools/v2-build/template.html` | `24BB9A5D1050A0A677B487AD9D30C8FE9BF5C74E220F3E0B03BC2ECF590FF45D` |
| `index.html` / `v2.html` | `28E9D0DDAA0C5B72DDB1302FD67F8FEC50E180E1B243AC00444141ACD695C5B9` |
| `tools/v2-build/gate.py` | `92832D510ADBFF8ED2AC135E110D6B85024CB2F329DA05A3B0C14FD17985FBA6` |
| `preview.html` | `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` |
| `tools/v2-build/preview.template.html` | `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` |
| `tools/v2-build/mapdata.json` | `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` |
| `tools/v2-build/src_baseline.json` | `61A27D0CFF317B8CB3A25237BE362245C6C477B72069921F23994A3C56051EAA` |

## 公式 gate

最終版に対して `python tools/v2-build/gate.py` を再実行したが exit 1。ブラウザ評価前の named pipe 作成で `PermissionError: [WinError 5]`、続いて既存の `REND=None` 例外経路で `TypeError`。`gate.py` を直すことは依頼範囲外かつ禁止されているため触っていない。

`python tools/v2-build/gate.py --no-browser` は診断目的にだけ実行し、合否根拠には不使用。正本 exit 0 の取得には、Windows sandbox外の通常端末で同じ公式コマンドを1回実行する必要がある。

`codex-handoff-gate layer` は `Layer 2`。正本 technical gate がpassしていないため reviewer submit は `technical_gate must pass` で拒否され、submit receiptは未発行。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| BA-1/BA-2を実装し生成HTMLを更新 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html` / build exit 0 | Layer 2 | 独立コードreviewerの差分確認 |
| 6端末・既定/歩きズーム・位置情報を実 Chromium で再計測 | 本文の数値 / JS error 0 / 最悪40.2ms | Layer 2 | 公式 Python gate は環境ブロックのため未取得 |
| 保護ファイル・座標・構文・差分を検査 | SHA-256同一 / JS parse成功 / `git diff --check` exit 0 | Layer 2 | sandbox外で `python tools/v2-build/gate.py` exit 0 を取得し、独立reviewerへ返す |

返却先: `ai:claude-code`（独立コードreviewer）。
