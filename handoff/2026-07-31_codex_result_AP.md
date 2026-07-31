# Task AP 実装結果

対象の手編集: `tools/v2-build/template.html`

## 結果の要点

- AP-1 は、47px 上限への射影を廃止し、`(東の実y - 西の実y) × 1.3px/m` との符号付き誤差を東西へ半分ずつ戻す射影へ変更した。
- AP-2 は候補を増やしていない。調査の結果、`中華レストラン とらの子` は通常候補が密集店への帰属判定で尽き、AO で追加した引き出し線候補は「長い店名の中央まで」を線長として測っていたため残りが130px上限を超えていた。線の終点・距離判定をラベル矩形の最寄り辺へ直した。
- AP-3 は `#listrows` の上余白を 0px から 8px へ変更した。
- ブラウザ版 `gate.py` は未実施。N20〜N50の通過主張はしない。

## AP-1 向かい合わせ

`tools/v2-build/template.html:1549-1552` で、各向かい組について次を同じ反復内で合算する。

```text
want  = (east.entry.y - west.entry.y) × STRIP_PX_PER_M
error = (east.center - west.center) - want
east  -= error / 2
west  += error / 2
```

20回の交互射影後に列ごとの最終パックを通す構造は維持した。

Node で現行配置を再現した値（カード高45px）:

| 向かい組 | 真の符号付きズレ | 画面ズレ | 誤差 | displaced |
|---|---:|---:|---:|---|
| 七十七銀行中山支店 ⇔ 志摩整骨院 | -2.5px | -2.8px | 0.3px | あり |
| ウジエスーパー中山店 ⇔ 中山郵便局 | -16.9px | -33.7px | 16.8px | あり |
| ウジエスーパー中山店 ⇔ 中山歯科 | 2.7px | 19.3px | 16.5px | あり |
| 花祭壇 ⇔ 中山不動産 | -22.6px | -62.2px | 39.6px | あり |
| 花祭壇 ⇔ 中杜建設 | -16.8px | -9.2px | 7.6px | あり |
| 花祭壇 ⇔ ダイニングバー 祭 | 12.1px | 43.8px | 31.7px | あり |
| 藤倉設備工業 ⇔ お菜とお酒アイリス | -0.5px | -0.8px | 0.3px | あり |
| 柏屋 ⇔ 河村内科外科クリニック | -0.8px | 6.2px | 7.0px | あり |
| たけむらや ⇔ ウエルシア薬局 | 25.1px | 18.7px | 6.4px | あり |
| 西原歯科医院 ⇔ cake NAO | -15.3px | -14.5px | 0.9px | あり |

- 通常扱いで誤差24px超かつ引き出し線なし: **0組**
- 引き出し線ありで誤差53px超: **0組**
- 列内最小隙間: **8.000px**
- 並び順違反: **0件**

AP-1で指摘された `cake NAO ⇔ 西原歯科医院` は、真のズレ -15.3px に対して画面 -14.5px、誤差0.9pxになった。

## AP-2 中華レストラン とらの子

### 原因調査

ブラウザを起動せず、現行の候補列・初期viewBox・店座標・17px店名寸法を使う一時Node/Pythonコードで、各候補が最初に落ちる判定枝と相手を数えた。

3端末とも候補総数は通常336 + 引き出し線84 = 420。置ける候補は修正前 **0**だった。

- 通常336候補: 自分の★が最近傍にならず全滅。`Dogsalon Blanche` は通常候補を落とす相手の一つ（360x640再現で anchor 52候補 + rect 5候補）だが、単独原因ではない。`中杜建設`、`スクールIE 仙台中山校`、`花祭壇`、`中山不動産`、`ん daccha とこや` など東側密集地の複数店が帰属判定上の相手になっていた。
- 引き出し線84候補: 46候補は画面端条件で却下。残る38候補は他店との衝突ではなく、`labelLeaderSegment()` が★から長い店名の**中央**までを測るため、全て `LEADER_MAX_PX_VOICE = 130` を超えて却下されていた。
- したがって、AO-4で引き出し線候補を増やしても、追加分のうち画面端を通るものが線長判定で全滅していた。`Dogsalon Blanche` が84候補すべてを塞いでいたわけではない。

### 修正

- `tools/v2-build/template.html:1179-1184`: 判定用の線を、★からラベル矩形の中央ではなく**最寄り辺**へ結ぶよう変更。
- `tools/v2-build/template.html:1204-1205`: 実際に描く引き出し線も同じ最寄り辺を終点にし、判定と描画を一致させた。
- 候補配列、候補数、130px上限、他店の★・ラベル・バッジ・信号との衝突条件は変更していない。

同じ一時再現では、修正後の引き出し線84候補は各端末で `画面端46 / 尚絅教会との線衝突1 / Dogsalon Blancheとの線衝突1 / 配置可能36` になった。

| 端末 | 修正前の配置可能候補 | 修正後の配置可能候補 |
|---|---:|---:|
| 360x640 | 0 | 36 |
| 375x667 | 0 | 36 |
| 390x844 | 0 | 36 |

これはNode上の候補計算であり、11店すべてが実ブラウザで表示されることの最終証拠は依頼元のブラウザ版 `gate.py` に残す。

## AP-3 お店一覧

`tools/v2-build/template.html:284` で `#listrows` の上paddingを `0` から `8px` に変更した。見出し行の直下に独立した8px床を追加し、端末幅に依存しないCSS値にした。

## 検証

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| AP-1〜AP-3をテンプレートへ実装し生成HTMLを更新 | `tools/v2-build/template.html` / `index.html` / `v2.html` | Layer 2 | ブラウザ採点待ち |
| builderと生成再現性 | `python tools/v2-build/build_mapdata.py` 最終2回 exit 0。`mapdata.json` / `index.html` / `v2.html` の連続SHA一致 | Layer 3 | なし |
| AP-1純関数再現 | 全10組の表 / 最小隙間8.000px / 並び順0件 / 通常24px超0 / 引き出し線あり53px超0 | Layer 3 | 実描画高とブラウザN42/N48は依頼元で再測定 |
| AP-2候補原因の一時再現 | 3端末で修正前0候補、修正後36候補。候補追加なし | Layer 3 | ブラウザN26で11/11を確認 |
| 生成JavaScript構文 | `index.html` / `v2.html`: scripts=1、`new Function` parse OK、exit 0 | Layer 3 | なし |
| 非ブラウザ採点 | `.tmp-runtime/task-ap-gate-no-browser.json`。N1〜N19の表示は各0件、実際の総合判定はブラウザ実測なしのためFAIL・exit 1 | Layer 3 | N20〜N50の合否根拠にしない |
| 保護ファイル・座標資産 | `git diff --exit-code -- tools/v2-build/gate.py preview.html tools/v2-build/preview.template.html tools/v2-build/mapdata.json` exit 0 | Layer 3 | なし |
| 保護SHA | `gate.py` `2D9FD3C96BA682F462F936ECF66FFD5FAADB95EA5454FBD9ADEAAD23B4CFEEAE` / `preview.html` `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44` / `preview.template.html` `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC` / `mapdata.json` `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74` | Layer 3 | なし |
| 差分健全性 | `git diff --check` exit 0 | Layer 3 | なし |

ブラウザ版 `python tools/v2-build/gate.py` は未実施。N20〜N50、特に N26 / N31 / N42 / N48 の最終判定は依頼元のブラウザ検査へ返す。
