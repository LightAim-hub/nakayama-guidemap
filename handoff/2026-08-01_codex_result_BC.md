# Task BC 実装・検証結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

手編集したプロダクトソース: `tools/v2-build/template.html`

## 現在地

BC-1 の実装と `build_mapdata.py` による生成HTML更新まで実施した。現在地中心の表示範囲に店中心が3件未満の場合、5店目が入る最小倍率まで縮尺を下げる。倍率上限は「全体」表示と同じで、それ以上は下げない。

最寄り店は店舗の実投影座標 `tx` / `ty`（無い場合のみ `x` / `y`）と現在地の距離を1m=1単位で計算し、既存の二列表示と同じ `東へ約◯m` / `西へ約◯m` で状態表示する。

ただし、正本 `python tools/v2-build/gate.py` は Playwright 起動前の Windows named pipe 接続をサンドボックスに拒否され、`PermissionError: [WinError 5]`、続いて既存例外経路の `TypeError: REND is None` で exit 1 となった。権限昇格要求も実行環境ポリシーに拒否され、in-app Browser は利用可能ブラウザ0件だった。そのため、正本 gate の N1〜N52 全0件と、実ブラウザでの押下後DOM件数は本 seat では取得できていない。`--no-browser` は実行しておらず、合否根拠にも使っていない。本 handoff の上限は Layer 2 とする。

## 実装

- `shopsInViewBox()` で表示範囲内の店中心数を数える。
- 現在地へ同倍率で寄せた結果が3件以上なら、従来どおり倍率を変えない。
- 3件未満なら、現在地から5店目までの縦横距離を現在の縦横比へ換算し、5店目が入る倍率まで広げる。丸め余白は0.1%。
- 浮動小数点丸め等で5件に届かない場合だけ5%刻みで再確認し、「全体」倍率で停止する。
- `nearestShopMessage()` は実座標で最寄り店と距離を求める。範囲外判定は従来の早期 return のままで、現在地印も `viewBox` も変更しない。
- 位置取得は従来どおり `#locatebtn` の click から `getCurrentPosition()` を1回呼ぶだけ。外部送信・Web Storage処理は追加していない。

## 360x640・指定地点の決定的計算

下表は `tools/v2-build/template.html` から `shopsInViewBox()` / `currentLocationViewBox()` / `nearestShopMessage()` を抽出し、本番 `mapdata.json` と360x640の地図枠（360x540）で実行した値。店件数は描画店中心が `viewBox` 内にある数であり、実ブラウザの painted bbox / DOMラベル件数ではない。

| 押した位置 | 寄せた直後 | 自動調整後 | ★ | 状態表示 |
|---|---:|---:|---:|---|
| 商店街の端 (38.2960,140.8440) | 店1件 | **店5件** | 14px | `現在地を表示しました。いちばん近いのは 中山鳥瀧不動尊（目の神様）（西へ約224m）` |
| 投影の原点 (38.2935,140.8435) | 店24件 | **店24件**（倍率変更なし） | 14px | `現在地を表示しました。いちばん近いのは お菜とお酒アイリス（西へ約171m）` |
| 商店街中心から東へ0.7km | 初期表示のまま | **viewBox変更なし** | 14px | `今は中山から0.7km離れています` |
| 商店街中心から東へ1.4km | 初期表示のまま | **viewBox変更なし** | 14px | `今は中山から1.4km離れています` |
| 商店街中心から東へ5.0km | 初期表示のまま | **viewBox変更なし** | 14px | `今は中山から5.0km離れています` |

端の地点の自動調整後 `viewBox` は `x=587.109, y=75.679, width=782.487, height=1173.731`、画面scaleは約0.460。投影原点は `x=531.357, y=499.830, width=430.667, height=646.000`、画面scaleは約0.836。どちらも既存の `scale < 1.5 ? MAX_STAR_PX` が働き、`MAX_STAR_PX=14` のため★は14px。

実ブラウザで上表と同じ方法による「店 / ラベル」件数は未取得。ここを計算値で実測と偽装しない。通常権限で Playwright を起動できる reviewer が、端の地点で店5件以上・ラベル件数、投影原点で店件数・ラベル件数、範囲外3地点で押下前後の `viewBox` 同一を再計測する必要がある。

## 生成・静的検証

- `python tools/v2-build/build_mapdata.py`: exit 0。
  - shops=60 / roads=66 / signals=13
  - `index.html` / `v2.html` を再生成
- `tools/v2-build/template.html` / `index.html` / `v2.html`: inline script各1本、`new Function` parse成功。
- `git diff --check`: exit 0。
- 決定的関数試験: 端1→5件、原点24→24件、範囲外0.7 / 1.4 / 5.0kmはいずれも `withinCommercialArea=false`・`viewBoxChanged=false`。
- ソース検索: `getCurrentPosition` 1箇所、`fetch` / `sendBeacon` / `XMLHttpRequest` / `WebSocket` / `localStorage` / `sessionStorage` 0箇所。

## 保護対象

| ファイル | 着手前後 SHA-256 | 判定 |
|---|---|---|
| `tools/v2-build/gate.py` | `B6FCB5515ECCCB765D8B699C1CAF6D05696F51B69957042A12D7A96685B4C097` | 同一・不編集 |
| `preview.html` | `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` | 同一・不編集 |
| `tools/v2-build/preview.template.html` | `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` | 同一・不編集 |
| `tools/v2-build/mapdata.json` | `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` | 同一・座標不変 |
| `tools/v2-build/src_baseline.json` | `61A27D0CFF317B8CB3A25237BE362245C6C477B72069921F23994A3C56051EAA` | 同一 |

生成物の最終 SHA-256:

- `tools/v2-build/template.html`: `AFCD2789F46801F33C3EDF7F41FA60C01DA998240486A60A5F191FCA851EAA8E`
- `index.html` / `v2.html`: `7C89FE24A8741BCD88221F38A3BE2C46AFF1C4EB90F61C75654B5E5FD1B31ADD`

`gate.py` は着手前から dirty だったが、本作業では1文字も変更していない。`preview.html` と `tools/v2-build/preview.template.html` も変更していない。

## 正本 gate

`python tools/v2-build/gate.py`: exit 1。ブラウザ採点開始前に以下で停止。

```text
PermissionError: [WinError 5] アクセスが拒否されました。
TypeError: 'NoneType' object does not support item assignment
```

したがって、N1〜N52、ラベル可視40件以上、bbox交差0件、★60、信号13/13、配置200ms以下、位置情報の実ブラウザ回帰は未判定。Task BB のユーザー提示済み PASS を、今回の変更後 PASS として流用していない。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| 3件未満時の5店目フィットと全体倍率上限を実装 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html` | Layer 2 | 実ブラウザで押下後の店 / ラベル件数を再計測 |
| 実座標による最寄り店・距離・東西表示を実装 | 同上 / 決定的関数試験の状態表示2件 | Layer 2 | reviewer が表示文と距離を独立照合 |
| 生成HTML更新・構文・座標不変・privacy境界を検査 | build exit 0 / JS parse成功 / `git diff --check` exit 0 / 保護SHA同一 | Layer 2 | 正本ブラウザ gate の全項目確認 |
| 正本 gate を実行 | `python tools/v2-build/gate.py` exit 1 / `WinError 5`（ブラウザ評価前） | Layer 2 | 通常権限端末で exit 0 と N1〜N52全0件を取得 |

intake receipt: `C:\Users\paipa\nakayama-guidemap\.handoff_receipts\019fbc1c-3b29-70e2-98bc-8c950baf690f\LightAim-hub_nakayama-guidemap_36\intake-20260801T070132.927942Z-53592-00dd8f12caa4.json`

返却先: `ai:claude-code`（独立コード reviewer）。technical gate が pass していないため submit receipt は未発行。
