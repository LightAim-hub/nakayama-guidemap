# Task AX — 地図モードの N21 / N28 修正結果

手編集したプロダクトソース: `tools/v2-build/template.html`

## 結論

- `#mapFilterBadge` を 14px にし、こどもの声だけで絞り込んだ表示を `声 11件` に短縮した。完全な文言 `こどもの声 11件` は `title` と `aria-label` に残した。
- 地図下帯の2ボタンを 1.2:1 の幅配分へ変更し、`#mapbtn` / `#listbtn` を `white-space:nowrap` にした。
- 360x640 の実Chromiumでは、バッジは clientWidth / scrollWidth とも108pxで省略なし。`#listbtn` は86.2x44px、隣の `#mapbtn` との間隔は8pxで、`お店一覧` は1行だった。

## 実装差分

`tools/v2-build/template.html` のみを `codex.exe --codex-run-as-apply-patch` で手編集した。

1. 地図モードの `.map-filter-badge` を `font-size:12px` から `14px` へ変更。
2. こどもの声だけの絞り込み時は表示を `声 N件` に短縮。完全な説明は `title` / `aria-label` に保持。
3. 地図下帯を `1.35fr 1fr` から `1.2fr 1fr` へ変更し、一覧側の幅を確保。
4. 地図下帯の `#mapbtn` / `#listbtn` に `white-space:nowrap` を追加。

`python tools/v2-build/build_mapdata.py` を最終差分後に実行し、`index.html` / `v2.html` を再生成した。exit 0、shops=60 / roads=66 / signals=13。

## 実ブラウザ検証

この managed Windows seat では Python Playwright がブラウザ起動前の named pipe 作成で `PermissionError: [WinError 5]` になり、その後 `gate.py` の既存例外経路が `REND=None` に対して代入して `TypeError` となるため、`python tools/v2-build/gate.py` は exit 1だった。`gate.py` は変更していない。

`--no-browser` はブラウザ合否根拠にせず、Python Playwright と同梱の Chromium を Node ドライバから直接起動した。更新済み `gate.py` から `SWEEPJS`、追加済み6状態、`MAP_FRAME_JS`、`TIMEJS`、既存地図計測 `JS` を読み出して、そのまま実ページに評価した。

### UI総なめ

対象端末: 360x640 / 375x667 / 390x844 / 428x926 / 640x360 / 844x390。

各端末で「開いた直後・詳細シート・チューザー・お店一覧・検索中・地図・地図で絞り込み中」の42 device-state 組合せを測定した。

| gateの収集配列 | 対応項目 | 違反 |
|---|---|---:|
| `texts` | N21 | 0 |
| `taps` | N20 | 0 |
| `wrap` | N28 | 0 |
| `clip` | N29 | 0 |
| `contrast` | N30 | 0 |
| `gaps` | N31 / N44 | 0 |
| `emoji` | N34 | 0 |

360x640「地図で絞り込み中」の実寸:

| 要素 | 実測 |
|---|---|
| `#mapFilterBadge` | 14px / 110x24.1px / clientWidth=108 / scrollWidth=108 / 表示 `声 11件` / aria-label `こどもの声 11件` |
| `#listbtn` | 86.2x44px / 1行 / scrollWidth=clientWidth=82px |
| `#mapbtn` | 71.8x44px / 1行 |
| 一覧―戻るボタン間 | 8px |
| 拡大 / 縮小 | 各44x44px / 相互間隔8px |

### 地図枠・ラベル・性能

- 全6端末の `MAP_FRAME_JS`: 地図上のUI被覆0、縁切れ0、見出しあり、戻る手段あり。
- 360x640: 地図占有84.4%、被覆0、縁切れ0。
- 390x844: 地図占有88.2%、被覆0、縁切れ0。
- 既定ズーム: ラベル可視59、bbox交差0、こどもの声11店の名前欠け0、固定UI被覆0、信号との交差0。
- 歩きズーム2.0px/m: ラベル可視62、bbox交差0、こどもの声11店の名前欠け0、固定UI被覆0、信号との交差0。
- ★60 / 信号13 / 店舗60。ブラウザJS error 0。
- 360x640 の `TIMEJS` 5試行: 30.7 / 28.3 / 30.0 / 28.7 / 30.1ms。最悪30.7msで依頼上限200ms以内。

静的部分は `python tools/v2-build/gate.py --no-browser` で N1〜N51 の各表示が0、歩ける店60/60、信号13/13を確認した。ただし同コマンド自身が示すとおりブラウザ未実行なので、これ単独を総合合否根拠にはしていない。

## ファイル境界

- `git diff --check`: exit 0。
- `index.html` / `v2.html` のinline JavaScript: 両方 parse成功。
- `index.html` と `v2.html` は同一SHA-256: `7FD2ED482460669970FB0B1F856119DAACA7CE5D3D71E151C58CFEC3A5D678F2`。
- `preview.html` / `tools/v2-build/preview.template.html` / `tools/v2-build/mapdata.json` / `tools/v2-build/src_baseline.json`: `git diff --exit-code` 0。
- `tools/v2-build/gate.py` は着手前からユーザー差分あり。Codexは触っておらず、作業前後SHA-256は `A19642DFABA9CD54573B3F48CE1A2F04249878D16F6E6ACA512F068BA270EC5C`。
- `tools/v2-build/mapdata.json` SHA-256: `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74`。店・道路・信号座標は変更していない。

## 4列台帳

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| N21 / N28 を修正し生成HTMLを更新 | `C:\Users\paipa\nakayama-guidemap\tools\v2-build\template.html` / `build_mapdata.py` exit 0 | Layer 2 | 独立reviewerの差分確認 |
| 更新済み総なめ・地図枠・ラベル・性能を実Chromiumで再測 | 本ファイルの実測値 / 42 device-state違反0 / 最悪30.7ms | Layer 3 | Python版 `gate.py` の通常起動は seat の WinError 5 で未到達。通常実行可能な別sessionで公式exit 0を確認 |
| 保護ファイル・座標・生成物を検査 | 上記SHA-256 / `git diff --check` exit 0 / protected diff exit 0 | Layer 3 | push・deployは未実施 |

返却先: 独立コードreviewer。
