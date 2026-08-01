# Task AY — 地図を「歩く人の道具」にする 実装結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

手編集したプロダクトソース: `tools/v2-build/template.html`

## 結果

- ★は既定・全体・ズームを通して **14.00px固定**。60店すべて同じ画面pxを保つ。
- 390x844 の既定表示は **ラベル60件 / bbox交差0件 / こどもの声11店の名前11/11**。
- 地図枠とSVGは 360x640 / 390x844 / 428x926 の全幅で **充足率100%**。縦→横→縦の向き変更後も100%。
- 「現在地」は押下前の位置取得 **0回**、押下後 **1回**。位置は外部送信0件、localStorage 0件、sessionStorage 0件。
- 「全体」は店舗範囲 y=49.5〜1628.3（端から端 **1578.8m**）を含み、60店すべてがviewBox内。★は全体表示でも14.00px。

## AY-1 地図が枠を埋める

固定枠の実寸から縦横比を取り、元の中心 `(574, 1000)` を保ったまま不足方向だけ初期viewBoxを広げるようにした。`resize` / 画面向き変更時にも同じ計算をやり直す。

| 端末 | 地図枠 | SVG | 充足率 | 初期viewBox |
|---|---:|---:|---:|---|
| 360x640 | 360x490px | 360x490px | 100% | 336.69 677.00 474.61 646.00 |
| 390x844 | 390x694px | 390x694px | 100% | 362.00 622.75 424.00 754.50 |
| 428x926 | 428x776px | 428x776px | 100% | 362.00 615.63 424.00 768.75 |

390x844 → 844x390 → 390x844 と変更した実測でも、SVG/枠は `844x240 / 844x240`、復帰後 `390x694 / 390x694` で双方100%、viewBoxと枠の縦横比差0だった。

## AY-2 / AY-5 ★とラベル

★は `MIN_STAR_PX=14 / MAX_STAR_PX=14` とし、道路幅比の暴走上限は2.0。道路上でも色と形が残るよう外周を太くした。カテゴリ色は既存の医療・生活・食・教育・名所を維持し、390px実画面で判別できることを画像確認した。

18pxではなく14pxにした理由は、位置精度側のN15を守るため。390x844の実縮尺0.9198px/mで全道路との距離を再計算すると、★中心から道路帯外縁までの最小余裕は **2.729m**、★の最大食い込みは **4.881m**（上限5.0m）。中心は全店で帯の外にある。360px幅でも中心側の最小余裕は **1.342m** で正負が逆転していない。

| 端末 | ★ | 既定ラベル | bbox交差 | 声ラベル | 再配置5回の最悪 |
|---|---:|---:|---:|---:|---:|
| 360x640 | 60件 / 14.00px | 56件 | 0 | 11/11 | 35.1ms |
| 390x844 | 60件 / 14.00px | 60件 | 0 | 11/11 | 29.9ms |
| 428x926 | 60件 / 14.00px | 60件 | 0 | 11/11 | 29.2ms |

ラベルは通常14px、こどもの声14px、その他の主要施設16px。最低40件、N26の11店、交差0、200ms上限を保った。

## AY-3 現在地

下帯に高さ44pxの「現在地」ボタンを追加した。実装は次の通り。

1. ボタンのクリックハンドラ内だけで `navigator.geolocation.getCurrentPosition` を1回呼ぶ。
2. 取得した緯度経度を、既存 `GEO.meta.proj` の回転・原点で端末内の地図座標へ変換する。
3. 商店街範囲内なら、既存配色に合わせた青緑の現在地点（直径16px、白い外周）と精度円を表示し、その点へ寄せる。
4. 範囲外なら「今は中山からXXkm離れています」と表示し、viewBoxを変えない。
5. 拒否・タイムアウト・非対応では短い文言だけを表示し、地図を変えない。

実Chromiumの決定的スタブによる測定:

- 範囲内・精度80m: 押下前0回 → 押下後1回。精度円半径80m、現在地点表示、viewBox移動。
- 範囲外（東京駅付近）: 「今は中山から306km離れています」、viewBoxは押下前後で完全一致。
- 拒否: 「位置情報は許可されませんでした」、viewBoxは押下前後で完全一致。
- 3ケースとも押下後のネットワークリクエスト0件、localStorage/sessionStorageは前後とも0件。
- `template.html` 内の位置取得は `getCurrentPosition` 1箇所だけ。`fetch` / `sendBeacon` / 永続ストレージ呼出しは0箇所。

## AY-4 全体

高さ44pxの「全体」ボタンを現在地の隣に追加した。60店の実座標bboxに15mずつ余白を足し、その端末の地図枠比率へ不足方向だけ拡張する。360x640 / 390x844 / 428x926 / 640x360 の全4端末で **60/60店がviewBox内**、★はすべて14.00pxだった。

## 検証と制約

- `python tools/v2-build/build_mapdata.py`: exit 0、shops=60 / roads=66 / signals=13、`index.html` / `v2.html` 再生成。
- 生成HTMLのinline JavaScript: `index.html` / `v2.html` ともparse成功。
- Node Playwright + Chromium で上記4端末、向き変更、全体表示、現在地3分岐を実測。ブラウザJS error 0。
- `git diff --check`: exit 0。
- `preview.html` / `tools/v2-build/preview.template.html` / `tools/v2-build/mapdata.json` / `tools/v2-build/src_baseline.json`: `git diff --exit-code` 0。
- 店・道路・信号の正本 `mapdata.json` SHA-256は作業前後同一 `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74`。
- `gate.py` は着手前からユーザー差分あり。Codexは変更していない。現SHA-256 `735A26327E003B041DF9D2D218AD55AD937D096EA89CCFBD58F0DA1352A48ECF`。
- `preview.html` SHA-256 `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44`。
- `tools/v2-build/preview.template.html` SHA-256 `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC`。

### 公式gateの扱い

`python tools/v2-build/gate.py` は exit 1。Python Playwrightがブラウザ起動前のnamed pipe作成で `PermissionError: [WinError 5]` となり、その既存例外経路が `REND=None` への代入で `TypeError` になった。`gate.py` は変更していない。

`python tools/v2-build/gate.py --no-browser` の「違反0件」は総合合否根拠に使っていない。上記のNode実Chromium測定は実装自己検査であり、依頼者側の公式ブラウザ検査 N20〜N52 は未実施扱いとする。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| 枠比率viewBox、14px★、現在地、全体表示を実装 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html` | Layer 2 | 独立reviewerの差分確認 |
| 3縦幅＋横向き、向き変更、位置3分岐、全体表示を実Chromium測定 | 本ファイルの数値 / Node Chromium exit 0 / JS error 0 | Layer 3 | 依頼者側の公式ブラウザgate |
| 生成・構文・保護ファイル・座標を検査 | `build_mapdata.py` exit 0 / JS parse exit 0 / protected diff exit 0 | Layer 3 | push・deployは未実施 |

返却先: 独立コードreviewer。
