# BP: 案内文の「1文字だけの行」を止める

`gate.py` の **N58** をボタン・チップ以外の短い案内文にも広げたところ、**FAIL 2件**。
2件目は **普通の文字サイズ（360x640・16px）でいまの本番に出ている**。

```
.detail-guide の「左右にスワイプして次へ」→ 「へ」だけが1行に取り残される [390x844 文字32px 詳細シート]
.empty-help-title の「1件見つかりました。上のお店を押すと詳しく見られます」
    → 「す」だけが1行に取り残される [360x640 検索中]
```

## 触ってよい / いけない

- 触る: `tools/v2-build/template.html`
- **触らない: `tools/v2-build/gate.py` / `index.html` / `v2.html` / `mapdata.json` / `official_details.json`**

## やること

この2つの文が、最後の1文字だけ次の行に落ちないようにする。
すでに同じ問題を `.strip-shop-name`（`text-wrap:pretty`）と `.chip .lbl`（`word-break:keep-all`）で
一度解いているので、**新しいやり方を発明せず、そこと同じ手を当てること。**

- **文言は変えないこと。** 短くして逃げるのは不可（読む人に必要な案内なので）
- `.detail-guide` は詳細シートの操作案内、`.empty-help-title` は検索結果0〜1件の時の案内

## 合格条件

1. `python tools/v2-build/build_mapdata.py` が通り、`index.html` / `v2.html` が更新される
   （**ここまでやること。** 前回 template だけ直してビルドを反映し忘れ、gate が赤のままだった）
2. `python tools/v2-build/gate.py --target index.html` が **PASS（違反0件・N1〜N61）**
3. 歩ける店 60/60 / JSエラー 0

※ この環境では Codex からブラウザを起動できないことがある（WinError 5）。
その場合は **ビルドまで必ず終わらせて**、gate は未実行と正直に書くこと。
