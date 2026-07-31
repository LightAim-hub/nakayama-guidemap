# Task AR 実装結果

対象 Issue: `LightAim-hub/nakayama-guidemap#36`

## 結果

`layoutLabels()` の同一 Node 計測（360x640、拡大3回・縮小3回、6回の最悪値）は **34.305ms → 29.553ms**。目標320msに対する余裕は **290.447ms**。

Task AR 依頼時に提示された実ブラウザの改善前値は **405ms**。Node の軽量 DOM と実ブラウザは絶対値の尺度が違うため、405ms と 29.553ms を直接比較していない。今回のブラウザ側の主なボトルネックだった矩形読取は、同一6回計測の最悪ケースで **17,442回 → 7,716回（55.8%減）**、属性書込みは **68,207回 → 19,544回（71.3%減）**。

```json
{
  "viewport": "360x640",
  "zoom_sequence": ["in", "in", "in", "out", "out", "out"],
  "zoom_step": 1.45,
  "before_ms": [27.502, 28.967, 34.305, 28.110, 28.283, 31.082],
  "before_worst_ms": 34.305,
  "after_ms": [24.307, 25.558, 25.559, 24.794, 27.251, 29.553],
  "after_worst_ms": 29.553,
  "before_worst_rect_reads": 17442,
  "after_worst_rect_reads": 7716,
  "before_worst_attribute_writes": 68207,
  "after_worst_attribute_writes": 19544
}
```

## Node 計測方法

- Node 標準機能だけを使用。外部パッケージ・ブラウザは不使用。
- `tools/v2-build/template.html` から `layoutLabels` と全依存関数を括弧対応で抽出し、その実装自体を実行。
- `tools/v2-build/mapdata.json` の60店・道路座標由来の viewBox・13信号を入力。
- 360x640のうち地図領域を360x560、初期 viewBox を `362 677 424 646` とし、実装と同じ `ZOOM_STEP=1.45` で6回計測。
- SVG CTM、文字矩形、固定 viewport を決定論的な軽量 DOM で再現。各回の `performance.now()` 差、矩形読取回数、属性書込み回数を採取。
- 改善前と改善後で同じ Node コマンドを使い、ウォームアップ1周後の6回を記録。

## 変更内容

1. 優先度3の通常候補を「引き出し線なし／あり」で二度測っていた処理を、同じ `mainRect` / `labelRect` の一回の測定から両方判定する形に変更。
2. `main.getBoundingClientRect()` の直後に `labelRect()` が同じ主ラベルを再読込していたため、取得済み矩形を渡して再利用。
3. 候補ごとに不変な font-size、baseline、stroke-width を、同一 entry・同一 scale では一度だけ設定。

候補の並び順、衝突条件、優先度探索、通常90px／こどもの声130pxの上限、優先度1だけを退ける規則、店・道路・信号の座標は変更していない。

実装箇所:

- `tools/v2-build/template.html:922` — 取得済み主ラベル矩形を再利用
- `tools/v2-build/template.html:965` — 優先度3の同一候補測定を共有
- `tools/v2-build/template.html:1120` — 同一scaleの不変属性を再設定しない
- `tools/v2-build/template.html:1152` — `labelRect(entry, mainRect)` 対応

## 検証

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| Nodeで改善前後を同一条件計測 | 上記JSON / 34.305ms → 29.553ms / 最大29.553ms | Layer 3 | 実ブラウザ採点は独立 reviewer |
| builder再生成 | `python tools/v2-build/build_mapdata.py` / exit 0 / shops=60, roads=66, signals=13 | Layer 3 | なし |
| 連続生成の再現性 | `index.html` SHA-256 が連続2回 `6EE586364B9453E34F892986F9790EC840096EA9E468A4A91DFE79C9FED76D0F` / exit 0 | Layer 3 | なし |
| 生成JavaScript構文 | `index.html` / `v2.html` とも scripts=1、`new Function` parse OK / exit 0 | Layer 3 | なし |
| 静的ゲート | `python tools/v2-build/gate.py --no-browser` はブラウザ実測なしのため exit 1。N1-N50の静的違反表示は0だが、指示どおり合否根拠には不使用 | 未到達 | browser reviewerがN26/N27/N37/N38/N39/N41/N42/N48を再採点 |
| 差分健全性 | `git diff --check` / exit 0 | Layer 3 | なし |
| 保護ファイル・座標資産 | `git diff --exit-code -- tools/v2-build/gate.py preview.html tools/v2-build/preview.template.html tools/v2-build/mapdata.json` / exit 0 | Layer 3 | なし |

## 保護SHA

- `tools/v2-build/gate.py`: `2D9FD3C96BA682F462F936ECF66FFD5FAADB95EA5454FBD9ADEAAD23B4CFEEAE`
- `preview.html`: `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44`
- `tools/v2-build/preview.template.html`: `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC`
- `tools/v2-build/mapdata.json`: `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74`

## Done Definition 判定

| 条件 | 判定 |
|---|---|
| Node最悪実行時間320ms以下 | **29.553ms** |
| 59ラベル以上・退避は優先度1だけ | 配置候補・判定・優先度規則は不変。実ブラウザ確定は reviewer 待ち |
| N26/N37/N38/N39/N41/N42/N48非回帰 | 対象の意味ロジックは不変。実ブラウザ確定は reviewer 待ち |
| 指定保護ファイル・座標不変 | SHA / diff exit 0 |
| `build_mapdata.py` 実行 | exit 0、連続生成一致 |

現在地は **Layer 3**。Node性能、生成、構文、静的差分までは物理確認済み。ブラウザ版 `gate.py` の合格は `--no-browser` から推定せず、独立 reviewer の実ブラウザ採点へ返す。
