# Task BB 実装・検証結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

手編集したプロダクトソース: `tools/v2-build/template.html`

## 現在地

N45 の指摘に対し、選択肢2（断りは現在地ボタンの `title` と `aria-describedby` で常時伝え、画面上の status は取得操作中・結果通知時だけ一時表示）で実装した。

`#locationStatus` は地図を開いた直後には表示せず、位置取得中・取得結果・取得失敗、および全体表示の状態通知時だけ表示する。表示中も `pointer-events:none` なので、下の店へのポインター入力を塞がない。位置取得結果は4.5秒（全体表示は2.5秒）で消え、要素の本文は `押した時だけ位置を使います` に戻る。

ただし、正本 `python tools/v2-build/gate.py` はブラウザ評価開始前に Windows sandbox の named pipe 作成を拒否され、`PermissionError: [WinError 5]`、続いて既存例外経路の `TypeError: REND is None` で exit 1 となった。sandbox 外実行の権限要求も実行環境のポリシーで拒否され、Node Chromium は `spawn EPERM`、アプリ内ブラウザは利用可能ブラウザ0件だった。このため公式の N1〜N52 全0件・exit 0 は本 seat では取得できていない。`--no-browser` は診断にのみ使い、合否根拠にはしていない。本 handoff の上限は Layer 2 とする。

## 実装

- `#locationStatus` の地図表示時を既定 `display:none` に変更し、`.is-visible` の時だけ `display:flex` にした。
- `#locationStatus` に `pointer-events:none` を設定した。
- 現在地ボタンの `title` を `現在地を表示（押した時だけ位置を使います）` に変更した。
- `aria-describedby="locationStatus"`、`role="status"`、`aria-live="polite"` は維持した。
- `announceLocationStatus(message, hideAfter)` を追加し、取得中は継続表示、取得・拒否・失敗結果は4.5秒、全体表示は2.5秒で消すようにした。
- 通知が消えた後は `#locationStatus` の本文を断り書きへ戻し、現在地ボタンの説明が失われないようにした。

## 生成と静的検証

- `python tools/v2-build/build_mapdata.py`: exit 0。
  - shops=60 / roads=66 / signals=13
  - `index.html` / `v2.html` を再生成
- `tools/v2-build/template.html` / `index.html` / `v2.html`: inline script各1本、`new Function` parse成功。
- 3ファイルすべてで次の8条件を機械確認: `role=status` + `aria-live=polite`、`aria-describedby`、断り入り `title`、初期非表示、`.is-visible` 表示、`pointer-events:none`、一時通知関数、断り書きへの復元。
- `git diff --check`: exit 0。
- Task BB の `template.html` 差分は着手前コピー比で +24 / -9 行。店・道路・信号の座標を含む `mapdata.json` と `src_baseline.json` は着手前後 SHA-256 同一。

## 保護対象

| ファイル | 着手前後 SHA-256 | 判定 |
|---|---|---|
| `tools/v2-build/gate.py` | `B6FCB5515ECCCB765D8B699C1CAF6D05696F51B69957042A12D7A96685B4C097` | 同一・不編集 |
| `preview.html` | `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` | 同一・不編集 |
| `tools/v2-build/preview.template.html` | `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` | 同一・不編集 |
| `tools/v2-build/mapdata.json` | `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` | 同一・座標不変 |
| `tools/v2-build/src_baseline.json` | `61A27D0CFF317B8CB3A25237BE362245C6C477B72069921F23994A3C56051EAA` | 同一 |

`gate.py` は着手前から dirty だったが、Task BB では1文字も変更していない。`preview.html` と `tools/v2-build/preview.template.html` も変更していない。

## gate

### 公式ブラウザ版

`python tools/v2-build/gate.py`: exit 1。ブラウザ測定の前段で次の環境エラー。

```text
PermissionError: [WinError 5] アクセスが拒否されました。
TypeError: 'NoneType' object does not support item assignment
```

これは採点違反の出力ではなく、Python Playwright が起動できず `REND` が作られる前の失敗。`gate.py` は依頼どおり変更していない。

### 非ブラウザ診断（合否根拠には不使用）

`python tools/v2-build/gate.py --no-browser`: N1〜N52 の表示は各0件、信号13/13、歩ける店60/60。ただし `ブラウザ実測なし` 1件で判定は FAIL / exit 1。依頼どおり、この結果を PASS 根拠には使わない。

### N45 の実装上の照合

正本 N45 は、地図上の候補要素について `display:none` / `visibility:hidden` / `opacity:0` を除外し、表示中の非操作要素は `pointer-events:none` なら「下のタップを塞ぐ」違反から除外する。今回の `#locationStatus` は初期 `display:none`、一時表示時も `pointer-events:none` なので、指摘された常駐204x32px・`pointer-events:auto` の状態はソース上解消している。ただしこれは公式ブラウザ版 exit 0 の代替証拠ではない。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| N45 の常駐 status を、断りを保つ一時通知へ変更 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html` | Layer 2 | 独立 reviewer が差分と画面挙動を確認 |
| 生成HTMLを更新し、構文・ARIA・通知状態・保護対象を検査 | build exit 0 / JS parse成功 / `git diff --check` exit 0 / 保護SHA同一 | Layer 2 | 通常権限端末で公式ブラウザ gate を実行 |
| 公式 gate を実行 | `python tools/v2-build/gate.py` exit 1 / `WinError 5`（ブラウザ評価前） | Layer 2 | `python tools/v2-build/gate.py` exit 0 と N1〜N52 全0件を取得後に Layer 3 判定 |

intake receipt: `C:\Users\paipa\nakayama-guidemap\.handoff_receipts\019fbc09-d2c6-7ec0-b614-25603bd9a00a\LightAim-hub_nakayama-guidemap_36\intake-20260801T064032.063615Z-60620-86e8ddee4f7c.json`

`codex-handoff-gate layer`: `Layer 2`（canonical artifact 5 files を再読込）。technical gate が pass していないため submit receipt は未発行。

返却先: `ai:claude-code`（独立コード reviewer）。
